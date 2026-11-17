"""Generate CodeComplex-source chains from the conservative recovered atomic subset."""
import json
from pathlib import Path
import sys
import argparse
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from codewalk.composition import generate
from codewalk.data import read_jsonl


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',default=str(ROOT/'outputs/source-derived-datasets/bigo'))
    p.add_argument('--atoms',default=str(ROOT/'outputs/source-recovery/bigo/atoms.jsonl'))
    p.add_argument('--counts',help='Per-level counts, e.g. 1:80,2:80,3:80,10:80')
    p.add_argument('--max-per-source',type=int)
    p.add_argument('--profile',choices=('paper','reconstruction'),default='paper')
    args=p.parse_args()
    atoms=read_jsonl(args.atoms)
    if args.profile=='paper':
        if len(atoms)!=277 or len({a['source_id'] for a in atoms})!=277:
            p.error('Paper generation requires the declared 277-atom, one-snippet-per-problem pool. The recovered smaller/function-variant pool is reconstruction-only.')
    root=Path(args.output);root.mkdir(parents=True,exist_ok=True)
    summary={'source_atoms':len(atoms),'historical_pool_reproduced':False,'levels':{}}
    counts=[tuple(map(int,item.split(':'))) for item in args.counts.split(',')] if args.counts else (((1,80),(2,80),(3,80),(10,80)) if args.profile=='paper' else ((1,len(atoms)),(2,80),(3,80),(10,10)))
    for level,count in counts:
        report=generate('bigo',atoms,root/f'L{level}',level=level,count=count,seed=20261106+level,
                        max_candidates=5000,config={'timeout_seconds':10,
                            'require_nontrivial_composition':args.profile=='paper'},max_per_source=args.max_per_source)
        summary['levels'][str(level)]={'complete':report['complete'],'accepted':len(report['accepted']),
            'blocked':report['blocked'],'rejected':len(report['rejected'])}
        (root/'summary.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8')
        print(json.dumps({'level':level,**summary['levels'][str(level)]}),flush=True)


if __name__=='__main__':main()
