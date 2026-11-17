import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from codewalk.benchmark import checked_proof, grade_submission, evaluate


TASK = '''use vstd::prelude::*;
verus! {
spec fn step1(x: u64, y: u64) -> bool { y == x }
fn copy(x: u64) -> (r: u64)
    requires x < 100,
{
    x
}
fn chain_driver(x: u64) -> (r: u64)
    requires x < 100,
    ensures step1(x,r),
{
    let r = copy(x);
    r
}
}
fn main() {}
'''


class BenchmarkTests(unittest.TestCase):
    def test_proof_grader_preserves_execution_and_preconditions(self):
        valid = TASK.replace('requires x < 100,\n{', 'requires x < 100,\n    ensures r == x,\n{', 1)
        self.assertIn('ensures r == x', checked_proof(TASK,valid))
        for candidate in (TASK.replace('    x\n','    0\n'),TASK.replace('x < 100','x < 0',1),
                          TASK.replace('fn copy','proof fn copy'),TASK.replace('fn copy(x: u64)','fn copy(x: u32)',1)):
            with self.assertRaises(ValueError):checked_proof(TASK,candidate)

    def test_original_driver_and_predicate_are_restored(self):
        candidate = TASK.replace('y == x','true').replace('let r = copy(x);','let r = 0;')
        self.assertEqual(checked_proof(TASK,candidate),TASK)

    def test_existing_sound_loop_strategy_attribute_is_preserved(self):
        task = TASK.replace('fn copy', '#[verifier::loop_isolation(false)]\nfn copy')
        self.assertEqual(checked_proof(task,task),task)
        with self.assertRaises(ValueError):checked_proof(TASK,task)

    def test_proof_grader_rejects_bypasses_external_macros_and_extra_execution(self):
        for addition in ('proof fn bad() { assume(false); }','#[verifier::external_body] proof fn bad() {}',
                         'fn extra() {}','include!("hidden.rs");'):
            candidate = TASK.replace('\n}\nfn main()', '\n'+addition+'\n}\nfn main()')
            with self.assertRaises(ValueError):checked_proof(TASK,candidate)

    def test_proof_syntax_error_is_model_failure_but_missing_tool_is_infrastructure(self):
        result = grade_submission('verus',{'files':{'task.rs':TASK}},{},{'source':TASK},{'verus':'missing-codewalk-verifier'})
        self.assertEqual(result['status'],'infra_error')
        def broken(runner, work, filename):
            from codewalk.composition.base import InfrastructureError
            runner.records.append({'stdout':'','stderr':'error: expected expression','returncode':1})
            raise InfrastructureError('No verification counts')
        with patch('codewalk.benchmark.SourceVerusBackend.verify',side_effect=broken):
            result = grade_submission('verus',{'files':{'task.rs':TASK}},{},{'source':TASK},{})
        self.assertEqual(result['status'],'failure')

    def test_repair_missing_runtime_does_not_count_as_failure(self):
        result = grade_submission('bugfixing',{'task_id':'one'},{},{'patch':''},{})
        self.assertEqual(result['status'],'infra_error')

    def test_repair_rejects_test_patch_before_running_tests(self):
        with tempfile.TemporaryDirectory() as tmp:
            patch_text = 'diff --git a/tests/test_x.py b/tests/test_x.py\n--- a/tests/test_x.py\n+++ b/tests/test_x.py\n@@ -1 +1 @@\n-a\n+b\n'
            gold = patch_text.replace('tests/test_x.py','src.py')
            result = grade_submission('bugfixing',{'task_id':'one'},{'gold_patches':[gold],'target_tests':['tests/test_x.py::test_x']},
                                      {'patch':patch_text},{'prepared_repositories':{'one':tmp}})
            self.assertEqual(result['status'],'failure')
            self.assertIn('allowed source',result['reason'])

    def test_evaluator_rejects_duplicate_attempts_before_grading(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for folder in ('model_inputs','judge'):
                (root/folder).mkdir()
            (root/'model_inputs/bigo.jsonl').write_text('{"task_id":"v2:one"}\n')
            (root/'judge/bigo.jsonl').write_text('{"task_id":"v2:one","level":1,"label":"linear"}\n')
            row = {'task_id':'v2:one','sample_idx':0,'response':'linear'}
            with self.assertRaises(ValueError):list(evaluate(root,'bigo',[row,row],{}))
            with self.assertRaises(ValueError):list(evaluate(root,'bigo',[{**row,'task_id':'old:one'}],{}))


if __name__ == '__main__':unittest.main()
