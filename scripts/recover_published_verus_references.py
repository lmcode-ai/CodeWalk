"""Recover and optionally verify references for exact published task bytes and original component groups."""
import argparse
from collections import Counter
import concurrent.futures
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from codewalk.data import read_jsonl
from codewalk.recovery.rust import verus_body
from codewalk.recovery.published_verus import recover_reference
from codewalk.composition.base import Runner
from codewalk.composition.rust_source import SourceVerusBackend
from codewalk.composition.rust_proof import BYPASS


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True)
    parser.add_argument('--manifest',default=str(ROOT/'data/verus/manifest.json'))
    parser.add_argument('--tasks',default=str(ROOT/'outputs/canonical-originals/verus'))
    parser.add_argument('--atoms',default=str(ROOT/'outputs/source-recovery/verus-paper-l1/atoms.jsonl'))
    parser.add_argument('--upstream',default=str(ROOT/'outputs/source-recovery/upstream/verus-proof-synthesis'))
    parser.add_argument('--config',help='When supplied, actually verify each reference and unchanged unfinished input')
    parser.add_argument('--per-level',type=int,help='Explicit smoke subset per level; never described as the full bank')
    args=parser.parse_args();out=Path(args.output).resolve()
    if out.exists():raise ValueError('Preserve earlier recovery runs; choose a new output directory')
    out.mkdir(parents=True)
    manifest=json.loads(Path(args.manifest).read_text());originals=manifest['tasks']
    l1={r['id']:r for r in originals if r['level']==1}
    sources={(l1[a['id']]['source_programs'][0],l1[a['id']]['component_functions'][0]):a['payload']['reference_body']
             for a in read_jsonl(args.atoms)}
    upstream={p.name:p for p in Path(args.upstream).rglob('*.rs')}
    config=json.loads(Path(args.config).read_text()) if args.config else None
    if config:
        version=Runner(config).run([config.get('verus','verus'),'--version'],out,name='toolchain-version')
        if version['returncode']!=0:raise ValueError('Verifier unavailable')
        (out/'toolchain.json').write_text(json.dumps(version,indent=2)+'\n')
    if args.per_level is not None:
        if args.per_level<1:raise ValueError('Smoke sample must be positive')
        selected=[r for level in (1,2,3,10) for r in [x for x in originals if x['level']==level][:args.per_level]]
    else:selected=originals

    def recover(row):
        work=out/row['id'];work.mkdir()
        result={'task_id':row['id'],'level':row['level'],'original_sha256':row['sha256'],
                'source_matches_hf':False,'reference_verifies':False,'unfinished_well_formed':False,
                'unfinished_fails_proof':False,'admitted':False}
        runner=Runner(config) if config else None
        try:
            raw=(Path(args.tasks)/row['file']).read_bytes()
            if hashlib.sha256(raw).hexdigest()!=row['sha256']:raise ValueError('Original task bytes differ from HF manifest')
            result['source_matches_hf']=True
            components=[]
            for s,f in zip(row['source_programs'],row['component_functions']):
                components.append(sources[s,f] if (s,f) in sources else verus_body(upstream[s].read_text()))
            reference,evidence=recover_reference(raw.decode('utf-8'),components)
            if BYPASS.search(reference):raise ValueError('Reference contains an unsupported proof-bypass token')
            (work/'task.rs').write_bytes(raw);(work/'reference.rs').write_text(reference,encoding='utf-8',newline='\n')
            result['structural_evidence']=evidence
            result['reference_sha256']=hashlib.sha256((work/'reference.rs').read_bytes()).hexdigest()
            if config:
                backend=SourceVerusBackend(config)
                try:
                    verified=backend.verify(runner,work,'reference.rs');result['reference_verification']=verified
                    result['reference_verifies']=verified['errors']==0
                    result['structural_evidence']['reference_verified']=result['reference_verifies']
                except Exception as exc:result['reference_error']=str(exc)
                try:
                    unfinished=backend.verify(runner,work,'task.rs');result['unfinished_verification']=unfinished
                    result['unfinished_well_formed']=True;result['unfinished_fails_proof']=unfinished['errors']>0
                except Exception as exc:result['unfinished_error']=str(exc)
                result['admitted']=result['reference_verifies'] and result['unfinished_well_formed'] and result['unfinished_fails_proof']
        except Exception as exc:result['recovery_error']=str(exc)
        finally:
            if runner:(work/'execution.json').write_text(json.dumps(runner.records,indent=2)+'\n')
            (work/'result.json').write_text(json.dumps(result,indent=2)+'\n')
        return result

    results=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        for result in pool.map(recover,selected):
            results.append(result)
            if len(results)%20==0:print(json.dumps({'checked':len(results),'admitted':sum(r['admitted'] for r in results)}),flush=True)
    report={'original_bank_tasks':len(originals),'selected_tasks':len(selected),'full_bank':args.per_level is None,
        'actual_verification_performed':bool(config),'source_hashes_match':sum(r['source_matches_hf'] for r in results),
        'references_verified':sum(r['reference_verifies'] for r in results),
        'unchanged_public_inputs_well_formed':sum(r['unfinished_well_formed'] for r in results),
        'admitted':sum(r['admitted'] for r in results),'counts_by_level':dict(Counter(str(r['level']) for r in results)),
        'all_public_inputs_unchanged':all(r['source_matches_hf'] for r in results),'results':results,
        'historical_model_results_bound':False}
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='results'},indent=2),flush=True)


if __name__=='__main__':main()
