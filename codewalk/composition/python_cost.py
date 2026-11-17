"""Python unary-chain renderer with an explicit source-annotation complexity oracle."""
import ast
import json
from pathlib import Path
from .base import Backend, BuiltTask, Reject, InfrastructureError, save, text, identifier


WORKER = '''import importlib.util,json,sys,copy
from pathlib import Path
root=Path(__file__).parent
spec=json.loads((root/'checks.json').read_text())
functions=[]
def size(x,kind):
    if kind=='length': return len(x)
    if kind=='value' and type(x) is int and x>=0: return x
    if kind=='constant': return 1
    if kind=='shared' and isinstance(x,dict) and type(x.get('n')) is int and x['n']>=0: return x['n']
    raise ValueError('Unsupported size measure or input')
def square(x): return isinstance(x,list) and all(isinstance(r,list) and len(r)==len(x) for r in x)
def shared(x,stage):
    if stage['input_size']!='shared':return
    n=size(x,'shared');args=x.get('args');layout=stage['input_contract']['argument_layout']
    if not isinstance(args,list) or len(args)!=len(layout):raise ValueError('Shared argument arity mismatch')
    for value,kind in zip(args,layout):
        if kind=='integer':
            if type(value) is not int or not 0<=value<=n:raise ValueError('Scalar violates shared n bound')
        elif kind=='array':
            if not isinstance(value,list) or len(value)!=n or any(type(v) is not int for v in value):raise ValueError('Array violates shared n contract')
        elif kind=='string':
            if not isinstance(value,str) or len(value)!=n:raise ValueError('String violates shared n contract')
        else:raise ValueError('Unsupported shared argument layout')
try:
    for i,stage in enumerate(spec['stages']):
        module_spec=importlib.util.spec_from_file_location('stage_'+str(i),root/('stage_'+str(i)+'.py'))
        module=importlib.util.module_from_spec(module_spec); module_spec.loader.exec_module(module)
        fn=getattr(module,stage['entry']); functions.append(fn)
        for case in stage['cases']:
            shared(case['input'],stage)
            if stage.get('input_shape')=='square' and not square(case['input']): raise ValueError('Non-square matrix input')
            result=fn(copy.deepcopy(case['input']))
            if stage.get('output_shape')=='square' and not square(result): raise ValueError('Non-square matrix output')
            root_type=stage['output_type'].split('[',1)[0]
            if root_type in ('tuple','list','int','bool','str','float') and type(result).__name__!=root_type: raise ValueError('Atomic output representation mismatch')
            if json.dumps(result,sort_keys=True)!=json.dumps(case['expected'],sort_keys=True): raise ValueError('Atomic reference test failed')
            expected=stage['size_transfer']['coefficient']*size(case['input'],stage['input_size'])**stage['size_transfer']['power']+stage['size_transfer'].get('offset',0)
            if size(result,stage['output_size'])!=expected: raise ValueError('Size transfer test failed')
    sys.path.insert(0,str(root))
    import driver
    for case in spec['stages'][0]['cases']:
        value=copy.deepcopy(case['input'])
        for stage,fn in zip(spec['stages'],functions):
            shared(value,stage)
            if stage.get('input_shape')=='square' and not square(value): raise ValueError('Composite violates square-matrix input contract')
            incoming=copy.deepcopy(value); value=fn(value)
            if stage.get('output_shape')=='square' and not square(value): raise ValueError('Composite violates square-matrix output contract')
            expected=stage['size_transfer']['coefficient']*size(incoming,stage['input_size'])**stage['size_transfer']['power']+stage['size_transfer'].get('offset',0)
            if size(value,stage['output_size'])!=expected: raise ValueError('Composite size transfer test failed')
        if driver.run(copy.deepcopy(case['input']))!=value: raise ValueError('Driver differs from ordered execution')
    print(json.dumps({'valid':True,'atomic_cases':sum(len(s['cases']) for s in spec['stages']),
                      'composite_cases':len(spec['stages'][0]['cases'])}))
except Exception as exc:
    print(json.dumps({'valid':False,'reason':type(exc).__name__+': '+str(exc)})); sys.exit(1)
'''


def derive(stages):
    """Compose exact monomial size annotations, then sum costs by dominance.

    Costs are Theta(n^p log(n)^q) annotations, not inferred from arbitrary Python.
    Powers/coefficient are nonnegative integer and positive integer respectively.
    """
    size_power = 1
    costs = []
    for stage in stages:
        p = stage['cost']['n_power'] * size_power
        q = stage['cost']['log_power'] if size_power else 0
        costs.append((p,q))
        size_power *= stage['size_transfer']['power']
    dominant = max(costs)
    labels = {(0,0):'constant',(0,1):'logn',(1,0):'linear',(1,1):'nlogn',
              (2,0):'quadratic',(3,0):'cubic'}
    if dominant not in labels:
        raise Reject(f'Unsupported derived complexity n^{dominant[0]} log(n)^{dominant[1]}')
    return {'label':labels[dominant],'stage_costs':[list(c) for c in costs],
            'final_size_power':size_power,'oracle':'source-annotated polynomial/log cost algebra'}


class ComplexityBackend(Backend):
    name = 'bigo'

    def validate(self, atom):
        super().validate(atom)
        p = atom['payload']
        identifier(p['entry'])
        tree = ast.parse(p['source'])
        functions = [n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name==p['entry']]
        if len(functions)!=1 or len(functions[0].args.args)!=1 or functions[0].args.vararg or functions[0].args.kwarg:
            raise ValueError('Complexity atoms require one top-level unary entry function')
        for k in ('input_type','output_type','cost_evidence'):
            if not isinstance(p.get(k),str) or not p[k]: raise ValueError(f'Missing {k}')
        for k in ('input_size','output_size'):
            if p.get(k) not in ('length','value','constant','shared'): raise ValueError('Unsupported size measure')
        if p['input_size']=='shared':
            layout=p.get('input_contract',{}).get('argument_layout')
            if not isinstance(layout,(list,tuple)) or not layout or any(k not in ('array','integer','string') for k in layout):
                raise ValueError('Shared n input requires an explicit supported argument layout')
        if p['output_size']=='shared':raise ValueError('Shared n records are supported only as explicit root inputs')
        for obj,keys in ((p['cost'],('n_power','log_power')),(p['size_transfer'],('power','coefficient'))):
            if any(type(obj.get(k)) is not int or obj[k]<0 for k in keys):
                raise ValueError('Cost/size powers must be nonnegative integers')
        if p['size_transfer']['coefficient']<1: raise ValueError('Size coefficient must be positive')
        if type(p['size_transfer'].get('offset',0)) is not int or p['size_transfer'].get('offset',0)<0:
            raise ValueError('Size offset must be a nonnegative integer')
        if not p.get('cases') or any(set(case)!= {'input','expected'} for case in p['cases']):
            raise ValueError('Atomic input/expected cases required')

    def compatible(self,a,b):
        return super().compatible(a,b) and a['payload']['output_size']==b['payload']['input_size']

    def render(self, atoms, root):
        stages = [a['payload'] for a in atoms]
        derivation = derive(stages)
        atomic_dominant=max((p['cost']['n_power'],p['cost']['log_power']) for p in stages)
        composed_dominant=max(tuple(c) for c in derivation['stage_costs'])
        nontrivial=len(stages)==1 or composed_dominant!=atomic_dominant
        if self.config.get('require_nontrivial_composition',False) and not nontrivial:
            raise Reject('Paper complexity admission requires the composed class to differ from the dominant atomic class (N > 1)')
        derivation['paper_nontriviality']={'applicable':len(stages)>1,'passed':nontrivial,
            'dominant_atomic_cost':list(atomic_dominant),'enforced':self.config.get('require_nontrivial_composition',False)}
        files = {f'stage_{i}.py':p['source'] for i,p in enumerate(stages)}
        imports = '\n'.join(f'from stage_{i} import {p["entry"]} as stage_{i}' for i,p in enumerate(stages))
        body = '\n'.join(f'    value = stage_{i}(value)' for i in range(len(stages)))
        files['driver.py'] = imports+'\n\ndef run(value):\n'+body+'\n    return value\n'
        for name,content in files.items(): text(root/'work'/name,content)
        text(root/'work'/'check.py',WORKER)
        save(root/'work'/'checks.json',{'stages':stages})
        return BuiltTask(root,{'files':files,'question':'Select the overall worst-case complexity of driver.run under input_contract; n uses the declared size measure.',
            'input_contract':{'type':stages[0]['input_type'],'size_measure':stages[0]['input_size'],
                              'shape':stages[0].get('input_shape'),
                              'details':stages[0].get('input_contract')},
            'labels':['constant','logn','linear','nlogn','quadratic','cubic','np']},
            {'label':derivation['label'],'derivation':derivation,'atomic_cost_evidence':[p['cost_evidence'] for p in stages]})

    def admit(self, built, runner):
        result = runner.run(['$PYTHON','-I','check.py'],built.root/'work',name='python-atomic-and-composite-tests')
        try: checked = json.loads(result['stdout'])
        except json.JSONDecodeError as exc:
            raise Reject('Python test harness did not produce valid evidence') from exc
        if result['returncode']!=0 or checked.get('valid') is not True:
            raise Reject(checked.get('reason','Python reference tests failed'))
        return {'atom_gate':True,'reference_gate':True,'tests':checked,
                'derivation':built.private['derivation'],
                'limitation':'Cost annotations are trusted upstream evidence; finite tests do not prove asymptotic bounds.'}
