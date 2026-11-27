import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.delivery import materialize, DeliveryUncertain
from tools.snapshot import take_snapshot
from tools.cli import main


def setup(base):
    source=base/'source'; source.mkdir(); work=source/'.work'; work.mkdir()
    site=work/'staging'/'run'; site.mkdir(parents=True)
    (site/'index.html').write_text('home'); (site/'assets').mkdir(); (site/'assets/style.css').write_text('css')
    (site/'other.html').write_text('other'); (site/'empty').mkdir()
    selection=work/'selection.json'; selection.write_text(json.dumps(['index.html','assets/style.css','empty']))
    return source,work,site,selection,work/'deliveries'/'one'


class DeliveryTests(unittest.TestCase):
    def test_explicit_selection_and_snapshot(self):
        with tempfile.TemporaryDirectory(dir='.') as t:
            src,work,site,selection,out=setup(Path(t).absolute())
            result=materialize(src,site,selection,out)
            self.assertEqual(result['status'],'unverified')
            self.assertEqual(result['excluded'], ['other.html'])
            self.assertEqual(result['delivery_snapshot'],take_snapshot(out,'delivery')['digest'])
            self.assertTrue((out/'empty').is_dir()); self.assertFalse((out/'other.html').exists())
            self.assertTrue(Path(result['record']).is_file())
            with self.assertRaises(ValueError): materialize(src,site,selection,out)
            (out/'assets/style.css').write_text('changed')
            self.assertNotEqual(result['delivery_snapshot'],take_snapshot(out,'delivery')['digest'])

    def test_bad_selection_never_creates_target(self):
        with tempfile.TemporaryDirectory(dir='.') as t:
            src,work,site,selection,out=setup(Path(t).absolute())
            for values in (['../escape'], ['index.html','index.html'], ['missing']):
                selection.write_text(json.dumps(values))
                with self.assertRaises(ValueError): materialize(src,site,selection,out)
                self.assertFalse(out.exists()); self.assertFalse((work/'deliveries').exists())
            selection.write_text(json.dumps(['index.html']))
            with self.assertRaises(ValueError): materialize(src,site,selection,work/'elsewhere')

    def test_failure_is_explicit_and_partial_directory_is_not_a_delivery(self):
        with tempfile.TemporaryDirectory(dir='.') as t:
            src,work,site,selection,out=setup(Path(t).absolute())
            with patch('tools.delivery._write_new',side_effect=OSError('injected')):
                with self.assertRaises(DeliveryUncertain): materialize(src,site,selection,out)
            self.assertTrue(out.exists())
            self.assertFalse(any((work/'delivery-records').iterdir()))

    def test_mkdir_error_after_creation_reports_uncertain(self):
        with tempfile.TemporaryDirectory(dir='.') as t:
            src,work,site,selection,out=setup(Path(t).absolute())
            (work/'deliveries').mkdir()
            original=Path.mkdir
            def mkdir_then_fail(path,*args,**kwargs):
                result=original(path,*args,**kwargs)
                if path==out: raise OSError('injected after mkdir')
                return result
            with patch.object(Path,'mkdir',autospec=True,side_effect=mkdir_then_fail):
                with self.assertRaises(DeliveryUncertain): materialize(src,site,selection,out)
            self.assertTrue(out.is_dir()); self.assertFalse((work/'delivery-records').exists())

    def test_cli_returns_incomplete_and_unverified(self):
        with tempfile.TemporaryDirectory(dir='.') as t:
            src,work,site,selection,out=setup(Path(t).absolute())
            stream=io.StringIO()
            with contextlib.redirect_stdout(stream):
                code=main(['materialize','--source',str(src),'--site',str(site),'--selection',str(selection),'--output',str(out),'--json'])
            self.assertEqual(code,2)
            result=json.loads(stream.getvalue())
            self.assertEqual(result['delivery']['status'],'unverified')
            self.assertEqual(result['operation'],'applied')

if __name__=='__main__': unittest.main()
