"""Restore published repair tasks without confusing upstream admission with a fresh local run."""
from collections import Counter
import hashlib
import json
from pathlib import Path

from .data import read_jsonl, registry


def test_ids(value):
    if isinstance(value,str):
        import ast
        try:value=json.loads(value)
        except json.JSONDecodeError:value=ast.literal_eval(value)
    if not isinstance(value,list) or not value or any(not isinstance(v,str) or not v or v.startswith('-') for v in value):
        raise ValueError('Expected nonempty explicit test IDs')
    # Published composed records sometimes repeat a shared target test; its
    # set union is the grading contract. The untouched row remains in judge/.
    return list(dict.fromkeys(value))


def restore(source, output):
    """Copy exact task definitions; keep references and preparation outside model inputs."""
    source=Path(source);output=Path(output)
    if output.exists():raise ValueError('Restore destination must not exist')
    spec=registry()['bugfixing'];receipt=json.loads((source/'download_receipt.json').read_text())
    path=source/'data/test.jsonl';raw=path.read_bytes()
    if receipt['revision']!=spec['revision'] or receipt['repo_id']!=spec['repo_id']:
        raise ValueError('Public dataset revision differs from the pinned registry')
    if hashlib.sha256(raw).hexdigest()!=receipt['files']['data/test.jsonl']['sha256']:
        raise ValueError('Published task file differs from download receipt')
    rows=read_jsonl(path);counts=Counter();seen=set();public=[];recipes=[];judges=[];lineage=[]
    for row in rows:
        task=row['task_id'];level=int(row['level']);bugs=row['bugs']
        if task in seen or level!=len(bugs) or level!=row['num_bugs']:raise ValueError('Invalid task identity/depth')
        seen.add(task);counts[str(level)]+=1
        union=sorted({t for b in bugs for t in test_ids(b['FAIL_TO_PASS'])})
        if union!=sorted(test_ids(row['all_FAIL_TO_PASS'])):raise ValueError('Published target-test union mismatch')
        if not row['image'] or not row['repo'] or not row['base_commit']:raise ValueError('Missing original preparation metadata')
        public.append({'task_id':task,'domain':'bugfixing',
            'question':'Repair the repository source so all target tests pass. Do not edit tests or grading configuration.',
            'target_tests':union,'workspace_state':'requires_preparation_from_separate_recipe'})
        recipes.append({'task_id':task,'repository':'https://github.com/'+row['repo']+'.git',
            'image':row['image'],'base_commit':row['base_commit'],'test_patches':[b['test_patch'] for b in bugs],
            'target_tests':union,'repository_path':None,
            'instructions':'Use the original benchmark image; locate its actual repository working directory, checkout the common base, apply all test patches, seal Git history, and run the agent without network access. Resolve and record the image digest before use.'})
        judges.append({'task_id':task,'level':level,'target_tests':union,'gold_patches':[b['gold_patch'] for b in bugs],
            'validation_status':'published_original_not_locally_readmitted',
            'upstream_record':row})
        lineage.append({'task_id':task,'domain':'bugfixing','level':level,
            'source_ids':[row['repo']],'atom_ids':[b['instance_id'] for b in bugs],
            'public_dataset':spec['repo_id'],'revision':spec['revision'],
            'original_record_sha256':hashlib.sha256(json.dumps(row,sort_keys=True,separators=(',',':')).encode()).hexdigest(),
            'validation_status':'published_original_not_locally_readmitted'})
    if dict(counts)!=spec['expected_levels']:raise ValueError('Published task counts differ from the full benchmark')
    output.mkdir(parents=True)
    for relative,records in [('model_inputs/bugfixing.jsonl',public),('preparation/bugfixing.jsonl',recipes),
                             ('judge/bugfixing.jsonl',judges),('judge/lineage.jsonl',lineage)]:
        target=output/relative;target.parent.mkdir(parents=True,exist_ok=True)
        target.write_text(''.join(json.dumps(r,ensure_ascii=True,sort_keys=True)+'\n' for r in records),encoding='utf-8')
    report={'domain':'bugfixing','tasks':len(rows),'counts_by_level':dict(counts),
        'definition_recovery':'Exact original published groups, base commits, images, test patches and gold patches',
        'upstream_revision':spec['revision'],'original_file_sha256':hashlib.sha256(raw).hexdigest(),
        'validation_status':'published_original_not_locally_readmitted',
        'native_reconstruction_subset_is_not_the_full_benchmark':True,
        'remaining_runtime_work':'Original container images, path/environment resolution and fresh G1/G2 execution; no fresh 568-task pass claim.'}
    (output/'manifest.json').write_text(json.dumps(report,indent=2)+'\n')
    return report


def prepare(recipes, task_id, output, *, repository=None):
    """Materialize an original shared snapshot without references or Git history.

    This prepares source and test patches only. It does not assert the original
    container environment is installed or that G1/G2 tests have been rerun.
    """
    import io
    import shutil
    import subprocess
    import tarfile
    import tempfile
    import urllib.request
    import zipfile
    from .data import safe_path
    from .composition.base import Runner
    from .composition.repair import RepairBackend
    output=Path(output).resolve()
    if output.exists():raise ValueError('Prepared workspace must not already exist')
    rows=[r for r in read_jsonl(recipes) if r['task_id']==task_id]
    if len(rows)!=1:raise ValueError('Expected exactly one original repair recipe')
    recipe=rows[0]
    with tempfile.TemporaryDirectory(prefix='cw-repair-') as temporary:
        work=Path(temporary);base=work/'base';base.mkdir()
        if repository is not None:
            result=subprocess.run(['git','-C',str(Path(repository).resolve()),'archive','--format=zip',recipe['base_commit']],
                                  capture_output=True,timeout=120)
            if result.returncode:raise ValueError('Original common base unavailable in supplied local Git repository')
            with zipfile.ZipFile(io.BytesIO(result.stdout)) as archive:
                for entry in archive.infolist():
                    if entry.is_dir():continue
                    if ((entry.external_attr>>16)&0o170000)==0o120000:raise ValueError('Use original container preparation for symlink repositories')
                    path=safe_path(base,entry.filename);path.parent.mkdir(parents=True,exist_ok=True)
                    path.write_bytes(archive.read(entry))
        else:
            import re
            match=re.fullmatch(r'https://github.com/([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)\.git',recipe['repository'])
            if not match or not re.fullmatch('[0-9a-f]{40,64}',recipe['base_commit']):raise ValueError('Unsupported original repository URL/commit')
            url='https://codeload.github.com/'+match[1]+'/tar.gz/'+recipe['base_commit']
            request=urllib.request.Request(url,headers={'User-Agent':'CodeWalk-repair-restore/0.4'})
            with urllib.request.urlopen(request,timeout=120) as response,tarfile.open(fileobj=response,mode='r|gz') as archive:
                for entry in archive:
                    if entry.isdir():continue
                    if not entry.isfile():raise ValueError('Use original container preparation for special/symlink repositories')
                    relative='/'.join(entry.name.split('/')[1:])
                    if not relative:raise ValueError('Invalid source archive root')
                    path=safe_path(base,relative);path.parent.mkdir(parents=True,exist_ok=True)
                    with archive.extractfile(entry) as content:path.write_bytes(content.read())
        # No gold patches are present in the preparation recipe or read here.
        runner=Runner({'timeout_seconds':120});backend=RepairBackend({})
        for i,patch in enumerate(recipe['test_patches']):
            target=work/f'test-{i}.patch';target.write_text(patch,encoding='utf-8',newline='\n')
            backend.apply(runner,base,target,f'original-test-patch-{i}')
        if any('.git' in p.relative_to(base).parts for p in base.rglob('*')):
            raise ValueError('Prepared source contains Git metadata')
        output.parent.mkdir(parents=True,exist_ok=True);shutil.copytree(base,output)
        fingerprint={p.relative_to(output).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
                     for p in sorted(output.rglob('*')) if p.is_file()}
        return {'task_id':task_id,'files':len(fingerprint),'target_tests':recipe['target_tests'],
            'prepared_source_sha256':hashlib.sha256(json.dumps(fingerprint,sort_keys=True).encode()).hexdigest(),
            'source_and_test_patches_prepared':True,'gold_exposed':False,'git_history_exposed':False,
            'test_execution_performed':False,'original_image':recipe['image'],
            'environment_note':'Source preparation alone does not recreate the original image dependencies or rerun admission.'}
