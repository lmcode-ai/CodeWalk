from __future__ import annotations
import json
from pathlib import Path
import platform
import inspect
import random
import sys
from .base import InfrastructureError, Reject, Runner, canonical, digest, save, publish_directory
from ..graph import sample_groups


def backend(domain, config):
    if domain=='verus' and config.get('verus_mode')=='source_recovered':
        from .rust_source import SourceVerusBackend
        return SourceVerusBackend(config)
    from .registry import BACKENDS
    return BACKENDS[domain](config)


def generate(domain, atoms, output, *, level, count=1, seed=42, max_candidates=100,
             max_per_source=None, config=None, groups=None):
    config = dict(config or {})
    quotas = config.get('label_quotas')
    if quotas is not None and (not isinstance(quotas,dict) or not quotas or
            any(type(v) is not int or v<0 for v in quotas.values()) or sum(quotas.values())!=count):
        raise ValueError('label_quotas must be nonnegative integer counts summing to --count')
    if any(type(v) is not int or v < 1 for v in (level,count,max_candidates)):
        raise ValueError('level/count/max_candidates must be positive integers')
    if type(seed) is not int:
        raise ValueError('seed must be an integer')
    implementation = backend(domain, config)
    for atom in atoms:
        implementation.validate(atom)
    if len({a['id'] for a in atoms})!=len(atoms) or level>len(atoms):
        raise ValueError('Duplicate atom IDs or insufficient distinct atoms')
    bank={a['id']:a for a in atoms}
    if groups is not None:
        from collections import Counter
        for ids in groups:
            if len(ids)!=level or len(set(ids))!=level or any(i not in bank for i in ids):
                raise ValueError('Explicit candidate groups require distinct known atom IDs at the requested level')
            group=[bank[i] for i in ids]
            if max_per_source is not None and max(Counter(a['source_id'] for a in group).values())>max_per_source:
                raise ValueError('Explicit group violates source reuse cap')
            if implementation.directed:
                valid=all(implementation.compatible(a,b) for a,b in zip(group,group[1:]))
            else:
                if any(implementation.compatible(a,b)!=implementation.compatible(b,a) for a in group for b in group):
                    raise ValueError('Explicit undirected groups require symmetric compatibility')
                reachable={0}
                while True:
                    expanded=reachable|{j for i in reachable for j in range(level) if implementation.compatible(group[i],group[j])}
                    if expanded==reachable:break
                    reachable=expanded
                valid=len(reachable)==level
            if not valid:raise ValueError('Explicit candidate group violates graph compatibility')
    root = Path(output).resolve()
    if root.exists() and any(root.iterdir()):
        raise ValueError('Output must be new or empty; existing runs are never overwritten')
    root.mkdir(parents=True,exist_ok=True)
    source_files = sorted(Path(__file__).parent.glob('*.py')) + [Path(__file__).parent.parent/'graph.py']
    source_hash = digest({p.name:p.read_text(encoding='utf-8') for p in source_files})
    backend_path = inspect.getsourcefile(type(implementation))
    if not backend_path: raise ValueError('Backend must have inspectable source for provenance')
    backend_hash = digest(Path(backend_path).read_text(encoding='utf-8'))
    report = {'schema_version':1,'generator_version':'codewalk-composition-v1',
              'domain':domain,'level':level,'requested_tasks':count,'seed':seed,
              'atoms_sha256':digest(atoms),'config_sha256':digest(config),'complete':False,
              'implementation_sha256':source_hash,
              'backend':type(implementation).__module__+'.'+type(implementation).__qualname__,
              'backend_sha256':backend_hash,
              'candidate_groups_sha256':digest(groups) if groups is not None else None,
              'python':sys.version,'platform':platform.platform(),
              'accepted':[],'rejected':[],'blocked':None}
    seen = set()
    public_rows = []
    label_counts = {}
    singletons=sorted(atoms,key=lambda a:a['id'])
    random.Random(seed).shuffle(singletons)
    try:
        for attempt in range(max_candidates):
            try:
                if groups is not None:
                    if attempt>=len(groups):break
                    group=[bank[i] for i in groups[attempt]]
                elif level==1:
                    if attempt>=len(singletons):break
                    group=[singletons[attempt]]
                else:
                    group = sample_groups(atoms,implementation.compatible,level=level,count=1,
                                      seed=seed+attempt,directed=implementation.directed,
                                      max_attempts=100,max_per_source=max_per_source,
                                      lookahead=config.get('path_lookahead',False))[0]
            except ValueError as exc:
                # No compatible groups, or a bounded sampler failed; never fabricate tasks.
                report['rejected'].append({'reason':str(exc),'sampling_attempt':attempt})
                continue
            key = tuple(a['id'] for a in group)
            if key in seen:
                continue
            seen.add(key)
            task_id = f'{domain}-L{level}-{digest([group,config,source_hash,backend_hash])[:20]}'
            staging = root/'private'/'candidates'/task_id
            staging.mkdir(parents=True)
            runner = Runner(config)
            save(staging/'atoms.json',group)
            try:
                built = implementation.render(group,staging)
                if quotas is not None:
                    label = built.private.get('label')
                    used = label_counts.get(label,0)
                    if label not in quotas or used>=quotas[label]:
                        raise Reject('Candidate label does not fill a remaining quota')
                evidence = implementation.admit(built,runner)
                if evidence.get('atom_gate') is not True or evidence.get('reference_gate') is not True:
                    raise Reject('Backend did not establish both admission gates')
                files = built.public.get('files',{})
                if not files:
                    raise Reject('Backend produced no public task files')
                from ..data import safe_path
                publication = staging/'publication'
                if 'task.json' in files or 'task.json' in built.public.get('binary_files_base64',{}):
                    raise Reject('task.json is reserved for exported task metadata')
                for relative,content in files.items():
                    target = safe_path(publication,relative)
                    target.parent.mkdir(parents=True,exist_ok=True)
                    target.write_text(content,encoding='utf-8',newline='\n')
                import base64
                for relative,encoded in built.public.get('binary_files_base64',{}).items():
                    if relative in files: raise Reject('Binary/text file path collision')
                    target = safe_path(publication,relative)
                    target.parent.mkdir(parents=True,exist_ok=True)
                    target.write_bytes(base64.b64decode(encoded,validate=True))
                public = {**built.public,'task_id':task_id,'domain':domain}
                save(publication/'task.json',public)
                # Judge data, atoms, compiler logs and references remain under private/.
                save(staging/'judge.json',built.private)
                save(staging/'admission.json',evidence)
                destination = root/'tasks'/task_id
                destination.parent.mkdir(parents=True,exist_ok=True)
                publish_directory(publication,destination)
                report['accepted'].append({'task_id':task_id,'atom_ids':list(key),
                    'source_ids':[a['source_id'] for a in group],'public_sha256':digest(public),
                    'admission_sha256':digest(evidence)})
                label = built.private.get('label')
                label_counts[label] = label_counts.get(label,0)+1
                public_rows.append(public)
            except Reject as exc:
                report['rejected'].append({'task_id':task_id,'reason':str(exc)})
            finally:
                save(staging/'execution.json',runner.records)
            if len(public_rows) == count:
                report['complete'] = True
                break
    except InfrastructureError as exc:
        report['blocked'] = str(exc)
    finally:
        save(root/'manifest.json',report)
        filename = 'dataset.jsonl' if report['complete'] else 'dataset.partial.jsonl'
        (root/filename).write_text(''.join(canonical(row)+'\n' for row in public_rows),encoding='utf-8')
    return report
