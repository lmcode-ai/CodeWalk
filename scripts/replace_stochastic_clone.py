"""Replace the unsupported RNG component with a freshly admitted deterministic component."""
from collections import Counter
import argparse
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from codewalk.composition import generate
from codewalk.composition.java_clone import stochastic_source
from codewalk.data import read_jsonl


def main():
    p=argparse.ArgumentParser();p.add_argument('--config',required=True)
    p.add_argument('--output',default=str(ROOT/'outputs/source-derived-datasets/clone-deterministic-replacements-v2'))
    args=p.parse_args()
    bank_root=ROOT/'outputs/source-derived-datasets/codeclone-original-first'
    atoms=[a for a in read_jsonl(ROOT/'outputs/source-recovery/clone/atoms.jsonl') if not stochastic_source(a['payload']['a_members']+'\n'+a['payload']['b_members'])]
    by_id={a['id']:a for a in atoms};usage=Counter();bad=[];keys={1:set(),2:set(),3:set()}
    for level in (1,2,3):
        root=bank_root/f'L{level}';report=json.loads((root/'manifest.json').read_text(encoding='utf-8'))
        if not report['complete']:raise ValueError('Base reconstruction must finish first')
        for row in report['accepted']:
            usage.update(row['atom_ids'])
            if 'fempd-13254' in row['atom_ids']:bad.append((level,row['task_id'],row['atom_ids']))
            else:keys[level].add(tuple(sorted(row['atom_ids'])))
    output=Path(args.output);output.mkdir(parents=True,exist_ok=True)
    summary=[]
    for index,(level,task_id,group) in enumerate(bad):
        label=json.loads((bank_root/f'L{level}/private/candidates'/task_id/'judge.json').read_text(encoding='utf-8'))['label']
        alternatives=sorted((a for a in atoms if a['payload']['label']==label and a['id'] not in group),key=lambda a:(usage[a['id']],a['id']))
        plans=[]
        for a in alternatives:
            replacement=[a['id'] if i=='fempd-13254' else i for i in group]
            if tuple(sorted(replacement)) not in keys[level]:plans.append(replacement)
            if len(plans)==10:break
        config=json.loads(Path(args.config).read_text());config.update({'timeout_seconds':30,'label_quotas':{label:1}})
        root=output/f'case-{index:03d}'
        report=generate('codeclone',atoms,root,level=level,count=1,max_candidates=len(plans),config=config,groups=plans)
        if not report['complete']:raise ValueError('Could not admit a deterministic replacement')
        report['replaces_task']=task_id
        (root/'manifest.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
        summary.append({'removed':task_id,'replacement':report['accepted'][0]['task_id'],'level':level})
        usage.update(report['accepted'][0]['atom_ids'])
        keys[level].add(tuple(sorted(report['accepted'][0]['atom_ids'])))
    (output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'replaced_tasks':len(summary),'excluded_atom':'fempd-13254'},indent=2))


if __name__=='__main__':main()
