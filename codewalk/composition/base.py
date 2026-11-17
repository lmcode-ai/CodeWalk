from __future__ import annotations
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import os
import re
import shutil
import subprocess
import sys
import time


class Reject(ValueError):
    """A candidate fails its domain admission, so another group may be sampled."""


class InfrastructureError(RuntimeError):
    """Missing tools, timeouts or execution failures; never counted as admission."""


def publish_directory(source,destination):
    """Atomic publication, tolerating short-lived Windows scanner/sharing locks."""
    for attempt in range(7):
        try:
            source.rename(destination)
            return
        except PermissionError as exc:
            if attempt==6:
                raise InfrastructureError('Cannot atomically publish verified task: filesystem access denied') from exc
            time.sleep(0.05 * (2**attempt))


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def save(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(value, indent=2, sort_keys=True)+'\n', encoding='utf-8')


def text(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(value, encoding='utf-8',newline='\n')


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', value):
        raise ValueError(f'Invalid identifier: {value!r}')
    return value


def validate_atom(atom, domain):
    if atom.get('schema_version') != 1 or atom.get('domain') != domain:
        raise ValueError('Atom schema_version/domain mismatch')
    for key in ('id', 'source_id'):
        if not isinstance(atom.get(key), str) or not atom[key]:
            raise ValueError(f'Atom needs nonempty {key}')
    provenance = atom.get('provenance', {})
    if any(not isinstance(provenance.get(k), str) or not provenance[k] for k in ('uri','revision','license')):
        raise ValueError('Atom requires provenance uri, revision and license')
    if not isinstance(atom.get('payload'), dict):
        raise ValueError('Atom payload must be an object')


@dataclass
class BuiltTask:
    root: Path
    public: dict
    private: dict


class Runner:
    """Argument-vector execution with per-command evidence; never uses a shell.

    Native execution is for trusted inputs. Docker mode is for untrusted source atoms.
    Tool versions, argv, return codes, logs and content hashes are retained privately.
    """
    def __init__(self, config):
        self.config = config
        self.records = []
        self.timeout = config.get('timeout_seconds', 60)
        if type(self.timeout) not in (int, float) or self.timeout <= 0:
            raise ValueError('timeout_seconds must be positive')
        self.mode = config.get('execution', 'native')
        if self.mode not in ('native','docker'):
            raise ValueError('execution must be native or docker')
        if self.mode == 'docker' and not re.fullmatch(r'[^\s]+@sha256:[0-9a-f]{64}', config.get('image','')):
            raise ValueError('Docker execution requires an immutable image@sha256:digest')

    def run(self, argv, cwd, *, name):
        cwd = Path(cwd).resolve()
        command = [str(x) for x in argv]
        if not command or any(not x or '\x00' in x for x in command):
            raise ValueError('Invalid command argument')
        if command[0] == '$PYTHON':
            command[0] = self.config.get('python',sys.executable) if self.mode == 'native' else 'python'
        if self.mode == 'docker':
            command = ['docker','run','--rm','--network','none','--cpus','2','--memory','4g',
                       '--pids-limit','256','--cap-drop','ALL','--security-opt','no-new-privileges',
                       '--env','PYTEST_DISABLE_PLUGIN_AUTOLOAD=1','--env','PYTHONDONTWRITEBYTECODE=1',
                       '--env','PYTHONHASHSEED=0','--env','PYTHONPATH=/work:/work/src',
                       '--mount',f'type=bind,src={cwd},dst=/work','-w','/work',self.config['image'],*command]
        if self.mode == 'native' and not (Path(command[0]).is_file() or shutil.which(command[0])):
            raise InfrastructureError(f'Executable unavailable: {command[0]}')
        # Do not forward model-provider keys or arbitrary user credentials.
        permitted = {'PATH','SYSTEMROOT','WINDIR','TEMP','TMP','HOME','USERPROFILE',
                     'JAVA_HOME','RUSTUP_HOME','CARGO_HOME','PATHEXT','COMSPEC'}
        env = {k:v for k,v in os.environ.items() if k.upper() in permitted}
        for k,v in self.config.get('tool_env',{}).items():
            if k not in {'JAVA_HOME','RUSTUP_HOME','CARGO_HOME','PATH'} or not isinstance(v,str):
                raise ValueError('tool_env only supports PATH and toolchain home paths')
            env[k] = v
        env.update({'PYTHONHASHSEED':'0','PYTHONDONTWRITEBYTECODE':'1','PYTEST_DISABLE_PLUGIN_AUTOLOAD':'1'})
        env['PYTHONPATH']=os.pathsep.join(str(p) for p in (cwd,cwd/'src') if p.is_dir())
        try:
            result = subprocess.run(command,cwd=cwd,env=env,capture_output=True,timeout=self.timeout)
        except (OSError,subprocess.TimeoutExpired) as exc:
            raise InfrastructureError(f'{name}: {type(exc).__name__}') from exc
        record = {'name':name,'argv':command,'returncode':result.returncode,
                  'stdout':result.stdout.decode('utf-8',errors='replace'),
                  'stderr':result.stderr.decode('utf-8',errors='replace')}
        self.records.append(record)
        return record


class Backend:
    name: str
    directed = True

    def __init__(self, config):
        self.config = config

    def validate(self, atom):
        validate_atom(atom, self.name)

    def compatible(self, left, right):
        return left['payload']['output_type'] == right['payload']['input_type']

    def render(self, atoms, root):
        raise NotImplementedError

    def admit(self, built, runner):
        raise NotImplementedError
