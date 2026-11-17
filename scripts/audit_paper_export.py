"""Audit full paper counts, source routing, restored definitions and classification control scores."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from codewalk.data import read_jsonl,safe_path
from codewalk.evaluation import grade_label,summarize
from codewalk.repair_restore import test_ids


def digest(row):return hashlib.sha256(json.dumps(row,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()).hexdigest()


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',default=str(ROOT/'outputs/paper-sized-benchmark'))
    p.add_argument('--output',default=str(ROOT/'outputs/paper-export-validation.json'));args=p.parse_args()
    root=Path(args.root);profile=json.loads((ROOT/'configs/paper-reconstruction.json').read_text())
    manifest=json.loads((root/'manifest.json').read_text())
    assert manifest['counts_by_level']==profile['expected_counts']
    assert manifest['total_tasks']==1706 and manifest['freshly_admitted_tasks']==1138 and manifest['restored_published_tasks']==568
    lineage=read_jsonl(root/'judge/lineage.jsonl');bank={r['task_id']:r for r in lineage}
    assert len(bank)==len(lineage)==1706
    report={'tasks':1706,'freshly_admitted':1138,'restored_original_definitions':568,'domains':{},
            'model_inference_performed':False,'historical_scores_reusable':False}
    all_ids=set();semantic=set()
    for domain,expected in profile['expected_counts'].items():
        inputs=read_jsonl(root/'model_inputs'/f'{domain}.jsonl');judges=read_jsonl(root/'judge'/f'{domain}.jsonl')
        ids={r['task_id'] for r in inputs};judge={r['task_id']:r for r in judges}
        assert len(ids)==len(inputs)==len(judges)==sum(expected.values())
        assert ids==set(judge) and not ids&all_ids;all_ids.update(ids)
        assert dict(Counter(str(r['level']) for r in judges))==expected
        details={'tasks':len(inputs),'counts_by_level':expected,'classification_controls':None}
        for row in inputs:
            task=row['task_id'];line=bank[task];j=judge[task];level=j['level']
            assert not set(row)&{'label','level','atom_ids','source_ids','reference_source','gold_patch','gold_patches'}
            assert not re.search('[\u3400-\u4dbf\u4e00-\u9fff]',row['question'])
            for name in (*row.get('files',{}),*row.get('binary_files_base64',{})):safe_path(root/'model-workspace',name)
            group=tuple(line['atom_ids'])
            if domain=='bugfixing':
                original=j['upstream_record'];group=(original['base_commit'],tuple(sorted(group)))
                assert line['original_record_sha256']==digest(original)
                assert j['validation_status']==line['validation_status']=='published_original_not_locally_readmitted'
                assert j['gold_patches']==[b['gold_patch'] for b in original['bugs']]
                assert row['target_tests']==sorted(test_ids(original['all_FAIL_TO_PASS']))
                assert row['workspace_state']=='requires_preparation_from_separate_recipe'
            else:
                assert line['public_sha256']==digest(row)
                assert line['admission']['atom_gate'] and line['admission']['reference_gate']
                if domain=='verus':
                    assert line['admission']['reference']['errors']==0
                    assert line['admission']['unfinished']['errors']>0
                    assert (root/j['reference_file']).is_file()
                elif domain=='codeclone':
                    assert row['composition_mode']=='chain'
                    stages={int(m[1]) for name in row['files'] if (m:=re.match(r'cw/stage_(\d+)/',name))}
                    assert stages==set(range(level))
                    for i in range(1,level):assert f'v{i-1}' in row['files']['OuterA.java']
                else:
                    assert len([f for f in row['files'] if re.fullmatch(r'stage_\d+\.py',f)])==level
            key=(domain,level,group);assert key not in semantic;semantic.add(key)
        if domain in ('codeclone','bigo'):
            controls={}
            for mode in ('reference','incorrect','malformed'):
                attempts=[]
                for task in judges:
                    label=task['label']
                    if mode=='incorrect':label=('not_equivalent' if label=='equivalent' else 'equivalent') if domain=='codeclone' else ('constant' if label!='constant' else 'linear')
                    answer=('VERDICT: '+('1' if label=='equivalent' else '0')) if domain=='codeclone' else label
                    if mode=='malformed':answer='unparseable'
                    attempts.append({'task_id':task['task_id'],'sample_idx':0,**grade_label(domain,answer,task['label'])})
                score=summarize(judges,attempts,1)['overall']['pass_at_1'];assert score==(1.0 if mode=='reference' else 0.0)
                controls[mode]=score
            details['classification_controls']=controls
        if domain=='codeclone':
            labels=Counter((r['level'],r['label']) for r in judges)
            assert all(labels[int(level),'equivalent']==labels[int(level),'not_equivalent']==count//2 for level,count in expected.items())
            details['all_levels_balanced']=True
        report['domains'][domain]=details
    recipes=read_jsonl(root/'preparation/bugfixing.jsonl')
    repair_judge={r['task_id']:r for r in read_jsonl(root/'judge/bugfixing.jsonl')}
    assert len(recipes)==568 and {r['task_id'] for r in recipes}==set(repair_judge)
    for recipe in recipes:
        original=repair_judge[recipe['task_id']]['upstream_record']
        assert recipe['base_commit']==original['base_commit'] and recipe['image']==original['image']
        assert recipe['test_patches']==[b['test_patch'] for b in original['bugs']]
        assert 'gold_patches' not in recipe
    report['duplicate_semantic_groups']=0;report['public_judge_separation']=True
    Path(args.output).write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))


if __name__=='__main__':main()
