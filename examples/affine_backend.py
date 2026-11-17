"""Complete extension of the canonical composition Backend interface."""
import argparse
import json
from pathlib import Path
from codewalk.composition import generate
from codewalk.composition.base import Backend, BuiltTask, Reject, save, text
from codewalk.composition.registry import BACKENDS


class AffineBackend(Backend):
    name = 'affine'
    directed = True

    def validate(self,atom):
        super().validate(atom)
        if any(type(atom['payload'].get(k)) is not int for k in ('a','b')):
            raise ValueError('Affine atoms need integer a and b')

    def compatible(self,left,right):
        return True  # Every generated integer -> integer function can feed the next.

    def render(self,atoms,root):
        stages=[a['payload'] for a in atoms]
        a,b=1,0
        for stage in stages: a,b=stage['a']*a,stage['a']*b+stage['b']
        files={f'stage_{i}.py':f'def run(x):\n    return {p["a"]} * x + {p["b"]}\n'
               for i,p in enumerate(stages)}
        files['driver.py']='\n'.join(f'from stage_{i} import run as f{i}' for i in range(len(stages)))+'\n\ndef run(x):\n'+''.join(
            f'    x = f{i}(x)\n' for i in range(len(stages)))+'    return x\n'
        for name,content in files.items(): text(root/'work'/name,content)
        save(root/'work'/'expected.json',{'coefficients':[a,b],'stages':stages})
        text(root/'work'/'check.py', '''import json,sys,importlib
from pathlib import Path
root=Path(__file__).parent; sys.path.insert(0,str(root))
expected=json.loads((root/'expected.json').read_text())
import driver
valid=True
for i,p in enumerate(expected['stages']):
    fn=importlib.import_module('stage_'+str(i)).run
    valid &= all(fn(x)==p['a']*x+p['b'] for x in (0,1))
a,b=expected['coefficients']
valid &= all(driver.run(x)==a*x+b for x in (0,1))
print(json.dumps({'valid':valid}));sys.exit(0 if valid else 1)
''')
        return BuiltTask(root,{'files':files,'question':'Return coefficients [A,B] of driver.run(x) = A*x+B.'},
                         {'coefficients':[a,b]})

    def admit(self,built,runner):
        if built.private['coefficients']==[1,0]: raise Reject('Composed task equals the unfinished identity baseline')
        checked=runner.run(['$PYTHON','-I','check.py'],built.root/'work',name='affine-exact-coefficient-check')
        if checked['returncode'] or json.loads(checked['stdout']).get('valid') is not True:
            raise Reject('Affine atomic/reference execution failed')
        return {'atom_gate':True,'reference_gate':True,
            'oracle':'Canonical integer affine syntax is closed under composition; values at 0 and 1 establish exact coefficient equality.'}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',required=True)
    args=parser.parse_args()
    BACKENDS[AffineBackend.name]=AffineBackend
    atoms=[{'schema_version':1,'domain':'affine','id':name,'source_id':name,
        'provenance':{'uri':'urn:codewalk:affine-example','revision':'1','license':'MIT'},
        'payload':{'a':a,'b':b}} for name,a,b in [('scale',2,0),('shift',1,3)]]
    report=generate('affine',atoms,Path(args.output),level=2)
    print(json.dumps(report,indent=2))
    if not report['complete']: raise SystemExit(2)


if __name__=='__main__': main()
