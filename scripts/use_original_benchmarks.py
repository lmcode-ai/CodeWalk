"""Connect the supplied benchmark scripts and exports to the CodeWalk workspace."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from codewalk.data import public_record, read_jsonl, safe_path
from codewalk.evaluation import COMPLEXITY_LABELS


def write_rows(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(''.join(json.dumps(row) + '\n' for row in rows), encoding='utf-8', newline='\n')


def rebuild_repair(published, output):
    receipt = json.loads((ROOT / 'docs/sources/bugfixing-download-receipt.json').read_text(encoding='utf-8'))
    expected = receipt['files']['data/test.jsonl']['sha256']
    if hashlib.sha256(published.read_bytes()).hexdigest() != expected:
        raise ValueError('The published repair file does not match the pinned release hash')
    cache = {}
    for task in read_jsonl(published):
        for bug in task['bugs']:
            row = {'base': bug['base_commit'], 'patch': bug['gold_patch'],
                   'test_patch': bug['test_patch'], 'F2P': bug['FAIL_TO_PASS'], 'source': task['source']}
            previous = cache.setdefault(bug['instance_id'], row)
            if any(previous[key] != value for key, value in row.items()):
                raise ValueError('Conflicting bug definitions in the pinned release')
        if task['source'] == 'swerebenchv2':
            first = cache[task['bugs'][0]['instance_id']]
            if first.setdefault('image', task['image']) != task['image']:
                raise ValueError('Conflicting image for the same base instance')
    original = ROOT / 'original/bugfixing'
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='repair-rebuild-', dir=output.parent) as temporary:
        work = Path(temporary)
        cache_file = work / 'instances_cache.json'
        cache_file.write_text(json.dumps(cache), encoding='utf-8')
        subprocess.run([sys.executable, str(original / 'assemble.py'), '--cache', str(cache_file),
                        '--out-dir', str(work)], cwd=original, check=True)
        assembled = work / 'benchmark_dataset.jsonl'
        # The original writer uses platform newlines. Normalize the transport bytes.
        content = assembled.read_bytes().replace(b'\r\n', b'\n')
        if hashlib.sha256(content).hexdigest() != expected:
            raise ValueError('Original assembler output differs from the pinned repair release')
        assembled.write_bytes(content)
        output.mkdir()
        for file in work.iterdir():
            file.replace(output / file.name)
    return {'tasks': len(read_jsonl(output / 'benchmark_dataset.jsonl')), 'published_sha256': expected,
            'exact_release_match': True, 'fresh_modal_gates_run': False}


def import_clone(inputs, output):
    public, judge = [], []
    seen = set()
    for path in inputs:
        rows = read_jsonl(path) if path.suffix.lower() == '.jsonl' else json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(rows, list) or not rows:
            raise ValueError(f'Expected a nonempty array or JSONL file of rendered tasks: {path}')
        for row in rows:
            identity = row.get('id', row.get('task_id'))
            if not isinstance(identity, str) or not identity or identity in seen:
                raise ValueError(f'Missing or repeated clone ID in {path}')
            if type(row.get('level')) is not int or row['level'] < 1 or row.get('label') not in ('equivalent', 'not_equivalent'):
                raise ValueError(f'Invalid level or label for {identity}')
            payload = public_record('codeclone', row)
            if any(not isinstance(payload[key], str) or not payload[key].strip() for key in ('side_a_code','side_b_code')):
                raise ValueError(f'Missing rendered Java source for {identity}')
            seen.add(identity)
            task_id = 'original-codeclone:' + identity
            public.append({**payload, 'task_id':task_id,
                           'question':'Decide whether the two Java programs are equivalent. Answer with one line: VERDICT: 1 for equivalent or VERDICT: 0 for not equivalent.'})
            judge.append({'task_id':task_id,'level':row['level'],'label':row['label'],'source_task_id':identity})
    output.mkdir(parents=True)
    write_rows(output / 'model_inputs/codeclone.jsonl', public)
    write_rows(output / 'judge/codeclone.jsonl', judge)
    return {'tasks':len(public), 'counts_by_level':dict(sorted(Counter(row['level'] for row in judge).items())),
            'inputs':[{'file':path.name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()} for path in inputs]}


def render_clone(database, positive, negative, level, output):
    if not database.is_file():
        raise ValueError('A local FEMPD SQLite database is required')
    original = ROOT / 'original/codeclone/composition'
    # The archived renderer resolves its sibling modules from its working directory.
    renderer = '''
import sqlite3
import sys
from render_full import render_level

connection = sqlite3.connect(sys.argv[1], uri=True)
connection.text_factory = bytes
try:
    render_level(connection, int(sys.argv[2]), *sys.argv[3:])
finally:
    connection.close()
'''
    with tempfile.TemporaryDirectory(prefix='clone-render-') as temporary:
        rendered = Path(temporary) / f'l{level}_full.json'
        subprocess.run([sys.executable, '-c', renderer, database.resolve().as_uri() + '?mode=ro',
                        str(level), str(positive.resolve()), str(negative.resolve()), str(rendered)],
                       cwd=original, check=True)
        result = import_clone([rendered], output)
        (output / rendered.name).write_bytes(rendered.read_bytes())
    return result


def import_verus(source, output):
    original = ROOT / 'original/verus'
    manifest = json.loads((original / 'published-manifest.json').read_text(encoding='utf-8'))
    reference_hashes = json.loads((original / 'reference-sha256.json').read_text(encoding='utf-8'))
    taskify = runpy.run_path(str(original / 'taskify.py'))['taskify']
    public, judge, references = [], [], {}
    for row in manifest['tasks']:
        identity = row['id']
        provenance = row['provenance']
        task_path = safe_path(source, f"{row['original_bank']}/{identity}.rs")
        reference_path = safe_path(source, f"{provenance['round']}/{provenance['file']}")
        task_bytes, reference_bytes = task_path.read_bytes(), reference_path.read_bytes()
        if hashlib.sha256(task_bytes).hexdigest() != row['sha256']:
            raise ValueError(f'Published task hash mismatch for {identity}')
        if hashlib.sha256(reference_bytes).hexdigest() != reference_hashes[identity]:
            raise ValueError(f'Archived reference hash mismatch for {identity}')
        task = task_bytes.decode('utf-8')
        if taskify(reference_bytes.decode('utf-8')) != task:
            raise ValueError(f'Original taskifier did not reproduce {identity}')
        task_id = 'original-verus:' + identity
        relative = f'judge/references/{identity}.rs'
        public.append({'task_id':task_id,'files':{'task.rs':task},
                       'question':'Complete proof annotations and postconditions. Preserve executable code and preconditions. The grader restores original specification predicates and chain_driver.'})
        judge.append({'task_id':task_id,'level':row['level'],'reference_file':relative,
                      'source_task_id':identity,'reference_sha256':reference_hashes[identity],
                      'public_sha256':row['sha256'],'provenance':provenance})
        references[relative] = reference_bytes
    output.mkdir(parents=True)
    write_rows(output / 'model_inputs/verus.jsonl', public)
    write_rows(output / 'judge/verus.jsonl', judge)
    for relative, content in references.items():
        path = safe_path(output, relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    return {'tasks':len(public),'counts_by_level':manifest['level_counts'],
            'published_hash_matches':len(public),'original_reference_hash_matches':len(references),
            'original_taskifier_exact_matches':len(public),'historical_model_results_bound':False}


def import_bigo(inputs, output):
    public, judge = [], []
    seen = set()
    source_hashes = []
    for path in inputs:
        source_hashes.append({'file':path.name, 'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
        rows = read_jsonl(path)
        if not rows:
            raise ValueError(f'Expected a nonempty original BigO JSONL file: {path}')
        for row in rows:
            identity, level, label, source = (row.get(key) for key in ('id','level','complexity','src'))
            if not isinstance(identity, str) or not identity or identity in seen:
                raise ValueError(f'Missing or repeated BigO ID in {path}')
            if type(level) is not int or level < 1 or label not in COMPLEXITY_LABELS:
                raise ValueError(f'Invalid level or complexity label for {identity}')
            if not isinstance(source, str) or not source.strip():
                raise ValueError(f'Missing Python source for {identity}')
            compile(source, identity, 'exec')
            seen.add(identity)
            task_id = 'original-bigo:' + identity
            public.append({'task_id':task_id,'files':{'composed.py':source},
                           'question':'Classify the time complexity of composed(x) in terms of the numeric input magnitude. '
                           'Reply with exactly one label: constant, logn, linear, nlogn, quadratic, cubic, or np.'})
            judge.append({'task_id':task_id,'level':level,'label':label,'source_task_id':identity,
                          'source_sha256':hashlib.sha256(source.encode('utf-8')).hexdigest()})
    output.mkdir(parents=True)
    write_rows(output / 'model_inputs/bigo.jsonl', public)
    write_rows(output / 'judge/bigo.jsonl', judge)
    return {'tasks':len(public),'counts_by_level':dict(sorted(Counter(row['level'] for row in judge).items())),
            'inputs':source_hashes,'historical_model_results_bound':False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest='command', required=True)
    repair = subcommands.add_parser('rebuild-repair')
    repair.add_argument('--published',type=Path,required=True)
    clone = subcommands.add_parser('import-clone')
    clone.add_argument('--input',type=Path,nargs='+',required=True)
    render = subcommands.add_parser('render-clone')
    render.add_argument('--database',type=Path,required=True)
    render.add_argument('--positive',type=Path,required=True)
    render.add_argument('--negative',type=Path,required=True)
    render.add_argument('--level',type=int,choices=range(2,11),required=True)
    verus = subcommands.add_parser('import-verus')
    verus.add_argument('--source',type=Path,required=True,help='Extracted verus_composition directory')
    bigo = subcommands.add_parser('import-bigo')
    bigo.add_argument('--input',type=Path,nargs='+',required=True)
    for command in (repair,clone,render,verus,bigo):
        command.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists():
        parser.error('Choose a new output directory')
    if args.command == 'rebuild-repair':
        result = rebuild_repair(args.published.resolve(),output)
    elif args.command == 'render-clone':
        result = render_clone(args.database,args.positive,args.negative,args.level,output)
    elif args.command == 'import-verus':
        result = import_verus(args.source.resolve(),output)
    elif args.command == 'import-bigo':
        result = import_bigo(args.input,output)
    else:
        result = import_clone(args.input,output)
    summary = json.dumps(result,indent=2) + '\n'
    (output / 'integration-receipt.json').write_text(summary,encoding='utf-8')
    print(summary,end='')


if __name__ == '__main__':
    main()
