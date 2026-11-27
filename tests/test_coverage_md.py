import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from tools import queue_md as md, readiness
from tools.core import LFS
from tools.coverage import diagnostic


def setup(base):
    source=base/'source'; source.mkdir(); (source/'index.html').write_text('source')
    work=source/'.work'; work.mkdir(); site=work/'staging'/'site'; site.mkdir(parents=True)
    (site/'index.html').write_text('<!doctype html><html lang="en"><head><title>Test</title></head><body><main><h1>Home</h1></main></body></html>')
    data=md.parse(md.template(source))
    data['pages']=[dict(zip(md.TABLES['pages'], ['home','Home','/','index.html','confirmed','true','built','reviewed','']))]
    data['aliases']=[dict(zip(md.TABLES['aliases'], ['home','/#home','direct','reviewed']))]
    data['states']=[dict(zip(md.TABLES['states'], ['home','menu','true','390x844,768x1024','']))]
    for row in data['meta']:
        if row['key']=='discovery_status': row['value']='confirmed'
        if row['key']=='confirmation_reason': row['value']='reviewed'
    proposal=work/'proposal.md'; proposal.write_text(md.render(data)); md.commit(source,proposal,'absent','start')
    return source,site,data


class CoverageTests(unittest.TestCase):
    def test_all_routes_and_required_states_are_planned_but_not_pass(self):
        with tempfile.TemporaryDirectory(dir='.') as t:
            src,site,_=setup(Path(t).absolute()); result=diagnostic(src,site)
            self.assertEqual(result['coverage']['planned'],8); self.assertEqual(result['coverage']['executed'],0)
            self.assertEqual(sum(1 for x in result['coverage']['entries'] if x['route']=='/#home'),3)
            self.assertTrue(all(x['outcome']=='unknown' for x in result['coverage']['entries']))
            self.assertFalse(result['eligible']); self.assertNotEqual(result['status'],'PASS')
            self.assertTrue(any('сценария' in x for x in result['warnings']))

    def test_missing_required_page_and_resource_fail(self):
        with tempfile.TemporaryDirectory(dir='.') as t:
            src,site,data=setup(Path(t).absolute()); (site/'index.html').unlink(); (site/'other.html').write_text('other')
            work=src/'.work'; before=md.validate_file(src,work/'PAGE-QUEUE.md')['sha256']
            for row in data['meta']:
                if row['key']=='discovery_status': row['value']='review_required'
            data['resources']=[dict(zip(md.TABLES['resources'],['logo','global','logo.svg','true','available','reviewed']))]
            proposal=work/'next.md'; proposal.write_text(md.render(data)); md.commit(src,proposal,before,'add resource')
            result=diagnostic(src,site)
            self.assertEqual(result['status'],'FAIL')
            self.assertTrue(any('обязательной страницы' in x for x in result['issues']))
            self.assertTrue(any('обязательного ресурса' in x for x in result['issues']))

    def test_resource_observations_and_external_required_blocker(self):
        with tempfile.TemporaryDirectory(dir='.') as t:
            src,site,data=setup(Path(t).absolute()); work=src/'.work'
            for row in data['meta']:
                if row['key']=='discovery_status': row['value']='review_required'
            values=[('logo','global','logo.svg','true','available','reviewed'),
                    ('font','global','font.woff2','true','available','reviewed'),
                    ('optional','home','absent.svg','false','missing','reviewed'),
                    ('remote','global','https://assets.example.test/font?secret=synthetic-token','true','available','reviewed'),
                    ('remote-opt','home','https://assets.example.test/extra','false','unknown','reviewed'),
                    ('unsettled','global','logo.svg','true','unknown','needs review')]
            data['resources']=[dict(zip(md.TABLES['resources'],row)) for row in values]
            (site/'logo.svg').write_text('<svg></svg>'); (site/'font.woff2').write_bytes(LFS+b'oid sha256:synthetic\n')
            proposal=work/'next.md'; proposal.write_text(md.render(data)); md.commit(src,proposal,md.sha((work/'PAGE-QUEUE.md').read_bytes()),'add resources')
            result=diagnostic(src,site); resources={r['id']:r for r in result['resources']}
            self.assertEqual({k:v['observation'] for k,v in resources.items()},
                             {'logo':'present','font':'lfs_pointer','optional':'missing','remote':'external_unverified','remote-opt':'external_unverified','unsettled':'present'})
            self.assertEqual(result['status'],'FAIL'); self.assertTrue(any('LFS' in x for x in result['issues']))
            self.assertNotIn('synthetic-token',json.dumps(result['resources']))
            state=readiness.evaluate(src,site); self.assertFalse(state['eligible'])
            self.assertTrue(any('Обязательные внешние ресурсы не проверены: remote' in b for b in state['blockers']))
            self.assertEqual(resources['unsettled']['declared_status'],'unknown')
            self.assertTrue(any('очереди обязательные ресурсы отмечены missing или unknown: unsettled' in b for b in state['blockers']))
            self.assertFalse(any('remote-opt' in b for b in state['blockers']))
            self.assertEqual(state['resources'],result['resources'])
            (site/'font.woff2').write_bytes(b'font bytes')
            self.assertEqual({r['id']:r['observation'] for r in diagnostic(src,site)['resources']}['font'],'present')

    def test_resource_replaced_after_snapshot_is_rejected(self):
        from tools import coverage
        with tempfile.TemporaryDirectory(dir='.') as t:
            src,site,data=setup(Path(t).absolute()); work=src/'.work'
            for row in data['meta']:
                if row['key']=='discovery_status': row['value']='review_required'
            data['resources']=[dict(zip(md.TABLES['resources'],['logo','global','logo.svg','true','available','reviewed']))]
            logo=site/'logo.svg'; logo.write_bytes(b'original')
            proposal=work/'next.md'; proposal.write_text(md.render(data)); md.commit(src,proposal,md.sha((work/'PAGE-QUEUE.md').read_bytes()),'resource')
            original=coverage.read_snapshot_prefix
            def replace(path,entry,limit):
                logo.write_bytes(b'tampered')
                return original(path,entry,limit)
            with patch('tools.coverage.read_snapshot_prefix',side_effect=replace):
                with self.assertRaisesRegex(ValueError,'изменился'): diagnostic(src,site)

    def test_static_page_read_is_bound_to_delivery_snapshot(self):
        from tools import snapshot_access
        with tempfile.TemporaryDirectory(dir='.') as t:
            src,site,_=setup(Path(t).absolute()); page=site/'index.html'
            original=snapshot_access.read_snapshot_file; changed=False
            def replace(path,entry,limit):
                nonlocal changed
                if path==page and not changed:
                    changed=True; page.write_bytes(b'x'*entry['size'])
                return original(path,entry,limit)
            with patch('tools.snapshot_access.read_snapshot_file',side_effect=replace):
                try: result=diagnostic(src,site)
                except (OSError,ValueError): pass
                else: self.assertEqual(result['status'],'FAIL')
            self.assertTrue(changed)

    def test_directly_edited_queue_does_not_enter_diagnostic_runs(self):
        with tempfile.TemporaryDirectory(dir='.') as t:
            src,site,_=setup(Path(t).absolute()); canon=src/'.work/PAGE-QUEUE.md'
            canon.write_text(canon.read_text()+'uncommitted note\n')
            with self.assertRaises(ValueError): diagnostic(src,site)

    def test_stale_source_is_never_eligible(self):
        with tempfile.TemporaryDirectory(dir='.') as t:
            src,site,_=setup(Path(t).absolute()); (src/'index.html').write_text('changed')
            result=diagnostic(src,site); self.assertEqual(result['freshness'],'stale'); self.assertFalse(result['eligible'])

if __name__=='__main__': unittest.main()
