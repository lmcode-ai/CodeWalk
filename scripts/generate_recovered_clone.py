"""Generate balanced real-source aggregation banks, retaining admission and provenance."""
import argparse
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from codewalk.composition import generate
from codewalk.data import read_jsonl


def main():
    p=argparse.ArgumentParser();p.add_argument('--config',required=True);p.add_argument('--output',required=True)
    p.add_argument('--count',type=int,default=100);p.add_argument('--levels',type=int,nargs='+',default=[1,2,3])
    p.add_argument('--counts',help='Per-level quotas, e.g. 1:86,2:82,3:84,10:166')
    p.add_argument('--mode',choices=('aggregation','chain'),default='aggregation')
    p.add_argument('--loop-free',action='store_true',help='Restrict deep chains to real methods without explicit loops; report this selection bias')
    p.add_argument('--seed',type=int,default=20261106)
    p.add_argument('--label',choices=('equivalent','not_equivalent'),help='Generate one class shard; final curation must restore paper class balance')
    args=p.parse_args()
    atoms=read_jsonl(ROOT/'outputs/source-recovery/clone/atoms.jsonl')
    if args.loop_free:
        import re
        atoms=[a for a in atoms if not re.search(r'\b(for|while|do)\b',a['payload']['a_members']+'\n'+a['payload']['b_members'])]
    if args.label=='equivalent':atoms=[a for a in atoms if a['payload']['label']=='equivalent']
    config=json.loads(Path(args.config).read_text());config.update({'clone_mode':args.mode,'timeout_seconds':30})
    counts=dict(tuple(map(int,item.split(':'))) for item in args.counts.split(',')) if args.counts else dict.fromkeys(args.levels,args.count)
    root=Path(args.output);root.mkdir(parents=True,exist_ok=True)
    summary={'source_atoms':len(atoms),'source':'Actual FEMPD methods selected by surviving HF component IDs',
             'historical_suite_reproduced':False,'levels':{}}
    for level,count in counts.items():
        quotas={args.label:count} if args.label else {'equivalent':count//2,'not_equivalent':count-count//2}
        level_config={**config,'label_quotas':quotas}
        # Sampling one large pool constructs the graph once rather than rebuilding
        # it before every candidate. Explicit plans still undergo full admission.
        from codewalk.graph import sample_groups
        from codewalk.composition.java_clone import CloneBackend
        import random
        if level==1:
            shuffled=list(atoms);random.Random(args.seed).shuffle(shuffled)
            groups=[[a['id']] for a in shuffled if not args.label or a['payload']['label']==args.label]
        elif args.label=='not_equivalent':
            backend=CloneBackend(level_config)
            positive=[a for a in atoms if a['payload']['label']=='equivalent']
            negative=[a for a in atoms if a['payload']['label']=='not_equivalent']
            prefix_count=len(positive) if level==2 else 3000
            prefixes=sample_groups(positive,backend.compatible,level=level-1,count=prefix_count,
                seed=args.seed+level,directed=backend.directed,max_attempts=100000)
            groups=[[a['id'] for a in prefix]+[last['id']] for prefix in prefixes for last in negative
                    if backend.compatible(prefix[-1],last)]
            random.Random(args.seed).shuffle(groups)
            groups=groups[:6000]
        else:
            backend=CloneBackend(level_config)
            candidates=sample_groups(atoms,backend.compatible,level=level,count=3000,seed=args.seed+level,
                                     directed=backend.directed,max_attempts=100000,lookahead=False)
            groups=[[a['id'] for a in group] for group in candidates
                    if sum(a['payload']['label']=='not_equivalent' for a in group)<=1]
        report=generate('codeclone',atoms,root/f'L{level}',level=level,count=count,seed=args.seed+level,
                        max_candidates=len(groups),config=level_config,groups=groups)
        summary['levels'][str(level)]={'complete':report['complete'],'accepted':len(report['accepted']),
            'rejected':len(report['rejected']),'blocked':report['blocked']}
        (root/'summary.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8')
        print(json.dumps({'level':level,**summary['levels'][str(level)]}),flush=True)
        if not report['complete']:raise SystemExit(2)


if __name__=='__main__':main()
