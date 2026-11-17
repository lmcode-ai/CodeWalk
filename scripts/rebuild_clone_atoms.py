"""Rebuild real FEMPD atoms using recovered source/EvoSuite inputs and fresh execution."""
import concurrent.futures
import hashlib
import json
from pathlib import Path
import re
import sys
import argparse

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from codewalk.recovery.java import normalize,test_inputs,generated_inputs,unique
from codewalk.composition.java_clone import CloneBackend,invocation,stochastic_source
from codewalk.composition.base import Runner,InfrastructureError


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--config',required=True)
    args=parser.parse_args();config=json.loads(Path(args.config).read_text());config['timeout_seconds']=15
    out=ROOT/'outputs/source-recovery/clone';out.mkdir(parents=True,exist_ok=True)
    expected={};artifacts={}
    for level in (1,2,3):
        for row in json.loads((ROOT/f'data/codeclone/data/level_{level}.json').read_text(encoding='utf-8')):
            if level==1 or row['label']=='equivalent':
                for pair in row['component_pairids']:expected[pair]=row['label']
            for pair in row['component_pairids']:artifacts.setdefault(pair,[]).append(row['id'])
    failures=[];atoms=[]
    def recover(path):
        source=json.loads(path.read_text(encoding='utf-8'));pair=source['pair_id']
        if any(stochastic_source(m['source']) for m in source['methods']):raise ValueError('Unseeded randomness excluded from deterministic benchmark')
        destination=out/'atoms'/f'{pair}.json'
        if destination.exists():return json.loads(destination.read_text(encoding='utf-8'))
        sides=[normalize(m) for m in source['methods']]
        left,right=sides
        if left['input_types']!=right['input_types'] or left['output_type']!=right['output_type']:
            raise ValueError('Source signatures differ')
        types=left['input_types']
        original=unique([v for m in source['methods'] for v in test_inputs(m['evosuite'],types)])[:48]
        generated=generated_inputs(types,left['parameter_names'],pair,count=64)
        cases=unique(original+generated)
        if not cases:raise ValueError('No supported test inputs')
        label=expected.get(pair)
        if label is None:
            if source['upstream_consensus'] not in (0,1):raise ValueError('No supported label provenance')
            label='equivalent' if source['upstream_consensus']==1 else 'not_equivalent'
        atom={'schema_version':1,'domain':'codeclone','id':f'fempd-{pair}','source_id':f'fempd-pair-{pair}',
            'provenance':{'uri':'https://github.com/YoshikiHigo/FEMPDataset','revision':'original-SQLite-selected-records',
                'license':'MIT','pair_id':pair,'published_task_ids':artifacts[pair],
                'source_sha256':[hashlib.sha256(m['source'].encode()).hexdigest() for m in source['methods']]},
            'payload':{'entry':'run','input_types':types,'output_type':left['output_type'],
                'a_members':left['member'],'b_members':right['member'],'label':label,
                'imports':['java.util.*','java.security.*','java.math.*','java.text.*','java.io.*','java.nio.charset.*'],
                'suites':{'probe_1':cases[:1],'probe_2':cases[:1]},
                'suite_evidence':{'probe_1':'temporary execution probe','probe_2':'temporary execution probe'}}}
        work=out/'probes'/str(pair);work.mkdir(parents=True,exist_ok=True)
        built=CloneBackend(config).render([atom],work)
        checks=[]
        for i,values in enumerate(cases):
            a=invocation(0,'a',atom['payload'],values);b=invocation(0,'b',atom['payload'],values)
            checks.append(f'probe({i}, () -> {a}, () -> {b});')
        probe='''public class Probe {
static class R {Object v;boolean ex;R(Object v,boolean ex){this.v=v;this.ex=ex;}}
static R obs(java.util.concurrent.Callable<Object> f){try{return new R(f.call(),false);}catch(Throwable e){return new R(e.getClass().getSimpleName(),true);}}
static void probe(int i,java.util.concurrent.Callable<Object>a,java.util.concurrent.Callable<Object>b){R x=obs(a),y=obs(b);boolean eq=x.ex==y.ex&&java.util.Objects.deepEquals(x.v,y.v);System.out.println("CW_PROBE:"+i+":"+(eq?1:0)+":"+(!x.ex&&!y.ex?1:0));}
public static void main(String[]args)throws Exception{'''+'\n'.join(checks)+'\n}}\n'
        (work/'work/Probe.java').write_text(probe,encoding='utf-8',newline='\n')
        runner=Runner(config)
        sources=sorted(str(p.relative_to(work/'work')).replace('\\','/') for p in (work/'work').rglob('*.java'))
        result=runner.run([config['javac'],'-encoding','UTF-8','-d','classes',*sources],work/'work',name='compile-source-recovered-probe')
        if result['returncode']:raise ValueError('Recovered source does not compile in supported normalization')
        result=runner.run([config['java'],'-Xmx256m','-cp','classes','Probe'],work/'work',name='execute-recovered-differential-probe')
        if result['returncode']:raise ValueError('Source execution failed')
        observed={int(i):(eq=='1',normal=='1') for i,eq,normal in re.findall(r'CW_PROBE:(\d+):([01]):([01])',result['stdout'])}
        if len(observed)!=len(cases):raise ValueError('Incomplete differential evidence')
        differing=[i for i,(eq,normal) in observed.items() if not eq]
        normal=[i for i,(eq,ok) in observed.items() if ok]
        if not normal:raise ValueError('No nonexceptional paired execution')
        if label=='equivalent' and differing:raise ValueError('Published/source EQ label contradicted by execution')
        if label=='not_equivalent' and not differing:raise ValueError('No distinguishing witness for declared NEQ')
        witnesses=[cases[i] for i in differing[:4]]
        regression=unique(original+[cases[i] for i in normal[:4]]+witnesses)
        boundary=unique(generated+[cases[i] for i in normal[:4]]+witnesses)
        atom['payload']['suites']={'recovered_source_regression':regression,'regenerated_boundary':boundary}
        atom['payload']['suite_evidence']={
            'recovered_source_regression':'Literal inputs extracted from original left/right EvoSuite source; supplemented with verified normal inputs and differential witnesses.',
            'regenerated_boundary':'Fresh deterministic type/name-driven inputs seeded by pair ID; supplemented with verified normal inputs and differential witnesses. Not independent historical re-verification.'}
        atom['recovery']={'original_evosuite_inputs':len(original),'probed_inputs':len(cases),
            'normal_pairs':len(normal),'distinguishing_inputs':len(differing),'label_source':'surviving public artifact or original human consensus',
            'historical_suite_reproduced':False,'historical_source_recovered':True}
        (work/'execution.json').write_text(json.dumps(runner.records,indent=2),encoding='utf-8')
        destination.parent.mkdir(parents=True,exist_ok=True);destination.write_text(json.dumps(atom,indent=2)+'\n',encoding='utf-8')
        return atom
    files=list((ROOT/'outputs/source-recovery/fempd').glob('[0-9]*.json'))
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        futures={pool.submit(recover,p):p.stem for p in files}
        for future in concurrent.futures.as_completed(futures):
            try:atoms.append(future.result())
            except Exception as exc:failures.append({'pair_id':futures[future],'reason':str(exc)})
            if (len(atoms)+len(failures))%25==0:print(json.dumps({'validated_atoms':len(atoms),'excluded':len(failures)}),flush=True)
    atoms.sort(key=lambda a:a['id'])
    (out/'atoms.jsonl').write_text(''.join(json.dumps(a)+'\n' for a in atoms),encoding='utf-8')
    summary={'source_pairs':len(files),'validated_atoms':len(atoms),
        'labels':{label:sum(a['payload']['label']==label for a in atoms) for label in ('equivalent','not_equivalent')},
        'excluded':failures,'note':'Actual FEMPD methods recovered; regenerated differential admission, not historical exact suites.'}
    (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8');print(json.dumps({k:v for k,v in summary.items() if k!='excluded'},indent=2))


if __name__=='__main__':main()
