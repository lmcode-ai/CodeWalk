import copy
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch as mock_patch
from codewalk.composition import generate
from codewalk.composition.python_cost import derive
from codewalk.composition.base import Reject
from examples.generation_demo import prepare
from codewalk.composition.repair import patch_files


def config(name):
    path = os.environ.get('CODEWALK_'+name.upper()+'_CONFIG')
    return json.loads(Path(path).read_text()) if path else {}


class GenerationTests(unittest.TestCase):
    def test_explicit_undirected_groups_cannot_bypass_symmetry(self):
        from codewalk.composition.base import Backend
        from codewalk.composition.registry import BACKENDS
        from examples.generation_demo import atom
        class Broken(Backend):
            name='broken';directed=False
            def compatible(self,a,b):return a['id']<b['id']
        BACKENDS['broken']=Broken
        try:
            with tempfile.TemporaryDirectory() as folder:
                atoms=[atom('broken',i,{}) for i in (0,1)]
                with self.assertRaises(ValueError):
                    generate('broken',atoms,Path(folder)/'out',level=2,groups=[[a['id'] for a in atoms]])
        finally:BACKENDS.pop('broken')

    def test_explicit_source_groups_keep_order_and_still_require_validation(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);atoms=prepare('bigo',root/'fixtures',2)
            ids=[atoms[1]['id'],atoms[0]['id']]
            report=generate('bigo',atoms,root/'out',level=2,groups=[ids],max_candidates=1)
            self.assertTrue(report['complete'])
            self.assertEqual(report['accepted'][0]['atom_ids'],ids)
            with self.assertRaises(ValueError):
                generate('bigo',atoms,root/'bad',level=2,groups=[[ids[0],ids[0]]])

    def test_unseeded_randomness_is_not_deterministic_clone_evidence(self):
        from codewalk.composition.java_clone import CloneBackend,stochastic_source
        self.assertTrue(stochastic_source('return new Random().nextInt();'))
        self.assertFalse(stochastic_source('return new Random(7).nextInt();'))
        with tempfile.TemporaryDirectory() as folder:
            atoms=prepare('codeclone',Path(folder)/'fixtures',1)
            atoms[0]['payload']['a_members']='public static int run(int x) {return new java.util.Random().nextInt();}'
            with self.assertRaises(ValueError):CloneBackend({}).validate(atoms[0])

    def test_directed_lookahead_prunes_dead_end(self):
        from codewalk.graph import sample_groups
        atoms=[{'id':x,'source_id':x} for x in 'abcd']
        edges={('a','b'),('b','c'),('a','d')}
        group=sample_groups(atoms,lambda a,b:(a['id'],b['id']) in edges,
                            level=3,count=1,seed=0,directed=True,lookahead=True)[0]
        self.assertEqual([a['id'] for a in group],['a','b','c'])

    def test_failed_publication_never_exports_a_complete_task(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); atoms=prepare('bigo',root/'fixtures',1)
            with mock_patch.object(Path,'rename',side_effect=PermissionError('scanner lock')), \
                 mock_patch('codewalk.composition.base.time.sleep'):
                report=generate('bigo',atoms,root/'out',level=1,max_candidates=1)
            self.assertFalse(report['complete'])
            self.assertIn('filesystem access denied',report['blocked'])
            self.assertFalse((root/'out/dataset.jsonl').exists())
            self.assertEqual(list((root/'out/tasks').iterdir()),[])

    def test_new_domain_uses_same_executable_pipeline(self):
        from examples.affine_backend import AffineBackend
        from codewalk.composition.registry import BACKENDS
        from examples.generation_demo import atom
        BACKENDS['affine']=AffineBackend
        try:
            with tempfile.TemporaryDirectory() as folder:
                atoms=[atom('affine',0,{'a':2,'b':0}),atom('affine',1,{'a':1,'b':3})]
                report=generate('affine',atoms,Path(folder)/'out',level=2)
                self.assertTrue(report['complete'])
        finally:
            BACKENDS.pop('affine')

    def test_repair_special_file_patch_rejected(self):
        with self.assertRaises(ValueError):
            patch_files('diff --git a/x b/x\nnew file mode 120000\n--- /dev/null\n+++ b/x\n@@ -0,0 +1 @@\n+/outside\n')

    def test_bigo_real_execution_levels_and_no_answer_leakage(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            atoms = prepare('bigo',root/'fixtures',10)
            for level in (1,2,3,10):
                output = root/f'L{level}'
                report = generate('bigo',atoms,output,level=level)
                self.assertTrue(report['complete'])
                row = json.loads((output/'dataset.jsonl').read_text())
                self.assertNotIn('label',row)
                self.assertNotIn('cost_evidence',json.dumps(row))
                self.assertTrue((output/'tasks'/row['task_id']/'driver.py').is_file())
                self.assertTrue(report['implementation_sha256'])

    def test_cost_propagation_not_max_atomic_labels(self):
        stages = [{'cost':{'n_power':1,'log_power':0},'size_transfer':{'power':2}},
                  {'cost':{'n_power':1,'log_power':0},'size_transfer':{'power':1}}]
        self.assertEqual(derive(stages)['label'],'quadratic')
        stages[1]['cost']['n_power']=2
        with self.assertRaises(Reject): derive(stages)

    def test_wrong_python_reference_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); atoms=prepare('bigo',root/'fixtures',1)
            atoms[0]['payload']['cases'][1]['expected']=[999]
            report=generate('bigo',atoms,root/'out',level=1,max_candidates=1)
            self.assertFalse(report['complete'])
            self.assertTrue(report['rejected'])
            self.assertFalse((root/'out/dataset.jsonl').exists())
            self.assertFalse((root/'out/tasks').exists())

    def test_incomplete_quota_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); atoms=prepare('bigo',root/'fixtures',2)
            report=generate('bigo',atoms,root/'out',level=1,count=2,max_candidates=1)
            self.assertFalse(report['complete'])
            self.assertEqual(len(report['accepted']),1)
            self.assertFalse((root/'out/dataset.jsonl').exists())
            with self.assertRaises(ValueError): generate('bigo',atoms,root/'out',level=1)
            report=generate('bigo',atoms,root/'quota',level=1,max_candidates=2,
                            config={'label_quotas':{'constant':1}})
            self.assertFalse(report['complete'])

    def test_missing_tool_is_blocked_not_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); atoms=prepare('codeclone',root/'fixtures',1)
            report=generate('codeclone',atoms,root/'out',level=1,
                            config={'javac':'codewalk-intentionally-missing-compiler'})
            self.assertFalse(report['complete'])
            self.assertTrue(report['blocked'])
            self.assertEqual(report['rejected'],[])

    @unittest.skipUnless(shutil.which('git') and __import__('importlib.util',fromlist=['find_spec']).find_spec('pytest'),
                         'Git and pytest required for real repair execution')
    def test_repair_actual_fail_then_joint_pass(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); atoms=prepare('bugfixing',root/'fixtures',2)
            report=generate('bugfixing',atoms,root/'out',level=2)
            self.assertTrue(report['complete'],report)
            task=report['accepted'][0]['task_id']
            private=root/'out/private/candidates'/task
            evidence=json.loads((private/'admission.json').read_text())
            self.assertEqual(evidence['joint_tests']['passed'],2)
            self.assertTrue(all(r['failures']==1 for r in evidence['atomic_tests']))
            row=json.loads((root/'out/dataset.jsonl').read_text())
            self.assertNotIn('gold_patch',json.dumps(row))
            self.assertNotIn('base_commit',row)
            self.assertFalse(any('/.git/' in path for path in row['files']))
            # A failing joint reference must not produce a second admitted task.
            bad=copy.deepcopy(atoms)
            bad[1]['payload']['gold_patch']=bad[1]['payload']['gold_patch'].replace('return x + 2','return x + 20')
            rejected=generate('bugfixing',bad,root/'bad',level=2,max_candidates=1)
            self.assertFalse(rejected['complete'])
            self.assertIn('Joint reference',rejected['rejected'][0]['reason'])

    @unittest.skipUnless(os.environ.get('CODEWALK_JAVA_CONFIG') or (shutil.which('javac') and shutil.which('java')),
                         'Real JDK required')
    def test_java_compile_and_masked_negative_rejection(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); atoms=prepare('codeclone',root/'fixtures',2)
            report=generate('codeclone',atoms,root/'out',level=2,config=config('java'))
            self.assertTrue(report['complete'],report)
            # Force one typed chain where a true negative atom is erased downstream.
            a,b=copy.deepcopy(atoms)
            a['payload'].update({'input_types':['int'],'output_type':'long','label':'not_equivalent',
                'a_members':'public static long run(int x) { return x+1L; }',
                'b_members':'public static long run(int x) { return x+2L; }'})
            b['payload'].update({'input_types':['long'],'output_type':'boolean','label':'equivalent',
                'a_members':'public static boolean run(long x) { return false; }',
                'b_members':'public static boolean run(long x) { return false; }'})
            bad=generate('codeclone',[a,b],root/'masked',level=2,max_candidates=1,
                         config={**config('java'),'clone_mode':'chain'})
            self.assertFalse(bad['complete'])
            self.assertTrue(bad['rejected'])
            # A real feed may bind a non-first parameter; remaining arguments
            # must stay free public inputs rather than silently being discarded.
            a,b=copy.deepcopy(atoms)
            a['payload'].update({'input_types':['int'],'output_type':'int','label':'equivalent',
                'a_members':'public static int run(int x) { return x+1; }',
                'b_members':'public static int run(int x) { return 1+x; }'})
            b['payload'].update({'input_types':['long','int'],'output_type':'int','label':'equivalent',
                'a_members':'public static int run(long unused,int x) { return x*2; }',
                'b_members':'public static int run(long unused,int x) { return x+x; }',
                'suites':{k:[[99,*v] for v in values] for k,values in b['payload']['suites'].items()}})
            good=generate('codeclone',[a,b],root/'multi',level=2,groups=[[a['id'],b['id']]],
                          config={**config('java'),'clone_mode':'chain'})
            self.assertTrue(good['complete'],good)
            row=json.loads((root/'multi/dataset.jsonl').read_text())
            self.assertIn('s1p0,v0',row['files']['OuterA.java'])

    @unittest.skipUnless(os.environ.get('CODEWALK_VERUS_CONFIG') or shutil.which('verus'),'Real Verus required')
    def test_verus_actual_reference_and_unfinished(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); atoms=prepare('verus',root/'fixtures',2)
            report=generate('verus',atoms,root/'out',level=2,config=config('verus'))
            self.assertTrue(report['complete'],report)
            task=report['accepted'][0]['task_id']
            evidence=json.loads((root/'out/private/candidates'/task/'admission.json').read_text())
            self.assertEqual(evidence['reference']['errors'],0)
            self.assertGreater(evidence['unfinished']['errors'],0)
            trivial=copy.deepcopy(atoms[:1]); trivial[0]['payload']['ensures']='true'
            rejected=generate('verus',trivial,root/'trivial',level=1,max_candidates=1,config=config('verus'))
            self.assertFalse(rejected['complete'])
            self.assertIn('already verifies',rejected['rejected'][0]['reason'])


if __name__=='__main__': unittest.main()
