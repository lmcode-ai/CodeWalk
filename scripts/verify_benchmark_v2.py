"""Run actual grading controls; never label these as model benchmark results."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from codewalk.benchmark import grade_submission
from codewalk.data import read_jsonl
from codewalk.evaluation import summarize


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root',type=Path,default=ROOT/'outputs/codewalk-benchmark-v2')
    parser.add_argument('--verus-config',type=Path,required=True)
    parser.add_argument('--repair-prepared',type=Path,required=True)
    parser.add_argument('--output',type=Path,default=ROOT/'outputs/benchmark-v2-validation.json')
    args = parser.parse_args()
    root = args.root
    report = {'scope':'synthetic classification and executable reference controls; no model inference',
              'historical_scores_reusable':False,'domains':{}}
    for domain in ('codeclone','bigo'):
        inputs = {r['task_id']:r for r in read_jsonl(root/'model_inputs'/f'{domain}.jsonl')}
        judges = read_jsonl(root/'judge'/f'{domain}.jsonl')
        controls = {}
        for mode in ('correct','incorrect','malformed'):
            attempts = []
            for judge in judges:
                label = judge['label']
                if mode == 'incorrect':
                    label = ('not_equivalent' if label=='equivalent' else 'equivalent') if domain=='codeclone' else ('constant' if label!='constant' else 'linear')
                answer = ('VERDICT: '+str(int(label=='equivalent'))) if domain=='codeclone' else label
                if mode == 'malformed':answer='invalid answer'
                result = grade_submission(domain,inputs[judge['task_id']],judge,{'response':answer},{})
                attempts.append({'task_id':judge['task_id'],'sample_idx':0,**result})
            score = summarize(judges,attempts,1)['overall']
            assert score['complete'] and score['pass_at_1'] == (1 if mode=='correct' else 0)
            controls[mode] = {'attempts':len(attempts),'expected_status_observed':True}
        report['domains'][domain]={'tasks':len(judges),'grading_controls':controls}
    config = json.loads(args.verus_config.read_text())
    inputs = {r['task_id']:r for r in read_jsonl(root/'model_inputs/verus.jsonl')}
    judges = read_jsonl(root/'judge/verus.jsonl')
    def check(judge):
        task = inputs[judge['task_id']]
        source = (root/judge['reference_file']).read_text(encoding='utf-8')
        reference = grade_submission('verus',task,judge,{'source':source},config)
        return {'task_id':judge['task_id'],'reference':reference}
    checked = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        for row in pool.map(check,judges):
            checked.append(row)
            if len(checked)%20==0:print(json.dumps({'proof_controls_checked':len(checked),'passed':sum(r['reference']['status']=='success' for r in checked)}),flush=True)
    failures = [r for r in checked if r['reference']['status']!='success']
    baseline = []
    for level in (1,2,3,10):
        judge = next(r for r in judges if r['level']==level)
        task = inputs[judge['task_id']]
        result = grade_submission('verus',task,judge,{'source':task['files']['task.rs']},config)
        baseline.append({'level':level,**result})
    report['domains']['verus']={'tasks':len(judges),'reference_successes':len(checked)-len(failures),
                               'reference_failures':failures,'unfinished_controls':baseline}
    judges = read_jsonl(root/'judge/bugfixing.jsonl')
    judge = next(r for r in judges if r['task_id'].endswith('horejsek__python-fastjsonschema-88_x2'))
    task = next(r for r in read_jsonl(root/'model_inputs/bugfixing.jsonl') if r['task_id']==judge['task_id'])
    config = {'timeout_seconds':120,'prepared_repositories':{task['task_id']:str(args.repair_prepared.resolve())}}
    original = grade_submission('bugfixing',task,judge,{'patch':''},config)
    gold = grade_submission('bugfixing',task,judge,{'patch':'\n'.join(judge['gold_patches'])},config)
    missing = grade_submission('bugfixing',task,judge,{'patch':''},{})
    report['domains']['bugfixing']={'tasks':568,'executed_tasks':1,'unchanged':original,'gold':gold,
                                   'missing_environment':missing,'full_bank_runtime_verified':False}
    report['controls_passed'] = (not failures and all(r['status']=='failure' for r in baseline)
                                 and original['status']=='failure' and gold['status']=='success'
                                 and missing['status']=='infra_error')
    args.output.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'controls_passed':report['controls_passed'],'output':str(args.output)},indent=2))
    if not report['controls_passed']:raise SystemExit(1)


if __name__ == '__main__':main()
