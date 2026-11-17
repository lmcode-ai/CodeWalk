"""Generate source-recovered Verus chains at multiple depths, preserving final returns."""
import argparse
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from codewalk.composition import generate
from codewalk.data import read_jsonl


def main():
    p=argparse.ArgumentParser();p.add_argument('--config',required=True);p.add_argument('--output',required=True)
    p.add_argument('--counts',default='1:87,2:25,3:25,10:10')
    p.add_argument('--conservative',action='store_true')
    p.add_argument('--atoms',default=str(ROOT/'outputs/source-recovery/verus/atoms.jsonl'))
    p.add_argument('--max-candidates',type=int,default=1000)
    args=p.parse_args();config=json.loads(Path(args.config).read_text());config.update({'verus_mode':'source_recovered','timeout_seconds':45})
    atoms=read_jsonl(args.atoms)
    if args.conservative:
        config.update({'conservative_bindings':True,'path_lookahead':True})
        atoms=[a for a in atoms if a['payload']['contract']['output_type']=='Vec<i32>' or
               any(t in ('Vec<i32>','&Vec<i32>','&[i32]') for _,t in a['payload']['contract']['parameters'])]
    root=Path(args.output);root.mkdir(parents=True,exist_ok=True);summary={'source_atoms':len(atoms),'levels':{}}
    for item in args.counts.split(','):
        level,count=map(int,item.split(':'))
        report=generate('verus',atoms,root/f'L{level}',level=level,count=count,seed=20261106+level,
                        max_candidates=args.max_candidates,config=config,max_per_source=2 if level==10 else None)
        summary['levels'][str(level)]={'complete':report['complete'],'accepted':len(report['accepted']),
            'blocked':report['blocked'],'rejected':len(report['rejected'])}
        (root/'summary.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8')
        print(json.dumps({'level':level,**summary['levels'][str(level)]}),flush=True)
        if not report['complete']:print('Requested quota not met; partial artifacts remain explicitly marked.',flush=True)


if __name__=='__main__':main()
