"""Replace missing original banks with admitted reconstructions; preserve historical scores separately."""
import hashlib
import argparse
import json
from pathlib import Path
import shutil
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from codewalk.data import read_jsonl


def write(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(''.join(json.dumps(row, ensure_ascii=True, sort_keys=True)+'\n' for row in rows), encoding='utf-8')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--refresh-validation',action='store_true')
    args = parser.parse_args()
    output = ROOT / 'outputs/codewalk-benchmark-v2'
    if args.refresh_validation:
        validation = json.loads((ROOT/'outputs/benchmark-v2-validation-final.json').read_text())
        cli = json.loads((ROOT/'outputs/benchmark-v2-cli/report.json').read_text())
        assert validation['controls_passed'] and cli['four_domain_cli_reference_controls_passed']
        manifest = json.loads((output/'manifest.json').read_text())
        manifest['four_domain_grading_controls_passed'] = True
        manifest['full_clone_and_bigo_label_controls_passed'] = True
        manifest['verus_reference_grading_controls_passed'] = 400
        manifest['repair_runtime_control_tasks'] = 1
        (output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
        destination = output/'judge/validation'
        destination.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(ROOT/'outputs/benchmark-v2-validation-final.json',destination/'controls.json')
        shutil.copyfile(ROOT/'outputs/benchmark-v2-cli/report.json',destination/'cli.json')
        shutil.copyfile(ROOT/'docs/evaluating-v2.md',output/'README.md')
        archive(output)
        print('Refreshed validation receipts; full repair runtime replay remains incomplete')
        return
    if output.exists():
        raise SystemExit('Output already exists; preserve the versioned artifact')
    old = ROOT / 'outputs/paper-sized-benchmark'
    originals = ROOT / 'outputs/paper-original-repair'
    proof = ROOT / 'outputs/historical-recovery/verus-original-historical-full-v2'
    report = json.loads((proof/'report.json').read_text())
    assert report['references_verified'] == report['admitted'] == 400
    lineage = []
    for domain in ('codeclone', 'bigo', 'bugfixing', 'verus'):
        source = originals if domain == 'bugfixing' else old
        if domain == 'verus':
            tasks, judges = [], []
            for result in report['results']:
                task_id = result['task_id']
                public, reference = proof/task_id/'task.rs', proof/task_id/'reference.rs'
                assert hashlib.sha256(public.read_bytes()).hexdigest() == result['original_sha256']
                assert hashlib.sha256(reference.read_bytes()).hexdigest() == result['reference_sha256']
                tasks.append({'task_id':task_id, 'files':{'task.rs':public.read_text(encoding='utf-8')},
                              'question':'Complete proof annotations and postconditions. Preserve executable code and preconditions. Original specification predicates and chain_driver are restored by the grader.'})
                name = 'judge/references/' + task_id + '.rs'
                target = output/name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(reference, target)
                judges.append({'task_id':task_id,'level':result['level'],'reference_file':name})
        else:
            tasks = read_jsonl(source/'model_inputs'/f'{domain}.jsonl')
            judges = read_jsonl(source/'judge'/f'{domain}.jsonl')
        expected = {'codeclone':418,'bigo':320,'bugfixing':568,'verus':400}[domain]
        assert len(tasks) == len(judges) == expected
        mapping = {row['task_id']:f'v2:{domain}:'+row['task_id'] for row in tasks}
        assert len(mapping) == expected
        assert {r['task_id'] for r in judges} == set(mapping)
        for row in tasks + judges:
            row['task_id'] = mapping[row['task_id']]
        for source_id, task_id in mapping.items():
            lineage.append({'task_id':task_id,'source_task_id':source_id,'domain':domain,
                            'origin':'new_composition' if domain in ('codeclone','bigo') else 'published_original_input',
                            'historical_model_result_bound':False})
        write(output/'model_inputs'/f'{domain}.jsonl', tasks)
        write(output/'judge'/f'{domain}.jsonl', judges)
        if domain == 'bugfixing':
            recipes = read_jsonl(originals/'preparation/bugfixing.jsonl')
            for row in recipes:
                row['task_id'] = mapping[row['task_id']]
            write(output/'preparation/bugfixing.jsonl', recipes)
    write(output/'judge/lineage.jsonl',lineage)
    shutil.copytree(old/'LICENSES', output/'LICENSES')
    manifest = {'version':'codewalk-benchmark-v2','total_tasks':1706,
                'counts':{'codeclone':418,'bigo':320,'bugfixing':568,'verus':400},
                'historical_paper_dataset':False,'historical_scores_reusable':False,
                'all_1706_runtime_checks_completed':False,
                'repair_full_runtime_replay_completed':False,
                'verus_reference_checks':400,
                'composition_differences':'See docs/three-way-alignment.md; new Clone/BigO are independent benchmark variants, not recovered paper tasks.'}
    (output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    shutil.copyfile(ROOT/'docs/evaluating-v2.md',output/'README.md')
    archive(output)
    print(json.dumps(manifest,indent=2))


def archive(output):
    files = sorted(p for p in output.rglob('*') if p.is_file() and p.name != 'SHA256SUMS')
    (output/'SHA256SUMS').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.relative_to(output).as_posix()+'\n' for p in files),encoding='utf-8')
    archive_path = output.with_suffix('.zip')
    with zipfile.ZipFile(archive_path,'w',compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(output.rglob('*')):
            if path.is_file():archive.write(path,'codewalk-benchmark-v2/'+path.relative_to(output).as_posix())
    with zipfile.ZipFile(archive_path) as archive:
        assert archive.testzip() is None
    archive_path.with_suffix('.zip.sha256').write_text(hashlib.sha256(archive_path.read_bytes()).hexdigest()+'  '+archive_path.name+'\n',encoding='utf-8')


if __name__ == '__main__':main()
