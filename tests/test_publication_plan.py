import contextlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools import queue_md as md
from tools.delivery import materialize
from tools.publication import plan
from tools.lifecycle import publish


@contextlib.contextmanager
def cd(path):
    old=os.getcwd(); os.chdir(path)
    try: yield
    finally: os.chdir(old)


class PublicationPlanTests(unittest.TestCase):
    def test_required_external_resource_is_in_plan_and_not_fetched(self):
        with tempfile.TemporaryDirectory(dir='.') as tmp, cd(tmp):
            root=Path.cwd(); src=root/'source'; src.mkdir(); (src/'index.html').write_text('source')
            work=src/'.work'; work.mkdir(); site=work/'staging'/'run'; site.mkdir(parents=True)
            (site/'index.html').write_text('<!doctype html><html lang="en"><head><title>Page</title><meta name="viewport" content="width=device-width"></head><body><main>Page</main></body></html>')
            data=md.parse(md.template(src))
            data['pages']=[dict(zip(md.TABLES['pages'],['home','Home','/','index.html','confirmed','true','built','reviewed','']))]
            data['resources']=[dict(zip(md.TABLES['resources'],['font','global','https://example.test/font?token=synthetic-secret','true','available','reviewed']))]
            proposal=work/'p.md'; proposal.write_text(md.render(data)); md.commit(src,proposal,'absent','initial')
            selection=work/'selection.json'; selection.write_text(json.dumps(['index.html']))
            delivery=materialize(src,site,selection,work/'deliveries'/'run')
            with patch('socket.socket',side_effect=AssertionError('unexpected network access')):
                result=plan(src,delivery['record'],root/'vanilla')
            self.assertEqual(result['resources'],[{'id':'font','scope':'global','required':True,'declared_status':'available','observation':'external_unverified'}])
            self.assertTrue(any('Обязательные внешние ресурсы не проверены: font' in item for item in result['blockers']))
            self.assertNotIn('synthetic-secret',json.dumps(result['resources']))
            self.assertFalse(result['apply_allowed']); self.assertFalse((root/'vanilla').exists())

    def test_diff_and_stale_delivery_fail_closed(self):
        with tempfile.TemporaryDirectory(dir='.') as tmp, cd(tmp):
            root=Path.cwd(); src=root/'source'; src.mkdir(); (src/'index.html').write_text('source')
            work=src/'.work'; work.mkdir(); site=work/'staging'/'run'; site.mkdir(parents=True)
            (site/'index.html').write_text('<html><body><h1>New</h1></body></html>')
            proposal=work/'p.md'; md.write_template(src,proposal); md.commit(src,proposal,'absent','initial')
            selection=work/'selection.json'; selection.write_text(json.dumps(['index.html']))
            delivery=materialize(src,site,selection,work/'deliveries'/'run')
            target=root/'vanilla'; target.mkdir(); (target/'index.html').write_text('old'); (target/'old.css').write_text('old')
            before=(target/'index.html').read_bytes()
            result=plan(src,delivery['record'],target)
            self.assertEqual(result['diff']['changed'],['index.html']); self.assertEqual(result['diff']['removed'],['old.css'])
            self.assertFalse(result['apply_allowed']); self.assertEqual((target/'index.html').read_bytes(),before)
            self.assertIn('same_filesystem',result['permissions']); self.assertTrue(result['required_approvals'])
            self.assertIn('не гарантируют',result['permissions']['note'])
            with self.assertRaises(ValueError): publish(src,work/'deliveries'/'run')
            (work/'deliveries/run/index.html').write_text('tampered')
            with self.assertRaisesRegex(ValueError,'изменился'): plan(src,delivery['record'],target)
            self.assertEqual((target/'index.html').read_bytes(),before)

if __name__=='__main__': unittest.main()
