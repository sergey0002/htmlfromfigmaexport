import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools import static_reference
from tools.cli import main


def setup(root):
    source=root/'source'; source.mkdir(); (source/'index.html').write_text('<html>static reference</html>')
    (source/'assets').mkdir(); (source/'assets/style.css').write_text('body{color:black}')
    (source/'assets/ignored.css').write_text('ignored')
    (source/'.env').write_text('do not copy'); (source/'node_modules').mkdir(); (source/'node_modules/secret.js').write_text('ignored')
    work=source/'.work'; work.mkdir(); selection=work/'reference-selection.json'
    selection.write_text(json.dumps(['index.html','assets/style.css']))
    return source,work,selection


class StaticReferenceTests(unittest.TestCase):
    def test_exact_copy_detects_source_and_reference_drift(self):
        with tempfile.TemporaryDirectory(dir='.') as t:
            source,work,selection=setup(Path(t).absolute()); output=work/'static-references'/'one'
            data=static_reference.materialize(source,selection,output)
            self.assertEqual(data['operation'],'applied'); self.assertFalse(data['publication_eligible'])
            self.assertEqual((output/'index.html').read_text(),(source/'index.html').read_text())
            self.assertFalse((output/'.env').exists()); self.assertFalse((output/'node_modules').exists())
            self.assertFalse((output/'assets/ignored.css').exists())
            self.assertIn('assets/ignored.css',data['excluded'])
            state=static_reference.inspect(source,data['record'],data['sha256'])
            self.assertEqual(state['freshness'],'current'); self.assertFalse(state['isolated'])
            (output/'assets/style.css').write_text('tampered')
            state=static_reference.inspect(source,data['record'],data['sha256'])
            self.assertIn('reference_snapshot',state['changed'])
            (source/'assets/ignored.css').write_text('changed')
            state=static_reference.inspect(source,data['record'],data['sha256'])
            self.assertIn('source_snapshot',state['changed'])
            Path(data['record']).write_text('{}')
            with self.assertRaises(ValueError): static_reference.inspect(source,data['record'],data['sha256'])

    def test_excluded_or_hidden_paths_and_overwrites_are_blocked(self):
        with tempfile.TemporaryDirectory(dir='.') as t:
            source,work,selection=setup(Path(t).absolute()); out=work/'static-references'/'one'
            for paths in (['.env','index.html'],['node_modules/secret.js','index.html'],['../x','index.html'],['assets'],[]):
                selection.write_text(json.dumps(paths))
                with self.subTest(paths=paths),self.assertRaises(ValueError): static_reference.materialize(source,selection,out)
                self.assertFalse(out.exists())
            selection.write_text(json.dumps(['index.html'])); static_reference.materialize(source,selection,out)
            with self.assertRaises(ValueError): static_reference.materialize(source,selection,out)
            self.assertEqual((source/'index.html').read_text(),'<html>static reference</html>')

    def test_uncertain_copy_and_cli(self):
        with tempfile.TemporaryDirectory(dir='.') as t:
            source,work,selection=setup(Path(t).absolute()); out=work/'static-references'/'one'
            with patch('tools.static_reference.os.fsync',side_effect=OSError('disk full')):
                with self.assertRaises(static_reference.ReferenceUncertain): static_reference.materialize(source,selection,out)
            self.assertTrue(out.exists()); self.assertEqual((source/'index.html').read_text(),'<html>static reference</html>')
            buf=io.StringIO(); target=work/'static-references'/'two'
            with contextlib.redirect_stdout(buf): code=main(['reference-materialize','--source',str(source),'--selection',str(selection),'--output',str(target),'--json'])
            report=json.loads(buf.getvalue()); self.assertEqual(code,2); self.assertEqual(report['operation'],'applied')
            item=report['reference']; buf=io.StringIO()
            with contextlib.redirect_stdout(buf): code=main(['reference-inspect','--source',str(source),'--file',item['record'],'--sha256',item['sha256'],'--json'])
            self.assertEqual(code,2); self.assertEqual(json.loads(buf.getvalue())['reference']['freshness'],'current')

    def test_mkdir_error_after_creation_is_reported_as_uncertain(self):
        for point in ('parent','output'):
            with self.subTest(point=point), tempfile.TemporaryDirectory(dir='.') as t:
                source,work,selection=setup(Path(t).absolute()); parent=work/'static-references'; output=parent/'one'
                original=Path.mkdir
                def fail_after(path,*args,**kwargs):
                    result=original(path,*args,**kwargs)
                    if path==(parent if point=='parent' else output): raise OSError('synthetic failure after mkdir')
                    return result
                buf=io.StringIO()
                with patch.object(Path,'mkdir',autospec=True,side_effect=fail_after), contextlib.redirect_stdout(buf):
                    code=main(['reference-materialize','--source',str(source),'--selection',str(selection),'--output',str(output),'--json'])
                self.assertEqual(code,4); self.assertEqual(json.loads(buf.getvalue())['operation'],'unknown')
                self.assertTrue(parent.exists()); self.assertEqual(output.exists(),point=='output')
                self.assertEqual((source/'index.html').read_text(),'<html>static reference</html>')

    @unittest.skipUnless(hasattr(os,'symlink'),'symlinks unavailable')
    def test_symlink_in_source_is_rejected(self):
        with tempfile.TemporaryDirectory(dir='.') as t:
            source,work,selection=setup(Path(t).absolute()); (source/'assets/link').symlink_to(source/'index.html')
            with self.assertRaises(ValueError): static_reference.materialize(source,selection,work/'static-references'/'one')

if __name__=='__main__': unittest.main()
