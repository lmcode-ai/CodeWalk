"""Evaluate versioned benchmark submissions with explicit runtime-error accounting."""
from pathlib import Path
import re
import shutil
import tempfile

from .data import read_jsonl
from .evaluation import grade_label
from .composition.base import Runner, InfrastructureError
from .composition.repair import RepairBackend, patch_files
from .composition.rust_source import SourceVerusBackend
from .recovery.rust import functions, tokens, verus_body, executable_projection
from .recovery.published_verus import requires, values


def checked_proof(original, candidate):
    """Validate editable proof slots, then restore original fixed predicates/driver.

    This conservative grammar supports the recovered flat Verus bank. Arbitrary Rust
    modules/macros/attributes are not an extension mechanism for model submissions.
    """
    forbidden = {'assume', 'admit', 'axiom', 'external', 'external_body', 'unsafe',
                 'exec_allows_no_decreases', 'verifier', 'include', 'include_str',
                 'include_bytes', 'cfg', 'global_size_of', 'trusted', 'unimplemented'}
    # Historical tasks contain this sound verification-strategy attribute. It is
    # also constrained by the unchanged outside-function skeleton below.
    scan_candidate = re.sub(r'#\s*\[\s*verifier\s*::\s*loop_isolation\s*\(\s*false\s*\)\s*\]', '', candidate)
    if forbidden & set(values(scan_candidate)):
        raise ValueError('Unsupported proof bypass, attribute or external code')
    old_body, new_body = verus_body(original), verus_body(candidate)
    old, new = functions(old_body), functions(new_body)
    if not old or not set(old) <= set(new):
        raise ValueError('Submission removed an original function')

    def outside(source, body, fns):
        remainder = body
        for fn in sorted(fns.values(), key=lambda f: f['start'], reverse=True):
            remainder = remainder[:fn['start']] + remainder[fn['end']:]
        start = source.index(body)
        whole = source[:start] + remainder + source[start+len(body):]
        # References may need these two standard prelude helpers.
        return values(whole.replace('use vstd::math::{max,min};', ''))

    if outside(original, old_body, old) != outside(candidate, new_body, new):
        raise ValueError('Submission changes code outside editable functions')
    # A dictionary parser must not silently discard duplicate function definitions.
    for name in new:
        if len(re.findall(r'\bfn\s+' + re.escape(name) + r'\s*(?:\(|<)', new_body)) != 1:
            raise ValueError('Duplicate function definition')
    replacements = []
    for name, fn in new.items():
        if name not in old:
            if not ({'proof', 'spec'} & set(values(fn['prefix']))):
                raise ValueError('Additional executable functions are forbidden')
            continue
        original_fn = old[name]
        fixed = name == 'chain_driver' or name.startswith('step') or 'spec' in values(original_fn['prefix'])
        if fixed:
            replacements.append((fn['start'], fn['end'], old_body[original_fn['start']:original_fn['end']]))
            continue
        if values(fn['prefix']) != values(original_fn['prefix']):
            raise ValueError('Function mode/visibility changed')
        def signature(header):
            ts = values(header)
            end = next((i for i, value in enumerate(ts) if value in {'requires','ensures','decreases','recommends','returns'}), len(ts))
            return ts[:end]
        if signature(fn['header']) != signature(original_fn['header']) or requires(fn) != requires(original_fn):
            raise ValueError('Function signature or precondition changed')
        if 'proof' not in values(original_fn['prefix']) and executable_projection(fn['body']) != executable_projection(original_fn['body']):
            raise ValueError('Executable code changed')
    for start, end, text in sorted(replacements, reverse=True):
        new_body = new_body[:start] + text + new_body[end:]
    start = candidate.index(verus_body(candidate))
    return candidate[:start] + new_body + candidate[start+len(verus_body(candidate)):]


def grade_submission(domain, task, judge, submission, config):
    if domain in ('codeclone', 'bigo'):
        return grade_label(domain, submission.get('response', ''), judge['label'])
    runner = Runner(config)
    try:
        with tempfile.TemporaryDirectory(prefix='cw-eval-') as temporary:
            work = Path(temporary)
            if domain == 'verus':
                source = checked_proof(task['files']['task.rs'], submission.get('source', ''))
                (work / 'submission.rs').write_text(source, encoding='utf-8', newline='\n')
                try:
                    result = SourceVerusBackend(config).verify(runner, work, 'submission.rs')
                except InfrastructureError:
                    diagnostics = '\n'.join(r.get('stdout','')+'\n'+r.get('stderr','') for r in runner.records)
                    if re.search(r'error\[E\d+\]|error: (?:expected|unexpected|cannot find|mismatched|unclosed)', diagnostics):
                        return {'status':'failure','reason':'Submission has parse/type errors','execution':runner.records}
                    raise
                return {'status': 'success' if result['errors'] == 0 else 'failure', 'verification': result, 'execution': runner.records}
            if domain != 'bugfixing':
                raise ValueError('Unknown benchmark domain')
            prepared = config.get('prepared_repositories', {}).get(task['task_id'])
            if not prepared or not Path(prepared).is_dir():
                raise InfrastructureError('Prepared task repository missing; run prepare_published_repair.py first')
            repository = work / 'repository'
            shutil.copytree(prepared, repository)
            if any(p.name.casefold() == '.git' or p.is_symlink() for p in repository.rglob('*')):
                raise InfrastructureError('Prepared repository must be history-free and contain no symlinks')
            patch = submission.get('patch', '')
            if patch.strip():
                allowed = set().union(*(patch_files(p) for p in judge['gold_patches']))
                changed = patch_files(patch)
                protected = {p.split('::')[0].casefold() for p in judge['target_tests']}
                if judge.get('upstream_record'):
                    for bug in judge['upstream_record']['bugs']:
                        protected.update(p.casefold() for p in patch_files(bug['test_patch']))
                configuration = {'conftest.py','pytest.ini','tox.ini','setup.cfg','pyproject.toml'}
                if not changed <= allowed or any(p.casefold() in protected or Path(p).name.casefold() in configuration for p in changed):
                    raise ValueError('Patch edits files outside the allowed source paths')
                patch_path = work / 'submission.patch'
                patch_path.write_text(patch, encoding='utf-8', newline='\n')
                RepairBackend(config).apply(runner, repository, patch_path, 'candidate-patch')
            result = RepairBackend(config).tests(runner, repository, judge['target_tests'], 'candidate-tests')
            return {'status': 'success' if result['failures'] == 0 else 'failure', 'tests': result, 'execution': runner.records}
    except InfrastructureError as exc:
        return {'status': 'infra_error', 'reason': str(exc), 'execution': runner.records}
    except ValueError as exc:
        return {'status': 'failure', 'reason': str(exc), 'execution': runner.records}


def evaluate(root, domain, submissions, config):
    root = Path(root)
    tasks = read_jsonl(root / 'model_inputs' / (domain + '.jsonl'))
    judges = read_jsonl(root / 'judge' / (domain + '.jsonl'))
    bank = {r['task_id']: r for r in tasks}
    oracle = {r['task_id']: r for r in judges}
    if len(bank) != len(tasks) or len(oracle) != len(judges) or bank.keys() != oracle.keys():
        raise ValueError('Inconsistent or duplicated task identities')
    seen = set()
    for row in submissions:
        key = row.get('task_id'), row.get('sample_idx')
        if key[0] not in bank or type(key[1]) is not int or key[1] < 0 or key in seen:
            raise ValueError('Unknown, duplicate or malformed attempt identity')
        seen.add(key)
    for row in submissions:
        task_id = row['task_id']
        task_config = {**config, **config.get('task_overrides', {}).get(task_id, {})}
        result = grade_submission(domain, bank[task_id], oracle[task_id], row, task_config)
        yield {'task_id': task_id, 'sample_idx': row['sample_idx'], **result}
