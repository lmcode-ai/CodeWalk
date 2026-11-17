"""Exercise available CLI workflows; never equate fixture scoring with model evaluation."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from codewalk import data
from codewalk.evaluation import COMPLEXITY_LABELS


def write(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(''.join(json.dumps(row) + '\n' for row in rows), encoding='utf-8')


def cli(*args, success=True):
    result = subprocess.run([sys.executable, '-m', 'codewalk', *map(str, args)],
                            cwd=ROOT, capture_output=True, text=True)
    if (result.returncode == 0) != success:
        raise RuntimeError(f"Unexpected CLI outcome: {args}: {result.stderr}")
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--verus-archive', type=Path)
    args = parser.parse_args()
    out = ROOT / 'outputs/workflow-verification'
    out.mkdir(parents=True, exist_ok=True)
    report = {'scope': 'local integration checks; no inference or domain semantic admission',
              'checked_at': '2026-11-06',
              'tool_executables': {name: shutil.which(name) for name in ('java','javac','verus','docker')},
              'datasets': {}, 'composition': {}, 'classification': {}}
    for domain in ('bugfixing','codeclone','verus'):
        spec = data.registry()[domain]
        receipt = json.loads((ROOT/'data'/domain/'download_receipt.json').read_text())
        if receipt['revision'] != spec['revision'] or receipt['repo_id'] != spec['repo_id']:
            raise RuntimeError('Dataset receipt revision mismatch')
        for relative, details in receipt['files'].items():
            content = data.safe_path(ROOT/'data'/domain, relative).read_bytes()
            if len(content) != details['bytes'] or hashlib.sha256(content).hexdigest() != details['sha256']:
                raise RuntimeError('Downloaded artifact integrity failure')
        cli('inspect', domain, '--root', ROOT/'data'/domain, '--output', out/f'{domain}-inspection.json')
        report['datasets'][domain] = json.loads((out/f'{domain}-inspection.json').read_text())
    for domain in ('bugfixing','codeclone'):
        destination = out/f'{domain}-public.jsonl'
        cli('export-inputs', domain, '--root', ROOT/'data'/domain, '--output', destination)
        rows = data.read_jsonl(destination)
        forbidden = {'level','label','gold_patch','bugs','component_pairids','base_commit','repo'}
        if any(forbidden.intersection(row) for row in rows):
            raise RuntimeError('Judge or environment metadata leaked into public fields')
        report['datasets'][domain]['exported_inputs'] = len(rows)
    if args.verus_archive:
        manifest = data.records('verus', ROOT/'data/verus')
        cache = out/'verus-source-cache'
        with zipfile.ZipFile(args.verus_archive) as archive:
            candidates = [n for n in archive.namelist() if n.endswith('/manifest.json') or n == 'manifest.json']
            if len(candidates) != 1:
                raise RuntimeError('Ambiguous ZIP layout')
            prefix = candidates[0][:-len('manifest.json')]
            for task in manifest:
                content = archive.read(prefix + task['file'])
                if hashlib.sha256(content).hexdigest() != task['sha256']:
                    raise RuntimeError('Archive does not match pinned manifest')
                target = data.safe_path(cache, task['file'])
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content)
        (cache/'manifest.json').write_bytes((ROOT/'data/verus/manifest.json').read_bytes())
        cli('export-inputs','verus','--root',cache,'--output',out/'verus-public.jsonl')
        report['datasets']['verus']['exported_hash_verified_inputs'] = len(data.read_jsonl(out/'verus-public.jsonl'))
    clone = data.records('codeclone', ROOT/'data/codeclone')
    tasks = [{'task_id':r['id'],'level':r['level'],'label':r['label']} for r in clone]
    write(out/'clone-judge.jsonl', tasks)
    for case in ('reference_echo','opposite','malformed'):
        rows = []
        for task in tasks:
            bit = int(task['label'] == 'equivalent')
            response = ('VERDICT: '+str(bit if case == 'reference_echo' else 1-bit)
                        if case != 'malformed' else 'no valid verdict')
            rows.append({'task_id':task['task_id'],'sample_idx':0,'response':response})
        write(out/f'clone-{case}-responses.jsonl',rows)
        cli('grade-labels','codeclone','--tasks',out/'clone-judge.jsonl',
            '--responses',out/f'clone-{case}-responses.jsonl','--output',out/f'clone-{case}-attempts.jsonl')
        cli('score','--tasks',out/'clone-judge.jsonl','--attempts',out/f'clone-{case}-attempts.jsonl',
            '--n',1,'--output',out/f'clone-{case}-score.json')
        result = json.loads((out/f'clone-{case}-score.json').read_text())['overall']
        expected = 1.0 if case == 'reference_echo' else 0.0
        if result['pass_at_1'] != expected or not result['complete']:
            raise RuntimeError('Classification control failed')
        report['classification'][case] = {'tasks':len(tasks),'control_pass_rate':expected,
            'note':'synthetic control responses, NOT a model benchmark result'}
    labels = sorted(COMPLEXITY_LABELS)
    write(out/'bigo-judge.jsonl',[{'task_id':f'fixture-{l}','level':1,'label':l} for l in labels])
    write(out/'bigo-responses.jsonl',[{'task_id':f'fixture-{l}','sample_idx':0,'response':l} for l in labels])
    cli('grade-labels','bigo','--tasks',out/'bigo-judge.jsonl','--responses',out/'bigo-responses.jsonl',
        '--output',out/'bigo-attempts.jsonl')
    if not all(r['status']=='success' for r in data.read_jsonl(out/'bigo-attempts.jsonl')):
        raise RuntimeError('Complexity label controls failed')
    report['classification']['bigo'] = 'all 7 label controls passed; no real dataset available'
    rejected = []
    for domain in ('bugfixing','verus','bigo','codeclone'):
        atoms = []
        for i in range(10):
            atom = {'id':f'a{i:02d}','source_id':f's{i}',
                    'input_type':f'T{i}','accepted_input_types':[f'T{i}'],'output_type':f'T{i+1}',
                    'label':'equivalent','size_transfer':'identity','cost':'linear',
                    'repo':'synthetic/repo','modified_files':['shared.py'],
                    'fix_time':f'2026-01-{i+1:02d}T00:00:00Z','base_commit':f'fixture-base-{i}',
                    'FAIL_TO_PASS':[f'test_{i}']}
            atoms.append(atom)
        write(out/f'{domain}-atoms.jsonl',atoms)
        for level in (1,2,3,10):
            target = out/f'{domain}-L{level}-plan.json'
            cli('plan',domain,'--atoms',out/f'{domain}-atoms.jsonl','--level',level,'--seed',42,'--output',target)
            plan = json.loads(target.read_text())['plans'][0]
            if plan['level'] != level or plan['admitted'] is not False or plan['status'] != 'candidate_only':
                raise RuntimeError('Candidate status or level incorrect')
        report['composition'][domain] = {'candidate_plan_levels':[1,2,3,10],
            'input':'synthetic normalized atoms','executable_task_generated':False,'semantic_admission_run':False}
        invalid = [dict(a) for a in atoms[:2]]
        if domain == 'bugfixing':
            invalid[1]['repo'] = 'different/repo'
            reason = 'cross-repository disconnected repair group'
        elif domain == 'bigo':
            invalid[0].pop('size_transfer')
            reason = 'missing intermediate size-transfer metadata'
        elif domain == 'codeclone':
            for atom in invalid:
                atom['label'] = 'not_equivalent'
            reason = 'more than one negative atom'
        else:
            for atom in invalid:
                atom['accepted_input_types'] = ['not-compatible']
            reason = 'incompatible directed chain'
        write(out/f'{domain}-invalid-atoms.jsonl',invalid)
        cli('plan',domain,'--atoms',out/f'{domain}-invalid-atoms.jsonl','--level',2,
            '--max-attempts',30,'--output',out/f'{domain}-invalid-plan.json',success=False)
        rejected.append(reason)
    cli('download','bigo','--destination',out/'missing-dataset-control',success=False)
    rejected.append('unconfigured complexity download')
    clone_attempts = data.read_jsonl(out/'clone-reference_echo-attempts.jsonl')
    for case, attempts in (
        ('duplicate', clone_attempts+[clone_attempts[0]]),
        ('unknown', [{**clone_attempts[0], 'task_id':'unknown-task'}])):
        write(out/f'{case}-attempts.jsonl',attempts)
        cli('score','--tasks',out/'clone-judge.jsonl','--attempts',out/f'{case}-attempts.jsonl',
            '--n',1,'--output',out/f'{case}-score.json',success=False)
        rejected.append(case+' attempt identity')
    for case, attempts in (
        ('missing',clone_attempts[:-1]),
        ('infra',clone_attempts[:-1]+[{**clone_attempts[-1],'status':'infra_error'}])):
        write(out/f'{case}-attempts.jsonl',attempts)
        cli('score','--tasks',out/'clone-judge.jsonl','--attempts',out/f'{case}-attempts.jsonl',
            '--n',1,'--output',out/f'{case}-score.json')
        score = json.loads((out/f'{case}-score.json').read_text())['overall']
        if score['complete'] or score['pass_at_1'] is not None:
            raise RuntimeError('Incomplete run incorrectly scored as complete')
        rejected.append(case+' results withheld from complete aggregate')
    report['failure_controls_passed'] = rejected
    report['blockers'] = {
        'bugfixing':['historical environment/test-runner adapters absent','repair agent runner absent'],
        'verus':['gold-preserving grader absent','reference proofs absent','Verus toolchain absent locally'],
        'bigo':['historical dataset absent','upstream cost annotations/atomic extraction not recovered'],
        'codeclone':['inference runner absent','historical atomic suites/normalization not recovered'],
        'all_domains':['original atom extractors absent',
                       'this script tests old candidate planning; use verify_generators.py for executable composition']}
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,indent=2))


if __name__ == '__main__':
    main()
