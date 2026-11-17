"""Recover source-derived, restricted-grammar CodeComplex function atoms."""
import ast
import argparse
import concurrent.futures
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import warnings
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from codewalk.recovery.python_cost import analyze

LABELS={(0,0):'constant',(0,1):'logn',(1,0):'linear',(1,1):'nlogn',(2,0):'quadratic',(3,0):'cubic'}
WORKER='''import json,sys,copy
from pathlib import Path
p=json.loads(Path('probe.json').read_text());env={};exec(p['source'],env)
rows=[]
for value in p['inputs']:
 try:
  v=copy.deepcopy(value);result=env[p['entry']](v)
  if result is None:result=v
  json.dumps(result);rows.append({'input':value,'expected':result,'python_output_type':type(result).__name__})
 except Exception:pass
print(json.dumps(rows))
'''


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',default=str(ROOT/'outputs/source-recovery/bigo'))
    parser.add_argument('--selection',choices=('problem','function'),default='problem',
                        help='Function mode retains distinct real functions from a source problem; not the historical one-per-problem policy')
    args=parser.parse_args()
    out=Path(args.output).resolve();out.mkdir(parents=True,exist_ok=True)
    pin=json.loads((ROOT/'codewalk/recovery/upstreams.json').read_text(encoding='utf-8'))['codecomplex']
    raw=(ROOT/'outputs/source-recovery/upstream/CodeComplex/data/python_data.jsonl').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=pin['sha256']:raise ValueError('CodeComplex source revision/hash mismatch')
    rows=[json.loads(l) for l in raw.decode('utf-8').splitlines()]
    revision=pin['revision']
    candidates=[];seen=set()
    for index,row in enumerate(rows):
        try:
            with warnings.catch_warnings():warnings.simplefilter('ignore');tree=ast.parse(row['src'])
        except SyntaxError:continue
        for fn in tree.body:
            if not isinstance(fn,ast.FunctionDef) or len(fn.args.args)!=1 or fn.args.posonlyargs or fn.args.kwonlyargs or fn.args.vararg or fn.args.kwarg:continue
            source=ast.get_source_segment(row['src'],fn)+'\n'
            key=hashlib.sha256(ast.dump(fn,include_attributes=False).encode()).hexdigest()
            if key in seen:continue
            before=len(candidates)
            iterated={n.target.id for n in ast.walk(fn) if isinstance(n,ast.For) and isinstance(n.target,ast.Name)
                      and isinstance(n.iter,ast.Name) and n.iter.id==fn.args.args[0].arg}
            character_comparisons=any(isinstance(n,ast.Compare) and
                any(isinstance(c,ast.Constant) and isinstance(c.value,str) and len(c.value)==1 for c in ast.walk(n)) and
                any(isinstance(c,ast.Name) and c.id in iterated for c in ast.walk(n)) for n in ast.walk(fn))
            for mode in ('array','string','integer','matrix'):
                if character_comparisons and mode!='string':continue
                if mode=='matrix' and any(isinstance(c,ast.Call) and (
                    isinstance(c.func,ast.Name) and c.func.id=='sorted' or isinstance(c.func,ast.Attribute) and c.func.attr=='sort')
                    and not any(k.arg=='key' for k in c.keywords) for c in ast.walk(fn)):continue
                try:
                    cost=analyze(fn,mode)
                    if LABELS.get(cost)!=row['complexity']:continue
                    candidates.append((index,row,fn.name,source,key,mode,cost))
                except ValueError:pass
            if len(candidates)>before:seen.add(key)
    print(json.dumps({'restricted_source_candidates':len(candidates)}),flush=True)
    def recover(candidate):
        index,row,entry,source,key,mode,cost=candidate
        work=out/'probes'/f'{index}-{entry}-{mode}';work.mkdir(parents=True,exist_ok=True)
        if mode=='integer':inputs=[0,1,2,3,5,8,16,24,32,64]
        elif mode=='string':inputs=['','a','ab','aba','abcab','aaaaaa','zyxwvuts','(',')','()','(()))',
                                    '0','1','12','123','12345','112233','01234567','10101010']
        elif mode=='matrix':inputs=[[[((i*3+j)%7) for j in range(n)] for i in range(n)] for n in (0,1,2,3,5,8)]
        else:inputs=[[],[1],[2,1],[3,0,2],[2,1,0,3,2],[i%4 for i in range(8)],
                     [1,2,3],[5,2,7,1,4],[2,2,2,2],[8,7,6,5,4,3,2,1]]
        data={'source':source,'entry':entry,'inputs':inputs}
        (work/'probe.json').write_text(json.dumps(data),encoding='utf-8');(work/'check.py').write_text(WORKER,encoding='utf-8')
        result=subprocess.run([sys.executable,'-I','check.py'],cwd=work,capture_output=True,timeout=3)
        if result.returncode:raise ValueError('Function execution failed')
        cases=json.loads(result.stdout)
        if len(cases)<4:raise ValueError('Insufficient valid source cases')
        kinds={c.pop('python_output_type') for c in cases}
        if len(kinds)!=1:raise ValueError('Inconsistent Python return types')
        output_kind=next(iter(kinds))
        def typ(v):
            if type(v) is int:return 'int'
            if type(v) is bool:return 'bool'
            if isinstance(v,str):return 'str'
            if isinstance(v,list) and all(type(x) is int for x in v):return 'list[int]'
            if isinstance(v,list) and all(isinstance(x,list) and all(type(y) is int for y in x) for x in v):return 'list[list[int]]'
            raise ValueError('Unsupported return type')
        def output_typ(value):
            if output_kind=='tuple':return 'tuple['+','.join(typ(v) for v in value)+']'
            return typ(value)
        output_types={output_typ(c['expected']) for c in cases if c['expected']!=[]}
        if len(output_types)!=1:raise ValueError('Inconsistent return representation')
        output_type=next(iter(output_types))
        output_square=output_type=='list[list[int]]' and all(isinstance(c['expected'],list) and all(isinstance(row,list) and len(row)==len(c['expected']) for row in c['expected']) for c in cases)
        if output_square:output_type='SquareMatrix[int]'
        input_type={'array':'list[int]','matrix':'SquareMatrix[int]','string':'str','integer':'int'}[mode]
        input_size='constant' if mode=='integer' and cost==(0,0) else 'value' if mode=='integer' else 'length'
        output_size='length' if output_type in ('str','list[int]','list[list[int]]','SquareMatrix[int]') or output_type.startswith('tuple[') else 'constant'
        def size(v,measure):return 1 if measure=='constant' else len(v) if measure=='length' else v
        fits=[]
        for power in range(4):
            for coefficient in range(1,5):
                for offset in range(5):
                    if all(size(c['expected'],output_size)==coefficient*size(c['input'],input_size)**power+offset for c in cases):
                        fits.append({'power':power,'coefficient':coefficient,'offset':offset})
        if not fits:raise ValueError('No supported size-transfer fit')
        transfer=min(fits,key=lambda f:(f['power'],f['offset'],f['coefficient']))
        normalized=source+'\ndef run(value):\n    result = '+entry+'(value)\n    return value if result is None else result\n'
        if entry=='run':
            # Only the declaration is renamed; recursive entries are excluded by the grammar.
            renamed=source.replace('def run(', 'def _source_run(',1)
            normalized=renamed+'\ndef run(value):\n    result = _source_run(value)\n    return value if result is None else result\n';entry_name='run'
        else:entry_name='run'
        atom={'schema_version':1,'domain':'bigo','id':f'codecomplex-{row["problem"]}-{entry}-{key[:8]}-{mode}',
            'source_id':row['problem'],'provenance':{'uri':'https://github.com/sybaik1/CodeComplex','revision':revision,
                'license':'Upstream source redistribution terms not specified; retained for local research, not a license grant',
                'program_index':index,'program_sha256':hashlib.sha256(row['src'].encode()).hexdigest(),'original_program_label':row['complexity']},
            'payload':{'entry':entry_name,'source':normalized,'input_type':input_type,'output_type':output_type,
                'input_size':input_size,'output_size':output_size,'cost':{'n_power':cost[0],'log_power':cost[1]},
                'size_transfer':transfer,'cases':cases,
                'cost_evidence':'Restricted AST cost grammar matches original program label. Extracted function body preserved; size transfer empirically fitted on recorded source cases, not universally proven.'},
            'recovery':{'mode':mode,'raw_function':entry,'source_kind':'Actual CodeComplex function; safe adapter subset',
                        'historical_atomic_pool_reproduced':False}}
        if mode=='matrix':atom['payload']['input_shape']='square'
        if output_square:atom['payload']['output_shape']='square'
        return atom
    accepted=[];excluded=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        futures={pool.submit(recover,c):c[0] for c in candidates}
        for future in concurrent.futures.as_completed(futures):
            try:accepted.append(future.result())
            except Exception as exc:excluded.append({'program_index':futures[future],'reason':str(exc)})
    # Preserve all successful recoveries as evidence; selection never invents new functions.
    accepted.sort(key=lambda a:(a['source_id'],a['payload']['cost']['n_power']==0,a['recovery']['mode']=='integer',a['id']))
    (out/'validated-candidates.jsonl').write_text(''.join(json.dumps(a)+'\n' for a in accepted),encoding='utf-8')
    chosen={}
    for a in accepted:
        key=a['source_id'] if args.selection=='problem' else hashlib.sha256(a['payload']['source'].encode()).hexdigest()
        chosen.setdefault(key,a)
    atoms=sorted(chosen.values(),key=lambda a:a['id'])
    (out/'atoms.jsonl').write_text(''.join(json.dumps(a)+'\n' for a in atoms),encoding='utf-8')
    summary={'upstream_programs':len(rows),'restricted_candidates':len(candidates),'validated_source_atoms':len(atoms),
             'selection_policy':args.selection,'unique_source_problems':len({a['source_id'] for a in atoms}),
             'classes':{l:sum(a['provenance']['original_program_label']==l for a in atoms) for l in LABELS.values()},
             'excluded':excluded,'limitation':'Restricted grammar, empirical size fits and local-case checks; not the historical extraction pool.'}
    (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in summary.items() if k!='excluded'},indent=2))


if __name__=='__main__':main()
