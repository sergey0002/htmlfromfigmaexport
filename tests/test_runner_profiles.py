import contextlib
import io
import json
import unittest
from unittest.mock import patch
from tools.cli import main


class RunnerProfilesTests(unittest.TestCase):
    def test_inspection_never_runs_project_and_does_not_claim_isolation(self):
        out=io.StringIO()
        with patch('subprocess.run',side_effect=AssertionError('unexpected execution')), contextlib.redirect_stdout(out):
            code=main(['runner-profiles','--json'])
        result=json.loads(out.getvalue()); self.assertEqual(code,2)
        profiles=result['runner']['profiles']
        self.assertFalse(result['runner']['executes_project'])
        self.assertFalse(profiles['managed-isolated']['available'])
        self.assertFalse(profiles['managed-local']['available'])
        self.assertTrue(profiles['external-unverified']['available'])

if __name__=='__main__': unittest.main()
