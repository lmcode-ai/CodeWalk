"""Real shared-snapshot repair composition using Git patches and pytest JUnit evidence."""
from datetime import datetime
import io
from pathlib import Path
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
import zipfile
from .base import Backend, BuiltTask, Reject, InfrastructureError, save, text
from ..data import safe_path


def patch_files(patch):
    if not isinstance(patch,str) or 'GIT binary patch' in patch:
        raise ValueError('Repair patches must be textual Git unified diffs')
    modes = re.findall(r'^(?:new file mode|new mode|old mode|deleted file mode) (\d+)$',patch,re.M)
    if any(mode not in ('100644','100755') for mode in modes):
        raise ValueError('Symlink and special-file patches are unsupported')
    if re.search(r'^(?:rename from|rename to|copy from|copy to) ',patch,re.M):
        raise ValueError('Normalize rename/copy patches before generation')
    paths = re.findall(r'^\+\+\+ b/(.+)$',patch,re.M)
    paths += re.findall(r'^--- a/(.+)$',patch,re.M)
    if not paths: raise ValueError('Patch must use Git unified diff paths')
    for path in paths:
        safe_path(Path.cwd(),path)
        if any(part.lower()=='.git' for part in Path(path).parts):
            raise ValueError('Patches cannot modify Git metadata')
    return set(paths)


class RepairBackend(Backend):
    name = 'bugfixing'
    directed = False

    def validate(self,atom):
        super().validate(atom)
        p = atom['payload']
        repo = Path(p['repository']).resolve()
        if not repo.is_dir(): raise ValueError('Repair repository must be an existing local Git checkout')
        if not re.fullmatch('[0-9a-f]{40,64}',p['base_commit']): raise ValueError('Use a full base commit hash')
        fixed = datetime.fromisoformat(p.get('fix_time',p.get('base_time','')).replace('Z','+00:00'))
        if fixed.tzinfo is None: raise ValueError('fix_time/base_time needs a time zone')
        for k in ('gold_patch','test_patch'):
            patch_files(p[k])
        if not p.get('test_ids') or len(set(p['test_ids']))!=len(p['test_ids']): raise ValueError('Unique pytest node IDs required')
        for test_id in p['test_ids']:
            if test_id.startswith('-') or '::' not in test_id: raise ValueError('Use explicit pytest node IDs')
            safe_path(repo,test_id.split('::')[0])
        if set(p.get('modified_files',[]))!=patch_files(p['gold_patch']):
            raise ValueError('modified_files must match gold patch source paths')
        tests = {t.split('::')[0] for t in p['test_ids']}
        if patch_files(p['gold_patch']) & tests: raise ValueError('Gold source patches cannot edit target tests')

    def compatible(self,a,b):
        a,b = a['payload'],b['payload']
        return Path(a['repository']).resolve()==Path(b['repository']).resolve() and bool(
            set(a.get('interaction_files',a['modified_files']))&set(b.get('interaction_files',b['modified_files'])))

    def render(self,atoms,root):
        protected = {t.split('::')[0].casefold() for a in atoms for t in a['payload']['test_ids']}
        protected.update(path.casefold() for a in atoms for path in patch_files(a['payload']['test_patch']))
        for atom in atoms:
            for path in patch_files(atom['payload']['gold_patch']):
                if path.casefold() in protected or Path(path).name.casefold() in ('conftest.py','pytest.ini','tox.ini','setup.cfg','pyproject.toml'):
                    raise Reject('Gold patches cannot change any group test or test configuration')
        first = min(atoms,key=lambda a:(datetime.fromisoformat(a['payload'].get('fix_time',a['payload'].get('base_time','')).replace('Z','+00:00')),a['id']))
        p = first['payload']
        work = root/'work'
        work.mkdir()
        try:
            result = subprocess.run(['git','-C',str(Path(p['repository']).resolve()),'archive','--format=zip',p['base_commit']],
                                    capture_output=True,timeout=60)
        except (OSError,subprocess.TimeoutExpired) as exc:
            raise InfrastructureError('Local git archive failed') from exc
        if result.returncode: raise InfrastructureError('Base commit unavailable in local repository')
        with zipfile.ZipFile(io.BytesIO(result.stdout)) as archive:
            for entry in archive.infolist():
                if entry.is_dir(): continue
                if ((entry.external_attr >> 16)&0o170000)==0o120000: raise Reject('Symlink source entries unsupported')
                path = safe_path(work/'base',entry.filename)
                path.parent.mkdir(parents=True,exist_ok=True)
                path.write_bytes(archive.read(entry))
        for i,atom in enumerate(atoms):
            text(work/f'test-{i}.patch',atom['payload']['test_patch'])
            text(work/f'gold-{i}.patch',atom['payload']['gold_patch'])
        return BuiltTask(root,{}, {'base_commit':p['base_commit'],'atoms':[a['payload'] for a in atoms],
                                  'target_tests':sorted({t for a in atoms for t in a['payload']['test_ids']})})

    def apply(self,runner,root,patch,name):
        # Git patch application is host-side preparation, never source-code execution.
        from .base import Runner
        local = Runner({'execution':'native','timeout_seconds':runner.timeout})
        gitdir = root.parent/'preparation.git'
        if not gitdir.exists():
            initialized = local.run(['git','-c','core.longpaths=true','init','--bare','--quiet',str(gitdir.resolve())],root,name='initialize-isolated-patch-context')
            if initialized['returncode']:
                runner.records.extend(local.records)
                raise InfrastructureError('Cannot initialize isolated Git context')
        git = ['git','--git-dir=../preparation.git','--work-tree=.',
               '-c','core.bare=false','-c','core.longpaths=true']
        import os
        patch_argument=os.path.relpath(patch.resolve(),root.resolve())
        result = local.run([*git,'apply','--check','--whitespace=nowarn',patch_argument],root,name=name+'-check')
        if result['returncode']!=0:
            runner.records.extend(local.records)
            raise Reject(f'{name}: patch does not apply at the shared snapshot')
        result = local.run([*git,'apply','--whitespace=nowarn',patch_argument],root,name=name)
        runner.records.extend(local.records)
        if result['returncode']!=0: raise Reject(f'{name}: application failed')

    def tests(self,runner,root,node_ids,name):
        xml = root/'cw-results.xml'
        result = runner.run(['$PYTHON','-m','pytest','-q','--import-mode=importlib',
                            '--junitxml=cw-results.xml',*node_ids],root,name=name)
        if not xml.is_file(): raise InfrastructureError('pytest did not produce JUnit evidence')
        try: tree = ET.parse(xml)
        except ET.ParseError as exc: raise InfrastructureError('Malformed pytest evidence') from exc
        cases = list(tree.iter('testcase'))
        errors = sum(c.find('error') is not None for c in cases)
        skipped = sum(c.find('skipped') is not None for c in cases)
        failures = sum(c.find('failure') is not None for c in cases)
        if errors or skipped or len(cases)!=len(node_ids) or result['returncode'] not in (0,1):
            raise InfrastructureError('Test collection/setup error, skipped test, or incorrect target count')
        report = {'collected':len(cases),'failures':failures,'passed':len(cases)-failures}
        xml.rename(root/(name+'.xml'))
        return report

    def admit(self,built,runner):
        work = built.root/'work'
        base = work/'base'
        atoms = built.private['atoms']
        for i,_ in enumerate(atoms): self.apply(runner,base,work/f'test-{i}.patch',f'test-patch-{i}')
        # Public projection is captured before running tests or applying any gold patch.
        import base64
        files = {}
        binary = {}
        for path in sorted(base.rglob('*')):
            if path.is_symlink(): raise Reject('Prepared repository cannot contain symlinks')
            if not path.is_file(): continue
            relative = path.relative_to(base).as_posix()
            content = path.read_bytes()
            try: files['repository/'+relative] = content.decode('utf-8')
            except UnicodeDecodeError: binary['repository/'+relative] = base64.b64encode(content).decode()
        built.public.update({'files':files,'binary_files_base64':binary,
            'question':'Repair the source so all target tests pass. Do not edit tests.',
            'target_tests':built.private['target_tests']})
        # Clone the pristine prepared state before any tests can mutate repository files.
        reference = work/'reference'
        shutil.copytree(base,reference)
        atom_reports = []
        for i,atom in enumerate(atoms):
            isolated = work/f'live-{i}'
            shutil.copytree(reference,isolated)
            checked = self.tests(runner,isolated,atom['test_ids'],f'live-{i}')
            if checked['failures']!=checked['collected']: raise Reject('Not every target test is FAIL_TO_PASS at common base')
            atom_reports.append(checked)
        for i,_ in enumerate(atoms): self.apply(runner,reference,work/f'gold-{i}.patch',f'gold-patch-{i}')
        checked = self.tests(runner,reference,built.private['target_tests'],'joint-gold')
        if checked['failures']: raise Reject('Joint reference does not pass all target tests')
        return {'atom_gate':True,'reference_gate':True,'atomic_tests':atom_reports,'joint_tests':checked,
                'oracle':'targeted FAIL_TO_PASS only; no PASS_TO_PASS regression claim'}
