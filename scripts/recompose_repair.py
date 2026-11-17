"""Enumerate and actually admit small real-source repair groups from recovered atoms."""
import itertools
import json
from pathlib import Path
import sys
import argparse
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from codewalk.composition import generate
from codewalk.composition.repair import RepairBackend
from codewalk.data import read_jsonl


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',default=str(ROOT/'outputs/source-derived-datasets/bugfixing-v2'))
    args=parser.parse_args();out=Path(args.output);out.mkdir(parents=True,exist_ok=True)
    summary={'source':'Original HF bug patches/test IDs and original Git commits; local native pytest admission',
             'accepted':[],'excluded':[]}
    for repo_index,source in enumerate(sorted((ROOT/'outputs/source-recovery/repair').glob('*/atoms.jsonl'))):
        pool=read_jsonl(source)
        for atom in pool:
            atom['payload']['interaction_files']=[p for p in atom['payload']['modified_files'] if p.endswith('.py')]
        for level in (1,2,3):
            for number,group in enumerate(itertools.combinations(pool,level)):
                case=f'r{repo_index}-L{level}-{number:03d}'
                target=out/case
                if (target/'manifest.json').exists():report=json.loads((target/'manifest.json').read_text(encoding='utf-8'))
                else:
                    try:report=generate('bugfixing',list(group),target,level=level,max_candidates=1,config={'timeout_seconds':45})
                    except Exception as exc:
                        summary['excluded'].append({'case':case,'error':str(exc)});continue
                if report['complete']:
                    summary['accepted'].append({'case':case,'level':level,'tasks':report['accepted']})
                    print(json.dumps({'accepted':len(summary['accepted']),'case':case}),flush=True)
                else:summary['excluded'].append({'case':case,'blocked':report['blocked'],'rejected':report['rejected']})
                (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8')
    (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'accepted':len(summary['accepted']),'excluded':len(summary['excluded'])}))


if __name__=='__main__':main()
