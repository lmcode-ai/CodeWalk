"""Preserve admissible original groups first; fill only missing slots with real-source groups."""
from collections import Counter
import json
from pathlib import Path
import random
import argparse
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from codewalk.composition import generate
from codewalk.data import read_jsonl
from codewalk.composition.java_clone import stochastic_source


def main():
    p=argparse.ArgumentParser();p.add_argument('--config',required=True);p.add_argument('--output',required=True)
    args=p.parse_args();root=Path(args.output);root.mkdir(parents=True,exist_ok=True)
    atoms=[a for a in read_jsonl(ROOT/'outputs/source-recovery/clone/atoms.jsonl') if not stochastic_source(a['payload']['a_members']+'\n'+a['payload']['b_members'])]
    bank={a['id']:a for a in atoms}
    config=json.loads(Path(args.config).read_text());config.update({'timeout_seconds':30,'clone_mode':'aggregation',
        'label_quotas':{'equivalent':50,'not_equivalent':50}})
    rng=random.Random(20261106);usage=Counter();summary={'policy':'original admissible component groups first; coverage-aware real-source fill',
        'source_atoms':len(atoms),'levels':{}}
    for level in (1,2,3):
        original=json.loads((ROOT/f'data/codeclone/data/level_{level}.json').read_text(encoding='utf-8'))
        plans=[];seen=set();quota=Counter()
        for row in original:
            ids=[f'fempd-{i}' for i in row['component_pairids']]
            if any(i not in bank for i in ids):continue
            negatives=sum(bank[i]['payload']['label']=='not_equivalent' for i in ids)
            label='not_equivalent' if negatives else 'equivalent'
            if negatives>1 or label!=row['label'] or quota[label]>=50:continue
            key=tuple(sorted(ids))
            if key in seen:continue
            plans.append(ids);seen.add(key);quota[label]+=1;usage.update(ids)
        preserved=len(plans)
        def proposed(label):
            result=[]
            for category,k in (('not_equivalent',int(label=='not_equivalent')),('equivalent',level-int(label=='not_equivalent'))):
                available=[a['id'] for a in atoms if a['payload']['label']==category]
                available.sort(key=lambda i:(usage[i],rng.random()))
                result.extend(available[:k])
            rng.shuffle(result)
            return result
        for label in ('equivalent','not_equivalent'):
            tries=0
            while quota[label]<50 and tries<5000:
                tries+=1;ids=proposed(label);key=tuple(sorted(ids))
                if key in seen:
                    rng.shuffle(ids)
                    # Coverage ties are randomized on the next proposal.
                    continue
                plans.append(ids);seen.add(key);quota[label]+=1;usage.update(ids)
        # Backups cover any original group that fails new admission; never relabel a task.
        base_usage=usage.copy()
        for n in range(400):
            label='equivalent' if n%2==0 else 'not_equivalent'
            ids=proposed(label);key=tuple(sorted(ids))
            if key not in seen:plans.append(ids);seen.add(key);usage.update(ids)
        report=generate('codeclone',atoms,root/f'L{level}',level=level,count=100,seed=20261106+level*1000003,
                        max_candidates=len(plans),config=config,groups=plans)
        summary['levels'][str(level)]={'complete':report['complete'],'accepted':len(report['accepted']),
            'original_groups_proposed':preserved,'rejected':len(report['rejected']),'blocked':report['blocked']}
        (root/'summary.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8')
        print(json.dumps({'level':level,**summary['levels'][str(level)]}),flush=True)
        if not report['complete']:raise SystemExit(2)
        usage=base_usage


if __name__=='__main__':main()
