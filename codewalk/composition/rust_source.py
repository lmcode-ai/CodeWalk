"""Recompose surviving real Verus tasks with recovered upstream reference proofs."""
import re
import functools
import hashlib
import json
import os
from pathlib import Path
import uuid
from .base import Backend,BuiltTask,Reject,InfrastructureError,text,canonical
from .rust_proof import VerusBackend,SCALARS,BYPASS
from ..recovery.rust import replace_names,publicize,functions,executable_projection,contract,tokens

PRIMITIVES=SCALARS|{'char'}


@functools.lru_cache(maxsize=16)
def toolchain_hash(files):
    return hashlib.sha256(b''.join(Path(path).read_bytes() for path,_,_ in files)).hexdigest()


def vector(typ):
    return bool(re.fullmatch(r'&?Vec<(?:'+ '|'.join(PRIMITIVES)+')>',typ) or
                re.fullmatch(r'&\[(?:'+ '|'.join(PRIMITIVES)+r')\]',typ))


def spec_type(typ):
    if typ in PRIMITIVES:return typ
    if typ.startswith('Vec<'):return 'Seq<'+typ[4:]
    raise ValueError('Unsupported recovered return type')


def bind(output,inputs):
    for i,(_,typ) in enumerate(inputs):
        if output==typ and output in PRIMITIVES:return i,'direct'
        if typ=='&'+output:return i,'borrow'
        if output.startswith('Vec<') and typ=='&['+output[4:-1]+']':return i,'slice'
    return None


class SourceVerusBackend(VerusBackend):
    name='verus'

    def validate(self,atom):
        Backend.validate(self,atom)
        p=atom['payload']
        if p.get('mode')!='source_recovered' or p.get('executable_tokens_match') is not True:
            raise ValueError('Recovered Verus atoms require matched executable projections')
        if BYPASS.search(p['reference_body']) or BYPASS.search(p['task_body']):raise ValueError('Proof bypass in recovered source')
        task_functions=functions(p['task_body']);reference_functions=functions(p['reference_body'])
        if not p.get('standalone_only') and canonical(contract(task_functions['chain_driver']))!=canonical(p['contract']):
            raise ValueError('Recovered driver metadata does not match actual task source')
        for name,fn in task_functions.items():
            if name=='chain_driver' or name=='step1':
                if name not in reference_functions or [t.value for t in tokens(p['task_body'][fn['start']:fn['end']])]!=[t.value for t in tokens(p['reference_body'][reference_functions[name]['start']:reference_functions[name]['end']])]:
                    raise ValueError('Fixed predicate/driver differs between task and reference')
            elif 'spec' not in fn['prefix'] and 'proof' not in fn['prefix']:
                if name not in reference_functions or executable_projection(fn['body'])!=executable_projection(reference_functions[name]['body']):
                    raise ValueError('Executable helper differs between task and reference')
            elif 'spec' in fn['prefix']:
                if name not in reference_functions or [t.value for t in tokens(fn['body'])]!=[t.value for t in tokens(reference_functions[name]['body'])]:
                    raise ValueError('Specification helper meaning differs between task and reference')
        if p.get('standalone_only'):return
        for _,typ in p['contract']['parameters']:
            if typ not in PRIMITIVES and not vector(typ):raise ValueError('Unsupported recovered input type')
        spec_type(p['contract']['output_type'])

    def compatible(self,a,b):
        if a['payload'].get('standalone_only') or b['payload'].get('standalone_only'):return False
        contract=b['payload']['contract']
        binding=bind(a['payload']['contract']['output_type'],contract['parameters'])
        if binding and self.config.get('conservative_bindings',False):
            from ..recovery.rust import tokens
            bound_name=contract['parameters'][binding[0]][0]
            if bound_name in {t.value for t in tokens(contract['requires'])}:return False
        return binding is not None

    def verify(self,runner,work,filename):
        if filename!='task.rs':
            cache=None
            # Only atomic references are cached. Full composite references and
            # unfinished public tasks are always checked for every candidate.
            if filename.startswith('atom-') and self.config.get('atomic_reference_cache'):
                executable=Path(self.config.get('verus','verus')).resolve()
                files=[p for p in (executable,executable.parent/'rust_verify.exe',executable.parent/'vstd.vir') if p.is_file()]
                if executable not in files:raise InfrastructureError('Cannot fingerprint Verus cache toolchain')
                fingerprint=toolchain_hash(tuple((str(p),p.stat().st_size,p.stat().st_mtime_ns) for p in files))
                key=hashlib.sha256((work/filename).read_bytes()+fingerprint.encode()+
                    canonical({k:v for k,v in self.config.items() if k!='atomic_reference_cache'}).encode()).hexdigest()
                cache=Path(self.config['atomic_reference_cache'])/(key+'.json')
                if cache.exists():
                    saved=json.loads(cache.read_text())
                    if saved.get('key')==key and saved['result'].get('errors')==0 and saved['result'].get('verified',0)>0:
                        runner.records.append({'name':'cached-atomic-proof','key':key,'toolchain_sha256':fingerprint,
                                               'source_sha256':hashlib.sha256((work/filename).read_bytes()).hexdigest(),
                                               'original_execution':saved['execution']})
                        return saved['result']
            try:
                result=super().verify(runner,work,filename)
                if cache is not None and result['errors']==0 and result['verified']>0:
                    cache.parent.mkdir(parents=True,exist_ok=True)
                    temp=cache.with_suffix('.'+uuid.uuid4().hex+'.tmp')
                    temp.write_text(json.dumps({'key':key,'result':result,'execution':runner.records[-1]}))
                    os.replace(temp,cache)
                return result
            except InfrastructureError:
                last=runner.records[-1] if runner.records else {}
                if last.get('returncode')==1 and re.search(r'^error(?:\[.*?\])?:',last.get('stderr',''),re.M):
                    raise Reject('Recovered composition rejected by Rust/Verus elaboration')
                raise
        command=self.config.get('verus_command',[self.config.get('verus','verus')])
        typed=runner.run([*command,'--no-verify',filename],work,name='verus-unfinished-typecheck-only')
        if typed['returncode']!=0:raise Reject('Unfinished source does not typecheck')
        result=runner.run([*command,filename],work,name='verus-'+filename)
        combined=result['stdout']+'\n'+result['stderr']
        counts=re.findall(r'verification results::\s*(\d+) verified,\s*(\d+) errors',combined)
        if len(counts)==1:
            verified,errors=map(int,counts[0])
            if result['returncode'] not in (0,1) or bool(errors)==(result['returncode']==0):
                raise Reject('Task verifier exit/count mismatch')
            return {'verified':verified,'errors':errors}
        diagnostics=re.findall(r'^error: (.+)$',combined,re.M)
        termination=[d for d in diagnostics if d.strip() in (
            'loop must have a `decreases` clause','loop must have a decreases clause')]
        if result['returncode']==1 and termination and all(d in termination or d.startswith('aborting due to ') for d in diagnostics):
            # This is a precise missing proof-annotation error, not arbitrary parse/type failure.
            return {'verified':0,'errors':len(termination),'failure_kind':'missing loop termination annotation',
                    'note':'Current Verus reports this proof obligation before final verification counts.'}
        raise Reject('Unfinished source has unsupported parse/type/toolchain diagnostics')

    def source(self,stages,reference):
        chunks=['use vstd::prelude::*;']
        for i,p in enumerate(stages):
            body=p['reference_body'] if reference else p['task_body']
            chunks.append(f'pub mod s{i} {{ use vstd::prelude::*; use vstd::math::{{max,min}};\nverus! {{\n'+publicize(body)+'\n}\n}\n')
        parameters=[];pre=[];body=[];conditions=[];existentials=[]
        for i,p in enumerate(stages):
            c=p['contract'];params=c['parameters']
            binding=None if i==0 else bind(stages[i-1]['contract']['output_type'],params)
            if i and binding is None:raise Reject('No real typed binding')
            args=[];header_map={};body_map={};header_logical=set();body_logical=set()
            for j,(name,typ) in enumerate(params):
                if binding and j==binding[0]:
                    previous=f'x{i-1}';logical=f'v{i}'
                    value=previous if binding[1]=='direct' else '&'+previous if binding[1]=='borrow' else previous+'.as_slice()'
                    header_map[name]=logical
                    if vector(typ):header_logical.add(name)
                else:
                    value=f'p{i}_{name}';parameters.append(value+': '+typ)
                    header_map[name]=value
                args.append(value)
                if vector(typ):
                    ghost=f'g{i}_{j}'
                    view=f'x{i-1}@' if binding and j==binding[0] else f'({value})@'
                    body.append(f'let ghost {ghost} = {view};')
                    body_map[name]=ghost;body_logical.add(name)
                else:body_map[name]=value
            if c['requires']:
                # Conditions on the bound input must follow from earlier guarantees.
                # External-only conditions can remain public driver preconditions.
                bound_name=params[binding[0]][0] if binding else None
                from ..recovery.rust import tokens
                mentions={t.value for t in tokens(c['requires'])}
                if bound_name is None or bound_name not in mentions:
                    pre.append(replace_names(c['requires'],header_map,header_logical))
            body.append(f'let x{i} = s{i}::chain_driver('+', '.join(args)+');')
            out=c['output_type'];out_logical=vector(out)
            current=f'v{i+1}'
            body.append('let ghost '+current+' = '+f'x{i}'+('@' if out_logical else '')+';')
            header_map[c['return_name']]='r_final' if i==len(stages)-1 else current
            if out_logical and i<len(stages)-1:header_logical.add(c['return_name'])
            body_map[c['return_name']]=current
            if out_logical:body_logical.add(c['return_name'])
            qualified={'step1':f's{i}::step1'}
            condition=replace_names(c['ensures'],{**header_map,**qualified},header_logical)
            bodycondition=replace_names(c['ensures'],{**body_map,**qualified},body_logical)
            conditions.append('('+condition+')')
            body.append('assert('+bodycondition+');')
            if i<len(stages)-1:existentials.append(current+': '+spec_type(out))
        final=stages[-1]['contract']['output_type']
        result=' && '.join(conditions)
        if existentials:result='exists|'+', '.join(existentials)+'| '+result
        chunks.append('verus! {\nfn chain_driver('+', '.join(parameters)+') -> (r_final: '+final+')')
        if pre:chunks.append('requires '+', '.join(pre)+',')
        chunks.append('ensures '+result+',\n{\n'+'\n'.join(body)+f'\nx{len(stages)-1}\n'+'}\n}\nfn main() {}\n')
        return '\n'.join(chunks)

    def render(self,atoms,root):
        stages=[a['payload'] for a in atoms]
        standalone=any(p.get('standalone_only') for p in stages)
        if standalone and len(stages)!=1:raise Reject('Standalone recovered sources cannot be composed into a chain')
        def single(p,reference):
            return 'use vstd::prelude::*;\nuse vstd::math::{max,min};\nverus! {\n'+p['reference_body' if reference else 'task_body']+'\n}\nfn main() {}\n'
        reference=single(stages[0],True) if standalone else self.source(stages,True)
        task=single(stages[0],False) if standalone else self.source(stages,False)
        text(root/'work/reference.rs',reference);text(root/'work/task.rs',task)
        for i,p in enumerate(stages):text(root/'work'/f'atom-{i}.rs',single(p,True) if standalone else self.source([p],True))
        return BuiltTask(root,{'files':{'task.rs':task},
            'question':'Complete the missing proof annotations. Preserve executable code, preconditions, all fixed step predicates and drivers.',
            'protected':['all module stage predicates','all module drivers','outer chain_driver','executable code','preconditions']},
            {'reference_source':reference,'stages':len(stages),'renderer_contract':'source-recovered Verus modules with original final-return shape'})
