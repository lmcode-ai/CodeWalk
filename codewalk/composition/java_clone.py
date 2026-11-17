"""Java clone composition: legacy aggregation by default; unary data-flow optional."""
import json
import re
from .base import Backend, BuiltTask, Reject, InfrastructureError, identifier, text

TYPES = {'boolean','byte','short','int','long','float','double','char','String'}


def stochastic_source(source):
    return bool(re.search(r'\bnew\s+(?:java\.util\.)?Random\s*\(\s*\)|\bnew\s+(?:java\.security\.)?SecureRandom\s*\(|\bMath\s*\.\s*random\s*\(|\bThreadLocalRandom\s*\.\s*current\s*\(|\bUUID\s*\.\s*randomUUID\s*\(|\bSystem\s*\.\s*(?:nanoTime|currentTimeMillis)\s*\(',source))


def java_type(kind):
    base = kind[:-2] if kind.endswith('[]') else kind
    if base not in TYPES: raise ValueError(f'Unsupported Java type: {kind}')
    return kind


def literal(value, kind):
    java_type(kind)
    if kind.endswith('[]'):
        if not isinstance(value,list): raise ValueError('Array input must be a JSON array')
        return 'new '+kind+'{'+','.join(literal(v,kind[:-2]) for v in value)+'}'
    if kind=='String':
        if value is None: return 'null'
        if not isinstance(value,str): raise ValueError('String input required')
        return json.dumps(value,ensure_ascii=True)
    if kind=='boolean':
        if type(value) is not bool: raise ValueError('Boolean input required')
        return str(value).lower()
    if kind=='char':
        if not isinstance(value,str) or len(value)!=1 or ord(value)>65535: raise ValueError('One UTF-16 char required')
        return '(char)'+str(ord(value))
    if kind in ('byte','short','int','long'):
        bits = {'byte':8,'short':16,'int':32,'long':64}[kind]
        if type(value) is not int or not -(2**(bits-1))<=value<2**(bits-1): raise ValueError('Integer out of range')
        return f'({kind})({value}{"L" if kind=="long" else ""})'
    if type(value) not in (int,float) or not __import__('math').isfinite(value): raise ValueError('Finite numeric input required')
    return repr(float(value))+('f' if kind=='float' else 'd')


def invocation(stage, side, p, values):
    args = ','.join(literal(v,t) for v,t in zip(values,p['input_types']))
    return f'cw.stage_{stage}.{side}.Atom.{p["entry"]}({args})'


def observed(expression):
    return 'obs(() -> '+expression+')'


class CloneBackend(Backend):
    name = 'codeclone'

    def __init__(self, config):
        super().__init__(config)
        self.mode = config.get('clone_mode','aggregation')
        if self.mode not in ('aggregation','chain'): raise ValueError('clone_mode must be aggregation or chain')
        self.directed = self.mode=='chain'

    def validate(self, atom):
        super().validate(atom)
        p = atom['payload']
        identifier(p['entry'])
        if p.get('label') not in ('equivalent','not_equivalent'): raise ValueError('Invalid clone atom label')
        if not p.get('input_types'): raise ValueError('At least one input required')
        for t in [*p['input_types'],p['output_type']]: java_type(t)
        if any(not isinstance(p.get(k),str) or not p[k] for k in ('a_members','b_members')):
            raise ValueError('Both Java class member sources required')
        if stochastic_source(p['a_members']+'\n'+p['b_members']):
            raise ValueError('Unseeded randomness/time requires a different observation oracle; excluded from deterministic clone admission')
        for imp in p.get('imports',['java.util.*']):
            if not re.fullmatch(r'[A-Za-z_][\w]*(?:\.[A-Za-z_][\w]*)*(?:\.\*)?',imp):
                raise ValueError('Imports must be qualified names, without Java statements')
        if not isinstance(p.get('suites'),dict) or len(p['suites'])<2:
            raise ValueError('At least two named atomic suites required')
        for suite in p['suites']:
            cases = p['suites'].get(suite)
            if not cases or not p.get('suite_evidence',{}).get(suite):
                raise ValueError('Both atomic suites and their provenance are required')
            for values in cases:
                if not isinstance(values,list) or len(values)!=len(p['input_types']): raise ValueError('Test arity mismatch')
                for value,kind in zip(values,p['input_types']): literal(value,kind)

    def compatible(self,a,b):
        return self.mode=='aggregation' or a['payload']['output_type'] in b['payload']['input_types']

    def render(self, atoms, root):
        stages = [a['payload'] for a in atoms]
        if sum(p['label']=='not_equivalent' for p in stages)>1:
            raise Reject('At most one negative atom per task')
        files = {}
        # Feed one exact-type parameter of each next stage from the previous return;
        # all remaining parameters are explicit public driver inputs.
        bindings=[None]+[p['input_types'].index(stages[i-1]['output_type'])
                         for i,p in enumerate(stages[1:],1)] if self.mode=='chain' else []
        free=[(i,j,t) for i,p in enumerate(stages) for j,t in enumerate(p['input_types'])
              if self.mode!='chain' or bindings[i]!=j]
        for i,p in enumerate(stages):
            imports = '\n'.join('import '+x+';' for x in p.get('imports',['java.util.*']))
            for side in ('a','b'):
                files[f'cw/stage_{i}/{side}/Atom.java'] = (
                    f'package cw.stage_{i}.{side};\n'+imports+'\npublic class Atom {\n'+p[side+'_members']+'\n}\n')
        for side in ('a','b'):
            class_name = 'Outer'+side.upper()
            if self.mode=='aggregation':
                params = [f'{t} s{i}p{j}' for i,p in enumerate(stages) for j,t in enumerate(p['input_types'])]
                calls = []
                for i,p in enumerate(stages):
                    args = ','.join(f's{i}p{j}' for j in range(len(p['input_types'])))
                    calls.append(f'        results[{i}] = obs(() -> cw.stage_{i}.{side}.Atom.{p["entry"]}({args}));')
                body = f'        Object[] results = new Object[{len(stages)}];\n'+'\n'.join(calls)+'\n        return results;'
                signature = 'Object[] run('+','.join(params)+')'
            else:
                signature = stages[-1]['output_type']+' run('+','.join(f'{t} s{i}p{j}' for i,j,t in free)+')'
                calls = []
                for i,p in enumerate(stages):
                    args=[f'v{i-1}' if bindings[i]==j else f's{i}p{j}' for j in range(len(p['input_types']))]
                    calls.append(f'        {p["output_type"]} v{i} = cw.stage_{i}.{side}.Atom.{p["entry"]}('+','.join(args)+');')
                body = '\n'.join(calls)+f'\n        return v{len(stages)-1};'
            files[class_name+'.java'] = ('public class '+class_name+' {\n'
                '    static Object obs(java.util.concurrent.Callable<Object> f) {\n'
                '        try { return f.call(); } catch (Throwable e) { return "__EXC__:"+e.getClass().getSimpleName(); }\n'
                '    }\n    public static '+signature+' throws Exception {\n'+body+'\n    }\n}\n')
        # Each atomic label must hold independently under both supplied suites.
        checks = []
        methods = []
        for i,p in enumerate(stages):
            for suite_index,suite in enumerate(p['suites']):
                suite_checks=['boolean allEqual=true; int beforeNormal=normalPairs;']
                for values in p['suites'][suite]:
                    suite_checks.append('allEqual &= same(() -> '+invocation(i,'a',p,values)+',() -> '+invocation(i,'b',p,values)+');')
                if self.config.get('require_nonexception_cases',True):
                    suite_checks.append('if (normalPairs == beforeNormal) fail("no nonexceptional case in atomic suite");')
                suite_checks.append('if (allEqual != '+str(p['label']=='equivalent').lower()+') fail("atomic label");')
                method=f'atomic_{i}_{suite_index}'
                methods.append('static void '+method+'() throws Exception {\n'+'\n'.join(suite_checks)+'\n}')
                checks.append(method+'();')
        combined = []
        if self.mode=='aggregation':
            baseline = [next(iter(p['suites'].values()))[0] for p in stages]
            for i,p in enumerate(stages):
                for suite in p['suites'].values():
                    for values in suite:
                        case = list(baseline); case[i]=values
                        combined.append([literal(v,t) for group,s in zip(case,stages) for v,t in zip(group,s['input_types'])])
        else:
            baseline=[next(iter(p['suites'].values()))[0] for p in stages]
            for index,p in enumerate(stages):
                for suite in p['suites'].values():
                    for values in suite:
                        case=list(baseline);case[index]=values
                        combined.append([literal(case[i][j],t) for i,j,t in free])
        checks.append('boolean compositeEqual=true;')
        checks.append('int compositeNormalBefore=normalPairs;')
        for start in range(0,len(combined),16):
            calls=[]
            for values in combined[start:start+16]:
                args = ','.join(values)
                calls.append('equal &= same(() -> OuterA.run('+args+'),() -> OuterB.run('+args+'));')
            method=f'composite_{start}'
            methods.append('static boolean '+method+'() throws Exception {boolean equal=true;\n'+'\n'.join(calls)+'\nreturn equal;}')
            checks.append('compositeEqual &= '+method+'();')
        label = 'not_equivalent' if any(p['label']=='not_equivalent' for p in stages) else 'equivalent'
        if self.mode=='chain' and self.config.get('require_nonexception_cases',True):
            checks.append('if (normalPairs == compositeNormalBefore) fail("no nonexceptional composite case");')
        checks.append('if (compositeEqual != '+str(label=='equivalent').lower()+') fail("composite label masked or invalid");')
        harness = ('public class Check {\n'
            'static int normalCalls=0, normalPairs=0;\n'
            'static Object obs(java.util.concurrent.Callable<Object> f) {try {Object value=f.call();normalCalls++;return value;} catch(Throwable e) {return "__EXC__:"+e.getClass().getSimpleName();}}\n'
            'static boolean same(java.util.concurrent.Callable<Object> a,java.util.concurrent.Callable<Object> b) {int before=normalCalls;Object x=obs(a),y=obs(b);if(normalCalls-before==2)normalPairs++;return java.util.Objects.deepEquals(x,y);}\n'
            'static void fail(String why) {System.out.println("CW_RESULT:{\\"valid\\":false,\\"reason\\":\\""+why+"\\"}");System.exit(1);}\n'
            + '\n'.join(methods)+'\npublic static void main(String[] args) throws Exception {\n'+'\n'.join(checks)+
            '\nSystem.out.println("CW_RESULT:{\\"valid\\":true}");\n}\n}\n')
        for name,content in files.items(): text(root/'work'/name,content)
        text(root/'work'/'Check.java',harness)
        return BuiltTask(root,{'files':files,'composition_mode':self.mode,
            'observation':'returned values, array contents and exception class tags; fresh inputs on each side',
            'question':'Are OuterA.run and OuterB.run equivalent? Emit VERDICT: 1 or VERDICT: 0.'},
            {'label':label,'composite_test_cases':len(combined),'atomic_suites':sum(len(p['suites']) for p in stages)})

    def admit(self,built,runner):
        javac = self.config.get('javac','javac')
        java = self.config.get('java','java')
        work = built.root/'work'
        sources = sorted(str(p.relative_to(work)).replace('\\','/') for p in work.rglob('*.java'))
        version = runner.run([javac,'-version'],work,name='javac-version')
        if version['returncode']!=0: raise InfrastructureError('javac unavailable')
        result = runner.run([javac,'-encoding','UTF-8','-d','classes',*sources],work,name='compile-atoms-and-composites')
        if result['returncode']!=0: raise Reject('Java compilation failed')
        try:result = runner.run([java,'-Xmx256m','-cp','classes','Check'],work,name='atomic-and-whole-composite-tests')
        except InfrastructureError as exc:
            if str(exc)=='atomic-and-whole-composite-tests: TimeoutExpired':
                raise Reject('Java composite did not finish within the candidate execution budget') from exc
            raise
        evidence = [line[len('CW_RESULT:'):] for line in result['stdout'].splitlines() if line.startswith('CW_RESULT:')]
        try: valid = len(evidence)==1 and json.loads(evidence[0]).get('valid') is True
        except json.JSONDecodeError: valid=False
        if result['returncode']!=0 or not valid: raise Reject('Java label validation failed')
        return {'atom_gate':True,'reference_gate':True,'suites':built.private['atomic_suites'],
            'composite_cases':built.private['composite_test_cases'],'observation':built.public['observation'],
            'limitation':'EQ is suite-relative; suite provenance is supplied by the atomic dataset adapter.'}
