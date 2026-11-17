"""Match actual unfinished Verus L1 sources to recovered verified upstream functions."""
import argparse
import concurrent.futures
import contextlib
import hashlib
import json
from pathlib import Path
import sys
import zipfile
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from codewalk.recovery.rust import *
from codewalk.composition.base import Runner
from codewalk.composition.rust_source import SourceVerusBackend


def main():
    p=argparse.ArgumentParser();p.add_argument('--config',required=True);p.add_argument('--archive')
    p.add_argument('--source-root',default=str(ROOT/'data/verus'),help='Downloaded source root when no ZIP is supplied')
    p.add_argument('--output',default=str(ROOT/'outputs/source-recovery/verus'))
    p.add_argument('--standalone',action='store_true',help='Preserve original standalone L1 wrappers, including non-chainable types')
    args=p.parse_args();config=json.loads(Path(args.config).read_text());config.update({'verus_mode':'source_recovered','timeout_seconds':30})
    out=Path(args.output).resolve();out.mkdir(parents=True,exist_ok=True)
    manifest=json.loads((ROOT/'data/verus/manifest.json').read_text(encoding='utf-8'))
    receipts=json.loads((ROOT/'outputs/source-recovery/upstream/receipts.json').read_text(encoding='utf-8'))
    revision=next(r['revision'] for r in receipts if r['repo']=='microsoft/verus-proof-synthesis')
    sources={p.name:p for p in (ROOT/'outputs/source-recovery/upstream/verus-proof-synthesis').rglob('*.rs')}
    candidates=[];excluded=[]
    with zipfile.ZipFile(args.archive) if args.archive else contextlib.nullcontext(None) as archive:
        prefix=next(n[:-len('manifest.json')] for n in archive.namelist() if n.endswith('/manifest.json')) if archive else ''
        for row in (r for r in manifest['tasks'] if r['level']==1):
            try:
                data=archive.read(prefix+row['file']) if archive else (Path(args.source_root)/row['file']).read_bytes()
                if hashlib.sha256(data).hexdigest()!=row['sha256']:raise ValueError('Task hash mismatch')
                task=verus_body(data.decode());original=functions(task)
                mapping={name:name[3:] for name in original if name.startswith('f1_')}
                task=replace_names(task,mapping);task_functions=functions(task)
                filename=row['source_programs'][0];reference=verus_body(sources[filename].read_text(encoding='utf-8'))
                adjustments=[]
                if row['id'] in ('S1_019','S1_027'):
                    # Newer Verus loop isolation needs the unchanged input bound
                    # restated as an invariant. Only proof annotations are added.
                    marker='invariant\n            1 <= index <= arr.len(),'
                    bound='forall|i: int| 0 <= i < arr.len() ==> i32::MIN / 2 < #[trigger] arr[i] < i32::MAX / 2,'
                    if marker not in reference or bound not in reference:raise ValueError('Expected audited loop-bound pattern absent')
                    reference=reference.replace(marker,marker+'\n            '+bound,1)
                    adjustments.append('Restated existing immutable input bound as a loop invariant for current Verus loop isolation')
                reference_functions=functions(reference);name=row['component_functions'][0]
                if executable_projection(task_functions[name]['body'])!=executable_projection(reference_functions[name]['body']):
                    raise ValueError('Executable token projection differs; no assumed equivalence')
                reference+='\n'+''.join(task[f['start']:f['end']]+'\n' for f in (task_functions['step1'],task_functions['chain_driver']))
                atom={'schema_version':1,'domain':'verus','id':row['id'],'source_id':filename,
                    'provenance':{'uri':'https://github.com/microsoft/verus-proof-synthesis','revision':revision,'license':'MIT',
                        'published_task_sha256':row['sha256'],'original_file':row['file']},
                    'payload':{'mode':'source_recovered','reference_body':reference,'task_body':task,
                        'executable_tokens_match':True,'standalone_only':args.standalone,
                        'contract':None if args.standalone else contract(task_functions['chain_driver'])}}
                atom['provenance']['reference_adjustments']=adjustments
                SourceVerusBackend(config).validate(atom);candidates.append(atom)
            except Exception as exc:excluded.append({'id':row['id'],'reason':str(exc)})
    validated=[]
    def check(atom):
        target=out/'atoms'/f'{atom["id"]}.json'
        if target.exists():return json.loads(target.read_text(encoding='utf-8'))
        backend=SourceVerusBackend(config);work=out/'checks'/atom['id'];work.mkdir(parents=True,exist_ok=True)
        runner=Runner(config);built=backend.render([atom],work)
        try:evidence=backend.admit(built,runner)
        finally:(work/'execution.json').write_text(json.dumps(runner.records,indent=2),encoding='utf-8')
        atom['recovery']={'admission':evidence,'source_kind':'real upstream proof + surviving unfinished source','historical_reference_exact':False}
        target.parent.mkdir(parents=True,exist_ok=True);target.write_text(json.dumps(atom,indent=2)+'\n',encoding='utf-8');return atom
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        futures={pool.submit(check,a):a['id'] for a in candidates}
        for f in concurrent.futures.as_completed(futures):
            try:validated.append(f.result())
            except Exception as exc:excluded.append({'id':futures[f],'reason':str(exc)})
            print(json.dumps({'validated':len(validated),'excluded':len(excluded)}),flush=True)
    validated.sort(key=lambda a:a['id'])
    (out/'atoms.jsonl').write_text(''.join(json.dumps(a)+'\n' for a in validated),encoding='utf-8')
    summary={'surviving_L1_tasks':100,'source_matched_candidates':len(candidates),'validated_atoms':len(validated),'excluded':excluded}
    (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8')


if __name__=='__main__':main()
