"""Structured unary Verus atoms: same executable segments, reference-only annotations.

    The v1 renderer supports Copy scalar interfaces. It deliberately does not pretend to
    recover arbitrary Rust AST transformations or vector/borrow-heavy historical atoms.
"""
import re
from .base import Backend, BuiltTask, Reject, InfrastructureError, text

SCALARS = {'bool','u8','u16','u32','u64','usize','i8','i16','i32','i64','isize'}
BYPASS = re.compile(r'\b(?:assume|admit|external_body|exec_allows_no_decreases|external|axiom)\b')


class VerusBackend(Backend):
    name = 'verus'

    def validate(self,atom):
        super().validate(atom)
        p = atom['payload']
        if p.get('input_type') not in SCALARS or p.get('output_type') not in SCALARS:
            raise ValueError('Verus v1 atoms support unary Copy scalar types only')
        if not isinstance(p.get('ensures'),str) or not p['ensures']:
            raise ValueError('A stage predicate over x and result is required')
        if not isinstance(p.get('requires',[]),list): raise ValueError('requires must be a list')
        if not p.get('segments') or any(set(s) not in ({'exec'},{'proof'},{'annotation'}) for s in p['segments']):
            raise ValueError('Use structured exec/proof/annotation segments')
        code = str(p)
        if BYPASS.search(code): raise ValueError('Proof bypass or external code in normalized atom')
        # The adapter is responsible for classifying Rust tokens. Do not accept proof
        # syntax disguised as executable segments or annotations that replace code.
        for segment in p['segments']:
            key,value = next(iter(segment.items()))
            if not isinstance(value,str): raise ValueError('Segment source must be text')
            if key=='exec' and re.search(r'\b(?:proof|spec|ensures|requires|invariant|decreases)\b',value):
                raise ValueError('Separate executable code from proof annotations')
            if key=='annotation' and not re.match(r'^\s*(?:invariant|invariant_except_break|decreases)\b',value):
                raise ValueError('Only loop/termination annotations are supported')

    def source(self,stages,reference):
        chunks = ['use vstd::prelude::*;\nverus! {']
        for i,p in enumerate(stages):
            typ,out = p['input_type'],p['output_type']
            chunks.append(f'pub open spec fn step_{i}(x: {typ}, result: {out}) -> bool {{ {p["ensures"]} }}')
            chunks.append(f'pub fn stage_{i}(x: {typ}) -> (result: {out})')
            if p.get('requires'): chunks.append('    requires '+', '.join(p['requires'])+',')
            if reference: chunks.append(f'    ensures step_{i}(x, result),')
            chunks.append('{')
            for segment in p['segments']:
                key,value = next(iter(segment.items()))
                if key=='exec': chunks.append(value)
                elif reference: chunks.append(('proof { '+value+' }') if key=='proof' else value)
            chunks.append('}')
        outputs = [p['output_type'] for p in stages]
        tuple_type = '('+', '.join(outputs)+(',' if len(outputs)==1 else '')+')'
        chunks.append(f'pub fn chain_driver(input: {stages[0]["input_type"]}) -> (result: {tuple_type})')
        # The first stage's original precondition remains a driver precondition. Later
        # preconditions must follow from prior stages and be proven by Verus itself.
        if stages[0].get('requires'):
            requires = [re.sub(r'\bx\b','input',x) for x in stages[0]['requires']]
            chunks.append('    requires '+', '.join(requires)+',')
        conditions = [f'step_{i}('+('input' if i==0 else f'result.{i-1}')+f', result.{i})' for i in range(len(stages))]
        chunks.append('    ensures '+', '.join(conditions)+',')
        chunks.append('{')
        for i,_ in enumerate(stages):
            previous = 'input' if i==0 else f'v{i-1}'
            chunks.append(f'    let v{i} = stage_{i}({previous});')
            chunks.append(f'    assert(step_{i}({previous}, v{i}));')
        chunks.append('    ('+', '.join(f'v{i}' for i in range(len(stages)))+(',' if len(stages)==1 else '')+')')
        chunks.append('}\n}\nfn main() {}\n')
        return '\n'.join(chunks)

    def render(self,atoms,root):
        stages = [a['payload'] for a in atoms]
        reference = self.source(stages,True)
        unfinished = self.source(stages,False)
        text(root/'work'/'reference.rs',reference)
        text(root/'work'/'task.rs',unfinished)
        for i,p in enumerate(stages): text(root/'work'/f'atom-{i}.rs',self.source([p],True))
        return BuiltTask(root,{'files':{'task.rs':unfinished},
            'question':'Complete proof annotations and postconditions. Preserve executable code, preconditions, step predicates and chain_driver.',
            'protected':['executable segments','preconditions','step predicates','chain_driver']},
            {'reference_source':reference,'stages':len(stages),'renderer_contract':'structured unary Copy-scalar Verus v1'})

    def verify(self,runner,work,filename):
        command = self.config.get('verus_command',[self.config.get('verus','verus')])
        if not isinstance(command,list) or not command or any(not isinstance(x,str) for x in command):
            raise ValueError('verus_command must be a nonempty argument list')
        result = runner.run([*command,filename],work,name='verus-'+filename)
        combined = result['stdout']+'\n'+result['stderr']
        matches = re.findall(r'verification results::\s*(\d+) verified,\s*(\d+) errors',combined)
        if len(matches)!=1:
            raise InfrastructureError('Verus did not report verification counts (toolchain, parse or type failure)')
        verified,errors = map(int,matches[0])
        if (errors==0 and result['returncode']!=0) or (errors>0 and result['returncode']==0):
            raise InfrastructureError('Verus exit status disagrees with verification counts')
        return {'verified':verified,'errors':errors}

    def admit(self,built,runner):
        work = built.root/'work'
        command = self.config.get('verus_command',[self.config.get('verus','verus')])
        version = runner.run([*command,'--version'],work,name='verus-version')
        if version['returncode']!=0: raise InfrastructureError('Verus toolchain unavailable')
        atoms = [self.verify(runner,work,f'atom-{i}.rs') for i in range(built.private['stages'])]
        if any(r['errors'] for r in atoms): raise Reject('Atomic reference does not verify')
        reference = self.verify(runner,work,'reference.rs')
        if reference['errors']: raise Reject('Whole reference does not verify')
        unfinished = self.verify(runner,work,'task.rs')
        if not unfinished['errors']: raise Reject('Unfinished task already verifies')
        return {'atom_gate':True,'reference_gate':True,'atoms':atoms,'reference':reference,
                'unfinished':unfinished,'protected_source_generated_from_same_structured_atoms':True}
