"""Create trusted synthetic atoms and run the real four-domain generator.

No historical benchmark data or results are reproduced by these fixtures.
"""
import argparse
import difflib
import json
from pathlib import Path
import subprocess
import sys
from codewalk.composition import generate


def atom(domain,i,payload):
    return {'schema_version':1,'domain':domain,'id':f'fixture-{i:02d}',
        'source_id':f'fixture-source-{i:02d}',
        'provenance':{'uri':'urn:codewalk:synthetic-generation-demo','revision':'1','license':'MIT'},
        'payload':payload}


def patch(path,before,after):
    return f'diff --git a/{path} b/{path}\n'+('new file mode 100644\n' if not before else '')+''.join(difflib.unified_diff(
        before.splitlines(keepends=True),after.splitlines(keepends=True),
        fromfile='a/'+path if before else '/dev/null',tofile='b/'+path))


def prepare(domain,root,n=2):
    root = Path(root).resolve()
    root.mkdir(parents=True,exist_ok=True)
    if domain=='bigo':
        return [atom(domain,i,{'entry':'run','source':'def run(values):\n    return [x for x in values]\n',
            'input_type':'list[int]','output_type':'list[int]','input_size':'length','output_size':'length',
            'cost':{'n_power':1,'log_power':0},'size_transfer':{'power':1,'coefficient':1},
            'cost_evidence':'Synthetic source: one traversal, one output element per input element.',
            'cases':[{'input':[],'expected':[]},{'input':[1,2,3],'expected':[1,2,3]}]}) for i in range(n)]
    if domain=='codeclone':
        return [atom(domain,i,{'entry':'run','input_types':['int'],'output_type':'int',
            'a_members':'public static int run(int x) { return x + 1; }',
            'b_members':'public static int run(int x) { return x + '+('2' if i==n-1 else '1')+'; }',
            'label':'not_equivalent' if i==n-1 else 'equivalent',
            'suites':{'type_driven':[[-2],[0],[2]],'cross_substitution':[[1],[3]]},
            'suite_evidence':{'type_driven':'Synthetic integer-domain boundary examples.',
                              'cross_substitution':'Synthetic second suite; not an EvoSuite experiment.'}}) for i in range(n)]
    if domain=='verus':
        return [atom(domain,i,{'input_type':'u64','output_type':'u64','requires':[],
            'ensures':f'result == x / {i+2}', 'segments':[{'exec':f'x / {i+2}'}]}) for i in range(n)]
    if domain!='bugfixing': raise ValueError('Unknown domain')
    repo = root/'repository'
    repo.mkdir()
    source = ''
    for i in range(n):
        source += f'def f{i}(x):\n    return x - {i+1}\n\n'+''.join(f'padding_{i}_{j} = 0\n' for j in range(12))+'\n'
    (repo/'math_impl.py').write_text(source,encoding='utf-8',newline='\n')
    def git(*args):
        result = subprocess.run(['git','-C',str(repo),*args],capture_output=True,text=True,check=True)
        return result.stdout.strip()
    git('init','--quiet')
    git('add','math_impl.py')
    # Identity is local to this disposable synthetic repository, never the release repo.
    git('-c','user.name=CodeWalk synthetic fixture','-c','user.email=fixture@example.invalid',
        'commit','--quiet','-m','Synthetic buggy base')
    commit = git('rev-parse','HEAD')
    atoms = []
    for i in range(n):
        tests = f'from math_impl import f{i}\n\ndef test_f{i}():\n    assert f{i}(3) == {3+i+1}\n'
        repaired = source.replace(f'def f{i}(x):\n    return x - {i+1}',f'def f{i}(x):\n    return x + {i+1}')
        atoms.append(atom(domain,i,{'repository':str(repo),'base_commit':commit,
            'fix_time':f'2026-01-{i+1:02d}T00:00:00Z','modified_files':['math_impl.py'],
            'gold_patch':patch('math_impl.py',source,repaired),
            'test_patch':patch(f'tests/test_f{i}.py','',tests),'test_ids':[f'tests/test_f{i}.py::test_f{i}']}))
    return atoms


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('domain',choices=('bugfixing','verus','bigo','codeclone'))
    parser.add_argument('--output',required=True)
    parser.add_argument('--level',type=int,default=2)
    parser.add_argument('--config')
    args = parser.parse_args()
    root = Path(args.output).resolve()
    atoms = prepare(args.domain,root/'fixtures',args.level)
    (root/'atoms.jsonl').write_text(''.join(json.dumps(a)+'\n' for a in atoms),encoding='utf-8')
    config = json.loads(Path(args.config).read_text(encoding='utf-8')) if args.config else {}
    report = generate(args.domain,atoms,root/'generated',level=args.level,config=config)
    print(json.dumps(report,indent=2))
    if not report['complete']: sys.exit(2)


if __name__=='__main__': main()
