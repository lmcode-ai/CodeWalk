"""Recover real multi-argument CodeComplex functions under an explicit shared-n input contract."""
import argparse
import ast
import concurrent.futures
import hashlib
import itertools
import json
from pathlib import Path
import subprocess
import sys
import warnings

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from codewalk.recovery.python_cost import analyze

LABELS={(0,0):'constant',(0,1):'logn',(1,0):'linear',(1,1):'nlogn',(2,0):'quadratic',(3,0):'cubic'}
WORKER='''import copy,json
from pathlib import Path
p=json.loads(Path('probe.json').read_text());env={};exec(p['source'],env);rows=[]
for record in p['inputs']:
 try:
  result=env[p['entry']](*copy.deepcopy(record['args']))
  json.dumps(result);rows.append({'input':record,'expected':result,'kind':type(result).__name__})
 except Exception:pass
print(json.dumps(rows))
'''


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True)
    args=parser.parse_args();out=Path(args.output).resolve();out.mkdir(parents=True,exist_ok=True)
    pin=json.loads((ROOT/'codewalk/recovery/upstreams.json').read_text())['codecomplex']
    raw=(ROOT/'outputs/source-recovery/upstream/CodeComplex/data/python_data.jsonl').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=pin['sha256']:raise ValueError('Pinned upstream hash mismatch')
    candidates=[];seen=set()
    for index,row in enumerate(json.loads(l) for l in raw.decode().splitlines()):
        try:
            with warnings.catch_warnings():warnings.simplefilter('ignore');tree=ast.parse(row['src'])
        except SyntaxError:continue
        for fn in tree.body:
            if not isinstance(fn,ast.FunctionDef) or not 2<=len(fn.args.args)<=3:continue
            if fn.args.defaults or fn.args.posonlyargs or fn.args.kwonlyargs or fn.args.vararg or fn.args.kwarg or fn.decorator_list:continue
            key=hashlib.sha256(ast.dump(fn,include_attributes=False).encode()).hexdigest()
            if key in seen:continue
            try:cost=analyze(fn,'array')
            except ValueError:continue
            if LABELS.get(cost)!=row['complexity']:continue
            seen.add(key);source=ast.get_source_segment(row['src'],fn)+'\n'
            for layout in itertools.product(('array','integer','string'),repeat=len(fn.args.args)):
                candidates.append((index,row,fn.name,source,key,cost,layout))
    print(json.dumps({'candidates':len(candidates)}),flush=True)

    def recover(candidate):
        index,row,entry,source,key,cost,layout=candidate
        work=out/'probes'/f'{index}-{entry}-{"-".join(layout)}'
        work.mkdir(parents=True,exist_ok=True)
        inputs=[]
        for n in (0,1,2,3,5,8):
            for scalar_style in ('size','last','zero'):
                values=[]
                for kind in layout:
                    if kind=='array':values.append([1+(i%4) for i in range(n)])
                    elif kind=='string':values.append(('123abc'*2)[:n])
                    else:values.append(n if scalar_style=='size' else max(n-1,0) if scalar_style=='last' else 0)
                inputs.append({'n':n,'args':values})
        (work/'probe.json').write_text(json.dumps({'source':source,'entry':entry,'inputs':inputs}))
        (work/'check.py').write_text(WORKER)
        result=subprocess.run([sys.executable,'-I','check.py'],cwd=work,capture_output=True,timeout=2)
        if result.returncode:raise ValueError('Source execution failed')
        cases=json.loads(result.stdout)
        if len({c['input']['n'] for c in cases})<4:raise ValueError('Insufficient distinct input sizes')
        kinds={c.pop('kind') for c in cases}
        if len(kinds)!=1:raise ValueError('Inconsistent output representation')
        kind=next(iter(kinds))
        if kind not in ('int','bool','float','str','list','tuple'):raise ValueError('Unsupported output representation')
        def typ(v):
            if type(v) in (int,bool,float,str):return type(v).__name__
            if isinstance(v,list) and all(type(x) is int for x in v):return 'list[int]'
            raise ValueError('Unsupported output type')
        types={('tuple['+','.join(typ(v) for v in c['expected'])+']') if kind=='tuple' else typ(c['expected']) for c in cases}
        if len(types)!=1:raise ValueError('Inconsistent output type')
        output=next(iter(types));measure='length' if kind in ('str','list','tuple') else 'constant'
        fits=[]
        for power,coefficient,offset in itertools.product(range(4),range(1,5),range(5)):
            if all((len(c['expected']) if measure=='length' else 1)==coefficient*c['input']['n']**power+offset for c in cases):
                fits.append({'power':power,'coefficient':coefficient,'offset':offset})
        if not fits:raise ValueError('No supported size transfer')
        transfer=min(fits,key=lambda f:(f['power'],f['offset'],f['coefficient']))
        # Avoid shadowing a source function named run.
        adapter='codewalk_entry' if entry=='run' else 'run'
        normalized=source+'\ndef '+adapter+'(record):\n    return '+entry+'(*record["args"])\n'
        return {'schema_version':1,'domain':'bigo','id':f'codecomplex-multi-{index}-{key[:10]}-{"-".join(layout)}',
            'source_id':row['problem'],'provenance':{'uri':'https://github.com/sybaik1/CodeComplex','revision':pin['revision'],
                'license':'Upstream redistribution terms unverified; local recovery is not a license grant',
                'program_index':index,'program_sha256':hashlib.sha256(row['src'].encode()).hexdigest(),
                'original_program_label':row['complexity']},
            'payload':{'entry':adapter,'source':normalized,'input_type':'SharedArgs['+','.join(layout)+']','output_type':output,
                'input_size':'shared','output_size':measure,'input_contract':{'argument_layout':layout,
                    'n':'all sequence lengths equal n; integer arguments are between zero and n'},
                'cost':{'n_power':cost[0],'log_power':cost[1]},'size_transfer':transfer,'cases':cases,
                'cost_evidence':'Restricted AST cost upper-growth classification agrees with original program label; all arguments share n. Finite size-transfer checks are not a universal proof.'},
            'recovery':{'source_kind':'Actual multi-argument CodeComplex function with a fixed arity adapter','raw_function':entry}}

    accepted=[];excluded=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        futures={pool.submit(recover,c):c[0] for c in candidates}
        for future in concurrent.futures.as_completed(futures):
            try:accepted.append(future.result())
            except Exception as exc:excluded.append({'program_index':futures[future],'reason':str(exc)})
    accepted.sort(key=lambda a:a['id']);chosen={}
    for a in accepted:chosen.setdefault(a['source_id'],a)
    atoms=sorted(chosen.values(),key=lambda a:a['id'])
    (out/'atoms.jsonl').write_text(''.join(json.dumps(a)+'\n' for a in atoms))
    (out/'validated-candidates.jsonl').write_text(''.join(json.dumps(a)+'\n' for a in accepted))
    summary={'candidates':len(candidates),'accepted_variants':len(accepted),'unique_source_problems':len(atoms),'excluded':excluded}
    (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps({k:v for k,v in summary.items() if k!='excluded'}),flush=True)


if __name__=='__main__':main()
