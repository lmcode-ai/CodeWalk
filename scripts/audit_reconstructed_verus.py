"""Additional typechecks of every curated Verus input; proof admission remains separate."""
import concurrent.futures
import hashlib
import json
from pathlib import Path
import sys
import zipfile
import argparse
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from codewalk.composition.base import Runner


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--config',default=str(ROOT/'outputs/verus-config.json'))
    parser.add_argument('--root',default=str(ROOT/'outputs/reconstructed-benchmark'))
    args=parser.parse_args();root=Path(args.root).resolve();checks=ROOT/'outputs/reconstruction-typechecks'
    config=json.loads(Path(args.config).read_text(encoding='utf-8'))
    records=[json.loads(l) for l in (root/'model_inputs/verus.jsonl').read_text(encoding='utf-8').splitlines()]
    def check(row):
        work=checks/row['task_id'];work.mkdir(parents=True,exist_ok=True)
        (work/'task.rs').write_text(row['files']['task.rs'],encoding='utf-8',newline='\n')
        result=Runner(config).run([config['verus'],'--no-verify','task.rs'],work,name='well-formedness-typecheck-only')
        (work/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        return {'task_id':row['task_id'],'returncode':result['returncode']}
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:results=list(pool.map(check,records))
    failures=[r for r in results if r['returncode']!=0]
    if failures:raise SystemExit('Typecheck failures: '+json.dumps(failures))
    report={'tasks':len(results),'typecheck_passed':len(results),
            'note':'--no-verify checks well-formedness only; actual proof reference/unfinished admission is recorded separately.'}
    (root/'judge/verus-additional-typechecks.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    files=sorted(p for p in root.rglob('*') if p.is_file() and p.name!='SHA256SUMS')
    (root/'SHA256SUMS').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.relative_to(root).as_posix()+'\n' for p in files),encoding='utf-8')
    target=ROOT/'outputs/source-reconstructed-benchmark.zip'
    with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(p for p in root.rglob('*') if p.is_file()):archive.write(path,'source-reconstructed-benchmark/'+path.relative_to(root).as_posix())
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
