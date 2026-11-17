import ast
import importlib.util
import json
from pathlib import Path
import tempfile
import sqlite3
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import unittest
from codewalk.recovery.rust import tokens,replace_names,verus_body,functions,executable_projection
from codewalk.recovery.python_cost import analyze
from codewalk.composition.python_cost import ComplexityBackend
from codewalk.composition.base import Runner
from examples.generation_demo import atom
from unittest.mock import patch


class RecoveryTests(unittest.TestCase):
    def test_free_function_recovery_does_not_rename_methods_or_qualified_apis(self):
        from codewalk.recovery.published_verus import rename_functions
        source='fn contains() -> bool { true }\nfn check(v: Seq<int>) -> bool { v.contains(1) && contains() && api::contains() }'
        result=rename_functions(source,{'contains':'f1_contains','check':'f1_check'})
        self.assertIn('fn f1_contains()',result)
        self.assertIn('v.contains(1)',result)
        self.assertIn('&& f1_contains()',result)
        self.assertIn('api::contains()',result)

    def test_original_reference_preserves_protected_blocks_and_reuses_identical_specs(self):
        from codewalk.recovery.published_verus import recover_reference
        from codewalk.recovery.rust import functions,verus_body
        source='''spec fn score(x: int) -> int { x }
fn copy(x: u64) -> (r: u64)
    ensures r as int == score(x as int),
{ x }
'''
        task='''use vstd::prelude::*;
verus! {
spec fn score(x: int) -> int { x }
spec fn f1_score(x: int) -> int { x }
fn f1_copy(x: u64) -> (r: u64) { x }
spec fn step1(x: u64, r: u64) -> bool { r as int == score(x as int) }
fn chain_driver(x: u64) -> (r: u64)
    ensures step1(x,r),
{ let r = f1_copy(x); assert(step1(x,r)); r }
}
fn main() {}
'''
        reference,evidence=recover_reference(task,[source])
        before,after=verus_body(task),verus_body(reference)
        a,b=functions(before),functions(after)
        for name in ['score','step1','chain_driver']:
            self.assertEqual(before[a[name]['start']:a[name]['end']],after[b[name]['start']:b[name]['end']])
        self.assertEqual(evidence['identical_public_spec_aliases'],{'f1_score':'score'})
        self.assertIn('r as int == score(x as int)',after[b['f1_copy']['start']:b['f1_copy']['end']])
        self.assertFalse(evidence['reference_verified'])

    def test_original_reference_rejects_changed_executable_or_precondition(self):
        from codewalk.recovery.published_verus import recover_reference
        task='''use vstd::prelude::*;
verus! {
fn f1_half(x: u64) -> (r: u64) requires x <= 10, { x / 2 }
spec fn step1(x: u64, r: u64) -> bool { r == x / 2 }
fn chain_driver(x: u64) -> (r: u64) requires x <= 10, ensures step1(x,r), { f1_half(x) }
}
fn main() {}
'''
        changed_code='fn half(x: u64) -> (r: u64) requires x <= 10, ensures r == x / 3, { x / 3 }'
        with self.assertRaisesRegex(ValueError,'executable tokens'):recover_reference(task,[changed_code])
        changed_domain='fn half(x: u64) -> (r: u64) requires x <= 5, ensures r == x / 2, { x / 2 }'
        with self.assertRaisesRegex(ValueError,'preconditions'):recover_reference(task,[changed_domain])

    def test_historical_missing_decreases_diagnostic_requires_separate_typecheck(self):
        from codewalk.composition.rust_source import SourceVerusBackend
        from codewalk.composition.base import Reject
        backend=SourceVerusBackend({});runner=Runner({})
        proof={'returncode':1,'stdout':'','stderr':'error: loop must have a decreases clause\nerror: aborting due to 1 previous error\n'}
        with patch.object(runner,'run',side_effect=[{'returncode':0,'stdout':'','stderr':''},proof]):
            self.assertEqual(backend.verify(runner,Path('.'),'task.rs')['errors'],1)
        with patch.object(runner,'run',return_value={'returncode':1,'stdout':'','stderr':'type error'}):
            with self.assertRaisesRegex(Reject,'does not typecheck'):backend.verify(runner,Path('.'),'task.rs')

    def test_paper_packager_refuses_unaligned_count_only_release(self):
        root=Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as folder:
            work=Path(folder);report=work/'alignment.json';profile=work/'profile.json'
            report.write_text(json.dumps({'datasets':{domain:{'hugging_face_identity':False,
                'paper_identity_and_results':None,'composition_methods':False}
                for domain in ('bugfixing','verus','bigo','codeclone')}}))
            profile.write_text(json.dumps({'requires_verified_three_way_alignment':True,
                                          'alignment_report':str(report)}))
            result=subprocess.run([sys.executable,str(root/'scripts/package_reconstructed_data.py'),
                '--profile',str(profile),'--output',str(work/'out')],capture_output=True,text=True)
            self.assertNotEqual(result.returncode,0)
            self.assertIn('Three-way alignment failed',result.stderr)
            self.assertFalse((work/'out').exists())

    def test_counts_and_reference_success_do_not_satisfy_three_way_alignment(self):
        from codewalk.alignment import require_alignment
        report={'tasks':1706,'code_tests_passed':True,'datasets':{
            domain:{'hugging_face_identity':True,'paper_identity_and_results':True,'composition_methods':True}
            for domain in ('bugfixing','verus','bigo','codeclone')}}
        require_alignment(report)
        report['datasets']['bigo']['composition_methods']=False
        with self.assertRaisesRegex(ValueError,'bigo: composition_methods'):require_alignment(report)
        report['datasets']['bigo']['composition_methods']=None
        with self.assertRaises(ValueError):require_alignment(report)

    def test_paper_complexity_gate_rejects_trivial_chains_but_keeps_numeric_growth(self):
        from codewalk.composition import generate
        from examples.generation_demo import prepare as fixtures
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            identities=fixtures('bigo',root/'fixtures',2)
            report=generate('bigo',identities,root/'trivial',level=2,max_candidates=1,
                            config={'require_nontrivial_composition':True})
            self.assertFalse(report['complete'])
            self.assertIn('dominant atomic',report['rejected'][0]['reason'])
            baseline=generate('bigo',identities[:1],root/'baseline',level=1,
                              config={'require_nontrivial_composition':True})
            self.assertTrue(baseline['complete'])
            producer=atom('bigo',10,{'entry':'run','source':'def run(n):\n    return n*n\n',
                'input_type':'int','output_type':'int','input_size':'value','output_size':'value',
                'cost':{'n_power':0,'log_power':0},'size_transfer':{'power':2,'coefficient':1},
                'cost_evidence':'Unit-cost integer multiplication; output value grows quadratically',
                'cases':[{'input':n,'expected':n*n} for n in (0,1,2,3)]})
            consumer=atom('bigo',11,{'entry':'run','source':'def run(n):\n    total=0\n    for i in range(n):\n        total+=1\n    return total\n',
                'input_type':'int','output_type':'int','input_size':'value','output_size':'value',
                'cost':{'n_power':1,'log_power':0},'size_transfer':{'power':1,'coefficient':1},
                'cost_evidence':'One increment per input value',
                'cases':[{'input':n,'expected':n} for n in (0,1,2,3)]})
            result=generate('bigo',[producer,consumer],root/'growth',level=2,
                groups=[[producer['id'],consumer['id']]],config={'require_nontrivial_composition':True})
            self.assertTrue(result['complete'],result)
            task=result['accepted'][0]['task_id'];judge=json.loads((root/'growth/private/candidates'/task/'judge.json').read_text())
            self.assertEqual(judge['label'],'quadratic')
            self.assertTrue(judge['derivation']['paper_nontriviality']['passed'])

    @unittest.skipUnless(__import__('shutil').which('git'),'Git required')
    def test_original_repair_preparer_applies_only_test_patches_and_seals_history(self):
        from codewalk.repair_restore import prepare as prepare_original
        from examples.generation_demo import prepare as fixtures
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);a=fixtures('bugfixing',root/'fixtures',1)[0]['payload']
            recipe={'task_id':'original','base_commit':a['base_commit'],'image':'fixture:not-executed',
                    'test_patches':[a['test_patch']],'target_tests':a['test_ids']}
            recipes=root/'recipes.jsonl';recipes.write_text(json.dumps(recipe)+'\n')
            receipt=prepare_original(recipes,'original',root/'agent',repository=a['repository'])
            self.assertTrue((root/'agent/tests/test_f0.py').is_file())
            self.assertIn('return x - 1',(root/'agent/math_impl.py').read_text())
            self.assertFalse(any(p.name=='.git' for p in (root/'agent').rglob('*')))
            self.assertFalse(receipt['gold_exposed'])
            self.assertFalse(receipt['test_execution_performed'])

    def test_shared_n_multiargument_admission_and_contract_rejection(self):
        from codewalk.composition import generate
        fn=ast.parse('def product(a,b):\n    for i in range(a):\n        for j in range(b):\n            pass\n    return a\n').body[0]
        self.assertEqual(analyze(fn,'array'),(2,0))
        payload={'entry':'run','source':ast.unparse(fn)+'\ndef run(record):\n    return product(*record["args"])\n',
            'input_type':'SharedArgs[integer,integer]','output_type':'int','input_size':'shared','output_size':'constant',
            'input_contract':{'argument_layout':['integer','integer'],'n':'arguments are between zero and n'},
            'cost':{'n_power':2,'log_power':0},'size_transfer':{'power':0,'coefficient':1},
            'cost_evidence':'Audited two nested loops over independently bounded shared n arguments',
            'cases':[{'input':{'n':n,'args':[n,n]},'expected':n} for n in (0,1,2,3)]}
        a=atom('bigo',0,payload)
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            report=generate('bigo',[a],root/'valid',level=1)
            self.assertTrue(report['complete'],report)
            a['payload']['cases'][0]['input']['args']=[100,100]
            invalid=generate('bigo',[a],root/'invalid',level=1,max_candidates=1)
            self.assertFalse(invalid['complete'])
            self.assertIn('shared n bound',invalid['rejected'][0]['reason'])

    def test_atomic_proof_cache_invalidates_source_and_toolchain(self):
        from codewalk.composition.rust_source import SourceVerusBackend
        from codewalk.composition.rust_proof import VerusBackend
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);tool=root/'verus.exe';tool.write_bytes(b'fixture-tool')
            (root/'atom-0.rs').write_text('source one')
            config={'verus':str(tool),'atomic_reference_cache':str(root/'cache')}
            backend=SourceVerusBackend(config);runner=Runner(config)
            def verify(*args):
                runner.records.append({'name':'actual-proof-fixture','returncode':0})
                return {'verified':2,'errors':0}
            with patch.object(VerusBackend,'verify',side_effect=verify) as called:
                backend.verify(runner,root,'atom-0.rs');backend.verify(runner,root,'atom-0.rs')
                self.assertEqual(called.call_count,1)
                (root/'atom-0.rs').write_text('different source')
                backend.verify(runner,root,'atom-0.rs');self.assertEqual(called.call_count,2)
                tool.write_bytes(b'changed fixture-tool-version')
                backend.verify(runner,root,'atom-0.rs');self.assertEqual(called.call_count,3)

    def test_published_repair_restore_preserves_full_definition_without_fresh_gate_claim(self):
        from codewalk.repair_restore import restore
        import hashlib
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/'source';(source/'data').mkdir(parents=True)
            target='tests/test_x.py::test_x'
            bugs=[{'instance_id':str(i),'FAIL_TO_PASS':[target],'test_patch':'TEST PATCH '+str(i),
                   'gold_patch':'PRIVATE GOLD '+str(i)} for i in range(2)]
            row={'task_id':'original','level':2,'num_bugs':2,'bugs':bugs,'repo':'owner/repository',
                 'base_commit':'a'*40,'image':'original/image:tag','all_FAIL_TO_PASS':[target,target]}
            raw=(json.dumps(row)+'\n').encode();(source/'data/test.jsonl').write_bytes(raw)
            (source/'download_receipt.json').write_text(json.dumps({'repo_id':'fixture','revision':'pin',
                'files':{'data/test.jsonl':{'sha256':hashlib.sha256(raw).hexdigest()}}}))
            with patch('codewalk.repair_restore.registry',return_value={'bugfixing':{'repo_id':'fixture','revision':'pin','expected_levels':{'2':1}}}):
                report=restore(source,root/'restored')
            self.assertEqual(report['validation_status'],'published_original_not_locally_readmitted')
            public=(root/'restored/model_inputs/bugfixing.jsonl').read_text()
            prep=(root/'restored/preparation/bugfixing.jsonl').read_text()
            self.assertNotIn('PRIVATE GOLD',public+prep)
            judge=json.loads((root/'restored/judge/bugfixing.jsonl').read_text())
            self.assertEqual(judge['upstream_record'],row)
            self.assertEqual(json.loads(public)['target_tests'],[target])

    def test_materialize_uses_only_public_files_and_rejects_escape(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);inputs=root/'inputs.jsonl'
            inputs.write_text(json.dumps({'task_id':'fixture','files':{'source.py':'x=1\n'},'label':'PRIVATE'})+'\n',encoding='utf-8')
            result=subprocess.run([sys.executable,'-m','codewalk','materialize','--inputs',str(inputs),
                '--task-id','fixture','--output',str(root/'model')],capture_output=True)
            self.assertEqual(result.returncode,0)
            self.assertEqual([p.name for p in (root/'model').iterdir()],['source.py'])
            inputs.write_text(json.dumps({'task_id':'escape','files':{'../outside.py':'x=2'}})+'\n',encoding='utf-8')
            result=subprocess.run([sys.executable,'-m','codewalk','materialize','--inputs',str(inputs),
                '--task-id','escape','--output',str(root/'invalid')],capture_output=True)
            self.assertNotEqual(result.returncode,0)
            self.assertFalse((root/'outside.py').exists())

    @unittest.skipUnless(importlib.util.find_spec('apsw') and importlib.util.find_spec('requests'),'HTTP SQLite recovery extras required')
    def test_range_sqlite_real_read_only_query_and_cache(self):
        from codewalk.recovery.http_sqlite import RangeStore,connect
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/'source.db'
            db=sqlite3.connect(source);db.execute('create table methods(id integer primary key,source text)')
            db.execute('insert into methods values(?,?)',(7,'literal source, not executable instructions'))
            db.commit();db.close();content=source.read_bytes()
            class Handler(BaseHTTPRequestHandler):
                def log_message(self,*args):pass
                def do_GET(self):
                    interval=self.headers['Range'].split('=')[1]
                    start,end=map(int,interval.split('-'));end=min(end,len(content)-1)
                    value=content[start:end+1]
                    self.send_response(206);self.send_header('Content-Range',f'bytes {start}-{end}/{len(content)}')
                    self.send_header('Content-Length',str(len(value)));self.send_header('ETag','fixed-fixture');self.end_headers();self.wfile.write(value)
            server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
            worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
            try:
                store=RangeStore(f'http://127.0.0.1:{server.server_port}/source.db',root/'cache',block_size=2048)
                connection,vfs=connect(store,name='codewalk-fixture-http')
                self.assertEqual(list(connection.execute('select source from methods where id=?',(7,))),[('literal source, not executable instructions',)])
                connection.close()
                before=store.bytes_fetched;store.read(64,0);self.assertEqual(store.bytes_fetched,before)
            finally:server.shutdown();server.server_close();worker.join()

    def test_rust_token_renaming_preserves_strings_and_comments(self):
        source='fn f1_f() { let s="f1_f"; /* outer /* nested */ f1_f */ f1_f(); }'
        changed=replace_names(source,{'f1_f':'original'})
        self.assertIn('fn original()',changed)
        self.assertIn('"f1_f"',changed)
        self.assertIn('/* outer /* nested */ f1_f */',changed)
        self.assertIn('original();',changed)

    def test_rust_proof_projection_preserves_execution(self):
        reference='let mut i=0; while i<n invariant i<=n, decreases n-i, { proof { assert(i<n); } i+=1; } assert(i==n); i'
        task='let mut i=0; while i<n { i+=1; } i'
        self.assertEqual(executable_projection(reference),executable_projection(task))
        block=verus_body('use vstd::prelude::*; verus! { spec fn id<T>(x:T)->T {x} fn run(x:u64)->u64 {x} }')
        self.assertEqual(set(functions(block)),{'id','run'})

    def test_bounded_cost_grammar_rejects_unknown_while_and_globals(self):
        valid=ast.parse('def f(n):\n c=0\n while n:\n  c+=1\n  n//=2\n return c').body[0]
        self.assertEqual(analyze(valid,'integer'),(0,1))
        for source in ('def f(n):\n while n:\n  n+=1\n return n',
                       'def f(n):\n return missing(n)'):
            with self.assertRaises(ValueError):analyze(ast.parse(source).body[0],'integer')

    def test_python_tuple_reference_and_affine_size_offset(self):
        p={'entry':'run','source':'def run(x):\n return (x,x+1)\n',
           'input_type':'int','output_type':'tuple[int,int]','input_size':'value','output_size':'length',
           'cost':{'n_power':0,'log_power':0},'size_transfer':{'power':0,'coefficient':1,'offset':1},
           'cost_evidence':'Synthetic constant pair construction.','cases':[{'input':1,'expected':[1,2]}]}
        a=atom('bigo',0,p);backend=ComplexityBackend({});backend.validate(a)
        with tempfile.TemporaryDirectory() as folder:
            built=backend.render([a],Path(folder));evidence=backend.admit(built,Runner({}))
            self.assertTrue(evidence['reference_gate'])

    @unittest.skipUnless(importlib.util.find_spec('tree_sitter_java'),'Java recovery extras required')
    def test_java_ast_and_original_suite_literal_inputs(self):
        from codewalk.recovery.java import normalize,test_inputs
        method={'name':'source','source':'int source(int x) { String s="source"; return source(x-1); }'}
        normalized=normalize(method)
        self.assertIn('int run(int x)',normalized['member'])
        self.assertIn('"source"',normalized['member'])
        self.assertIn('return run(x-1)',normalized['member'])
        suite='class Tests { void test0() { int[] a=new int[2]; a[0]=3; Target t=new Target(); t.__target__(a,1); } }'
        self.assertEqual(test_inputs(suite,['int[]','int']),[[[3,0],1]])


if __name__=='__main__':unittest.main()
