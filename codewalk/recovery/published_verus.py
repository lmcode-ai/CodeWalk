"""Recover references for published flat Verus tasks without rewriting their public inputs."""
from .rust import tokens,functions,replace_names,executable_projection,verus_body


def values(source):return tuple(t.value for t in tokens(source))


def rename_functions(source,mapping):
    """Rename local free-function identifiers without rewriting methods or qualified APIs."""
    ts=tokens(source);edits=[]
    for index,t in enumerate(ts):
        if t.value not in mapping:continue
        if index and ts[index-1].value=='.':continue
        if index>=2 and ts[index-1].value==ts[index-2].value==':':continue
        edits.append((t.start,t.end,mapping[t.value]))
    for start,end,value in sorted(edits,reverse=True):source=source[:start]+value+source[end:]
    return source


def requires(fn):
    ts=list(values(fn['header']))
    if 'requires' not in ts:return ()
    start=ts.index('requires')+1
    end=next((i for i in range(start,len(ts)) if ts[i] in ('ensures','decreases','recommends','returns')),len(ts))
    result=ts[start:end]
    while result and result[-1]==',':result.pop()
    return tuple(result)


def recover_reference(task,component_bodies):
    """Lift actual upstream proofs into the exact original stage namespaces.

    Component bodies omit the original public step predicates and driver; those
    blocks are preserved byte-for-byte from the published task. No public task
    bytes are changed. This constructs a candidate reference, not a proof claim.
    """
    body=verus_body(task);original=functions(body);edits=[];extra=[];used_aliases={}
    for index,source in enumerate(component_bodies,1):
        prefix=f'f{index}_';source_fns=functions(source)
        source_fns={k:v for k,v in source_fns.items() if k not in ('step1','chain_driver')}
        mapping={name:prefix+name for name in source_fns}
        renamed=rename_functions(source,mapping);reference=functions(renamed)
        # Published predicates can refer to an unprefixed copy of an upstream
        # recursive spec helper. Use that exact public definition in proof-only
        # annotations, rather than asking SMT to infer equality of two separately
        # named recursive functions. Both definitions must be token-identical
        # after namespace normalization; no new axiom or assumption is introduced.
        strip={value:key for key,value in mapping.items()}
        aliases={}
        for name,fn in reference.items():
            if not name.startswith(prefix) or 'spec' not in fn['prefix']:continue
            target=name[len(prefix):]
            if target not in original or 'spec' not in original[target]['prefix']:continue
            old=original[target]
            normalized=rename_functions(renamed[fn['start']:fn['end']],strip)
            if values(normalized)==values(body[old['start']:old['end']]):aliases[name]=target
        used_aliases.update(aliases)

        def reference_text(name):
            fn=reference[name];snippet=renamed[fn['start']:fn['end']]
            if not aliases or 'spec' in fn['prefix']:return snippet
            local=functions(snippet)[name];opening=local['body_start']
            header=snippet[:opening]
            post=next((t.start for t in tokens(header) if t.value=='ensures'),None)
            if post is not None:header=header[:post]+rename_functions(header[post:],aliases)
            proof_body=rename_functions(local['body'],aliases)
            if 'proof' not in fn['prefix'] and executable_projection(proof_body)!=executable_projection(local['body']):
                raise ValueError('Spec alias substitution would change executable tokens')
            return header+'{'+proof_body+'}'
        wanted={name for name in original if name.startswith(prefix)}
        if not wanted:raise ValueError('Published task has no functions in expected stage namespace')
        for name in sorted(wanted):
            if name not in reference:raise ValueError('No actual upstream reference for '+name)
            task_fn=original[name];ref_fn=reference[name]
            if values(task_fn['parameters'])!=values(ref_fn['parameters']) or requires(task_fn)!=requires(ref_fn):
                raise ValueError('Reference changes published parameters or preconditions: '+name)
            if 'spec' in task_fn['prefix']:
                if values(task_fn['body'])!=values(ref_fn['body']):raise ValueError('Reference changes a specification helper')
            elif 'proof' not in task_fn['prefix']:
                if executable_projection(task_fn['body'])!=executable_projection(ref_fn['body']):
                    raise ValueError('Reference changes published executable tokens: '+name)
            edits.append((task_fn['start'],task_fn['end'],reference_text(name)))
        # Restore proof/spec dependencies that annotation removal removed entirely.
        pending=list(wanted);required=set(wanted)
        while pending:
            name=pending.pop()
            for t in tokens(reference[name]['body']+' '+reference[name]['header']):
                if t.value in reference and t.value.startswith(prefix) and t.value not in required:
                    required.add(t.value);pending.append(t.value)
        for name in sorted(required-wanted):
            fn=reference[name]
            if 'spec' not in fn['prefix'] and 'proof' not in fn['prefix']:
                raise ValueError('Recovery would add an executable helper absent from the public task')
            extra.append(reference_text(name))
    recovered=body
    for start,end,replacement in sorted(edits,reverse=True):recovered=recovered[:start]+replacement+recovered[end:]
    recovered+='\n'+'\n'.join(extra)+'\n'
    recovered_fns=functions(recovered)
    protected=[name for name in original if name=='chain_driver' or name.startswith('step')]
    for name in protected:
        old,new=original[name],recovered_fns[name]
        if body[old['start']:old['end']]!=recovered[new['start']:new['end']]:
            raise ValueError('Protected predicate or driver changed')
    start=task.index(body);result=task[:start]+recovered+task[start+len(body):]
    # Original imports may rely on a different prelude version; reference-only
    # imports do not alter public source or verification specifications.
    if 'use vstd::prelude::*;' in result:
        result=result.replace('use vstd::prelude::*;','use vstd::prelude::*;\nuse vstd::math::{max,min};',1)
    return result,{'stages':len(component_bodies),'protected_blocks_preserved':protected,
                   'executable_tokens_preserved':True,'preconditions_preserved':True,
                   'new_proof_or_spec_helpers':len(extra),'identical_public_spec_aliases':used_aliases,
                   'reference_verified':False}
