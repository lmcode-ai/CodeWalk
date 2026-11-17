"""Recover actual repair atoms and referenced Git bases from the surviving HF release."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import urllib.request

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from codewalk.composition.repair import patch_files


def main():
    p=argparse.ArgumentParser();p.add_argument('--repo',default='horejsek/python-fastjsonschema')
    args=p.parse_args()
    rows=[json.loads(l) for l in (ROOT/'data/bugfixing/data/test.jsonl').read_text(encoding='utf-8').splitlines()]
    selected=[r for r in rows if r['repo']==args.repo]
    out=ROOT/'outputs/source-recovery/repair'/args.repo.replace('/','__');out.mkdir(parents=True,exist_ok=True)
    repo=out/'repository';repo.mkdir(exist_ok=True)
    env=dict(os.environ,GIT_TERMINAL_PROMPT='0')
    def git(*argv):
        result=subprocess.run(['git','-C',str(repo),'-c','credential.helper=',*argv],env=env,capture_output=True,text=True,timeout=120)
        if result.returncode:raise RuntimeError(result.stderr)
        return result.stdout.strip()
    if not (repo/'.git').exists():git('init','--quiet')
    unique={b['instance_id']:b for r in selected for b in r['bugs']}
    for base in sorted({b['base_commit'] for b in unique.values()}|{r['base_commit'] for r in selected}):
        exists=subprocess.run(['git','-C',str(repo),'cat-file','-e',base],capture_output=True).returncode==0
        if not exists:git('fetch','--quiet','--depth=1','https://github.com/'+args.repo+'.git',base)
    atoms=[];missing=[]
    for key,b in unique.items():
        number=key.rsplit('-',1)[1]
        metadata=out/f'pull-{number}.json'
        try:
            if metadata.exists():pull=json.loads(metadata.read_text(encoding='utf-8'))
            else:
                req=urllib.request.Request(f'https://api.github.com/repos/{args.repo}/pulls/{number}',headers={'User-Agent':'CodeWalk-source-recovery'})
                with urllib.request.urlopen(req,timeout=30) as response:pull=json.load(response)
                metadata.write_text(json.dumps(pull,indent=2),encoding='utf-8')
            fixed=pull.get('merged_at')
            if not fixed:raise ValueError('No actual merged_at timestamp')
            time_source='GitHub pull request merged_at'
            time_field={'fix_time':fixed}
        except Exception as exc:
            # Do not fabricate a fixing date. Actual base-commit time proposes a
            # candidate snapshot only; real G1/G2 must still establish coexistence.
            time_field={'base_time':git('show','-s','--format=%cI',b['base_commit'])}
            time_source='Actual base-commit timestamp; fixing date unavailable: '+str(exc)
        try:
            paths=sorted(patch_files(b['gold_patch']))
            atoms.append({'schema_version':1,'domain':'bugfixing','id':key,'source_id':args.repo,
                'provenance':{'uri':'https://github.com/'+args.repo,'revision':b['base_commit'],
                    'license':'see original repository license retained in generated repository',
                    'public_dataset':'CodeWalk/multi-bug-repair','timestamp_source':time_source},
                'payload':{'repository':str(repo),'base_commit':b['base_commit'],**time_field,
                    'gold_patch':b['gold_patch'],'test_patch':b['test_patch'],'modified_files':paths,'test_ids':b['FAIL_TO_PASS']}})
        except Exception as exc:missing.append({'id':key,'error':str(exc)})
    (out/'atoms.jsonl').write_text(''.join(json.dumps(a)+'\n' for a in atoms),encoding='utf-8')
    report={'repository':args.repo,'recovered_atoms':len(atoms),'errors':missing,'surviving_tasks':len(selected)}
    (out/'summary.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report,indent=2))


if __name__=='__main__':main()
