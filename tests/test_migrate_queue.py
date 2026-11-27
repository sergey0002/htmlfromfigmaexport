import contextlib
import io
import json
import os
import subprocess
import signal
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools import migrate_queue as migration, queue_md as md
from tools.queue import save, load
from tools.cli import main


def setup(base):
    source=base/'source'; source.mkdir(); (source/'index.html').write_text('reference')
    data={'schema_version':1, 'source':{'fingerprint':'old','unknown_source_field':'preserved'},
          'discovery':{'status':'unconfirmed','unresolved':['classify me'],'mystery':'kept'},
          'unresolved_links':[{'reference_route':'/unknown','reason':'needs research'}],
          'extra':{'unknown':'preserved'},
          'pages':[{'id':'home','title':'Home','reference_route':'/', 'reference_aliases':['/#home'],
                    'output':'index.html','confirmation':'confirmed','work_status':'built',
                    'evidence':['index.html'], 'custom':{'keep':1},
                    'states':[{'id':'menu','required':True,'scenario':None,'legacy_flag':'preserve'}],
                    'checks':{'browser':'checked'}}]}
    save(source/'.work/manifest.json',data,create=True)
    return source,data


@unittest.skipUnless(os.name == 'posix', 'POSIX migration requires flock')
class MigrationTests(unittest.TestCase):
    def test_dry_run_and_apply_preserve_original_bytes_and_archive(self):
        with tempfile.TemporaryDirectory(dir='.') as t:
            src,data=setup(Path(t).absolute()); work=src/'.work'
            old=(work/'manifest.json').read_bytes(); old_md=(work/'PAGE-QUEUE.md').read_bytes()
            info=md.inspect_legacy(src)
            self.assertEqual(info['counts'],{'pages':1,'aliases':1,'states':1,'unresolved_links':1,'notes':1})
            self.assertIn('extra',info['unknown_fields']['top_level'])
            self.assertIn('custom',info['unknown_fields']['pages']['home'])
            plan_path=work/'migration-plan.json'; plan=migration.create_plan(src,plan_path)
            self.assertEqual((work/'manifest.json').read_bytes(),old)
            self.assertEqual((work/'PAGE-QUEUE.md').read_bytes(),old_md)
            self.assertEqual(plan['unclassified_discovery'],['classify me'])
            self.assertEqual(md.parse(plan['proposal'])['issues'],[])
            with self.assertRaises(ValueError): migration.apply(src,plan_path,plan['manifest_sha256'],plan['markdown_sha256'],False)
            result=migration.apply(src,plan_path,plan['manifest_sha256'],plan['markdown_sha256'],True)
            run=work/'migrations'/result['migration_id']
            self.assertEqual((run/'manifest.json').read_bytes(),old); self.assertEqual((run/'PAGE-QUEUE.md').read_bytes(),old_md)
            self.assertEqual((work/'manifest.json').read_bytes(),old)
            self.assertEqual(json.loads((run/'manifest.json').read_text()),data)
            self.assertEqual(migration.inspect(src,result['migration_id'])['journal']['phase'],'complete')
            parsed=md.parse((work/'PAGE-QUEUE.md').read_text()); self.assertEqual(len(parsed['states']),1)
            meta=dict((x['key'],x['value']) for x in parsed['meta']); self.assertEqual(meta['discovery_status'],'review_required'); self.assertEqual(meta['legacy_review'],'unclassified')
            for row in parsed['meta']:
                if row['key']=='discovery_status': row['value']='confirmed'
                if row['key']=='confirmation_reason': row['value']='reviewed'
            with self.assertRaises(ValueError): md.parse(md.render(parsed))
            with self.assertRaises(ValueError): load(work/'manifest.json')
            with self.assertRaises(ValueError): save(work/'manifest.json',data)
            proposal=work/'edit.md'; proposal.write_text((work/'PAGE-QUEUE.md').read_text()+'notes\n')
            result2=md.commit(src,proposal,result['queue_sha256'],'editor note')
            self.assertEqual(result2['operation'],'applied')

    def test_nonstandard_unicode_and_unresolved_scenario_are_preserved_on_copy(self):
        with tempfile.TemporaryDirectory(dir='.') as t:
            src,data=setup(Path(t).absolute()); work=src/'.work'
            page=data['pages'][0]; page['title']='Раздел | путь \\ тест'; page['evidence']=['строка | \\ источник']
            page['states'][0]['scenario']='scenarios/missing.json'; page['custom']={'nested':['данные',{'symbol':'|'}]}
            data['unresolved_links'].append({'reference_route':'/#unclear','reason':'не решено','extra':{'keep':True}})
            save(work/'manifest.json',data)
            original=(work/'manifest.json').read_bytes(); markdown=(work/'PAGE-QUEUE.md').read_bytes()
            plan=migration.create_plan(src,work/'unicode-plan.json'); parsed=md.parse(plan['proposal'])
            self.assertEqual(parsed['pages'][0]['title'],page['title']); self.assertEqual(parsed['pages'][0]['evidence'],page['evidence'][0])
            self.assertEqual(parsed['states'][0]['scenario'],'scenarios/missing.json')
            self.assertEqual(len(plan['unclassified_links']),2)
            result=migration.apply(src,work/'unicode-plan.json',plan['manifest_sha256'],plan['markdown_sha256'],True)
            run=work/'migrations'/result['migration_id']
            self.assertEqual((run/'manifest.json').read_bytes(),original); self.assertEqual((run/'PAGE-QUEUE.md').read_bytes(),markdown)
            self.assertEqual(json.loads((run/'manifest.json').read_bytes()),data)
            compiled=md.compile_queue((work/'PAGE-QUEUE.md').read_text(),src)
            self.assertIsNone(compiled['semantic']['states'][0]['scenario_sha256'])
            meta={x['key']:x['value'] for x in parsed['meta']}; self.assertEqual(meta['discovery_status'],'review_required')

    def test_empty_legacy_queue_remains_unconfirmed_on_copy(self):
        with tempfile.TemporaryDirectory(dir='.') as t:
            src,data=setup(Path(t).absolute()); work=src/'.work'; data['pages']=[]; save(work/'manifest.json',data)
            plan=migration.create_plan(src,work/'empty-plan.json')
            self.assertEqual(plan['counts']['pages'],0)
            self.assertEqual(md.parse(plan['proposal'])['pages'],[])
            result=migration.apply(src,work/'empty-plan.json',plan['manifest_sha256'],plan['markdown_sha256'],True)
            parsed=md.parse((work/'PAGE-QUEUE.md').read_text())
            self.assertEqual(parsed['pages'],[]); self.assertEqual(migration.inspect(src,result['migration_id'])['journal']['phase'],'complete')
            self.assertEqual({x['key']:x['value'] for x in parsed['meta']}['discovery_status'],'review_required')

    def test_dry_run_cli_reports_written_plan_and_partial_write(self):
        with tempfile.TemporaryDirectory(dir='.') as t:
            src,_=setup(Path(t).absolute()); work=src/'.work'; before=(work/'PAGE-QUEUE.md').read_bytes()
            out=io.StringIO()
            with contextlib.redirect_stdout(out):
                code=main(['queue-md','migrate-dry-run','--source',str(src),'--output',str(work/'good.json'),'--json'])
            self.assertEqual(code,2); self.assertEqual(json.loads(out.getvalue())['operation'],'applied')
            self.assertTrue((work/'good.json').is_file()); self.assertEqual((work/'PAGE-QUEUE.md').read_bytes(),before)
            original=md._write_new
            def partial(path,content):
                if path==work/'partial.json':
                    path.write_bytes(content[:8]); raise OSError('injected disk error')
                return original(path,content)
            out=io.StringIO()
            with patch('tools.migrate_queue.md._write_new',side_effect=partial),contextlib.redirect_stdout(out):
                code=main(['queue-md','migrate-dry-run','--source',str(src),'--output',str(work/'partial.json'),'--json'])
            self.assertEqual(code,4); self.assertEqual(json.loads(out.getvalue())['operation'],'unknown')
            self.assertEqual(len((work/'partial.json').read_bytes()),8); self.assertEqual((work/'PAGE-QUEUE.md').read_bytes(),before)

    def test_partial_archive_is_unknown_and_blocks_another_apply(self):
        for fault in ('mkdir','archive-write'):
            with self.subTest(fault=fault), tempfile.TemporaryDirectory(dir='.') as t:
                src,_=setup(Path(t).absolute()); work=src/'.work'; plan=migration.create_plan(src,work/'plan.json')
                before=[(work/n).read_bytes() for n in ('manifest.json','PAGE-QUEUE.md')]
                original_mkdir=Path.mkdir; original_write=md._write_new
                def after_mkdir(path,*args,**kwargs):
                    result=original_mkdir(path,*args,**kwargs)
                    if path.parent==work/'migrations': raise OSError('failure after mkdir')
                    return result
                def partial(path,content):
                    if path.name=='PAGE-QUEUE.md' and path.parent.parent==work/'migrations':
                        path.write_bytes(content[:8]); raise OSError('failure during archive write')
                    return original_write(path,content)
                out=io.StringIO()
                target=patch.object(Path,'mkdir',autospec=True,side_effect=after_mkdir) if fault=='mkdir' else patch('tools.migrate_queue.md._write_new',side_effect=partial)
                with target,contextlib.redirect_stdout(out):
                    code=main(['queue-md','migrate-apply','--source',str(src),'--plan',str(work/'plan.json'),
                               '--expected-manifest-sha256',plan['manifest_sha256'],'--expected-markdown-sha256',plan['markdown_sha256'],
                               '--acknowledge-offline-writers','--json'])
                self.assertEqual(code,4); self.assertEqual(json.loads(out.getvalue())['operation'],'unknown')
                runs=list((work/'migrations').iterdir()); self.assertEqual(len(runs),1)
                self.assertFalse((work/md.MARKER).exists())
                self.assertEqual([(work/n).read_bytes() for n in ('manifest.json','PAGE-QUEUE.md')],before)
                with self.assertRaises((ValueError,OSError)): migration.inspect(src,runs[0].name)
                with self.assertRaises((ValueError,OSError)): migration.recover(src,runs[0].name,True)
                with self.assertRaisesRegex(ValueError,'архив миграции'): migration.apply(src,work/'plan.json',plan['manifest_sha256'],plan['markdown_sha256'],True)
                self.assertEqual(list((work/'migrations').iterdir()),runs)

    def test_prepared_archive_blocks_retry_but_can_recover_forward(self):
        with tempfile.TemporaryDirectory(dir='.') as t:
            src,_=setup(Path(t).absolute()); work=src/'.work'; plan=migration.create_plan(src,work/'plan.json')
            verify=migration._verify_archive
            def fail_after(*args): verify(*args); raise OSError('injected before marker')
            with patch('tools.migrate_queue._verify_archive',side_effect=fail_after):
                with self.assertRaises(migration.MigrationUncertain): migration.apply(src,work/'plan.json',plan['manifest_sha256'],plan['markdown_sha256'],True)
            run=next((work/'migrations').iterdir()); state=migration.inspect(src,run.name)
            self.assertEqual(state['journal']['phase'],'prepared'); self.assertEqual(state['marker_state'],'absent')
            with self.assertRaisesRegex(ValueError,'не завершена'): migration.apply(src,work/'plan.json',plan['manifest_sha256'],plan['markdown_sha256'],True)
            self.assertEqual(migration.recover(src,run.name,True)['status'],'complete')
            self.assertEqual(migration.inspect(src,run.name)['journal']['phase'],'complete')

    def test_conflict_and_changed_source_refused_before_cutover(self):
        with tempfile.TemporaryDirectory(dir='.') as t:
            src,data=setup(Path(t).absolute()); work=src/'.work'
            (work/'PAGE-QUEUE.md').write_text('human edits')
            with self.assertRaisesRegex(ValueError,'отличается'): migration.prepare(src)
            save(work/'manifest.json',data)
            plan=migration.create_plan(src,work/'plan.json')
            (src/'index.html').write_text('changed')
            with self.assertRaisesRegex(ValueError,'устарел'): migration.apply(src,work/'plan.json',plan['manifest_sha256'],plan['markdown_sha256'],True)
            self.assertFalse((work/md.MARKER).exists())

    def test_fault_after_marker_blocks_writers_and_recovery_finishes(self):
        with tempfile.TemporaryDirectory(dir='.') as t:
            src,data=setup(Path(t).absolute()); work=src/'.work'; plan=migration.create_plan(src,work/'plan.json')
            with patch('tools.migrate_queue._replace_queue',side_effect=OSError('injected')):
                with self.assertRaises(migration.MigrationUncertain): migration.apply(src,work/'plan.json',plan['manifest_sha256'],plan['markdown_sha256'],True)
            run=next((work/'migrations').iterdir()); state=migration.inspect(src,run.name)
            self.assertEqual(state['queue_state'],'legacy'); self.assertEqual(state['marker_state'],'valid')
            with self.assertRaises(ValueError): save(work/'manifest.json',data)
            with self.assertRaises(ValueError): md.validate_file(src,work/'PAGE-QUEUE.md')
            recovered=migration.recover(src,run.name,True); self.assertEqual(recovered['operation'],'applied')
            state=migration.inspect(src,run.name); self.assertEqual(state['queue_state'],'proposal'); self.assertEqual(state['journal']['phase'],'complete')
            self.assertEqual(migration.recover(src,run.name,True)['operation'],'not_applied')

    def test_sigkill_before_marker_never_allows_blind_reapply(self):
        for checkpoint in ('archive','prepared'):
            with self.subTest(checkpoint=checkpoint), tempfile.TemporaryDirectory(dir='.') as t:
                src,_=setup(Path(t).absolute()); work=src/'.work'; plan=migration.create_plan(src,work/'plan.json')
                before=[(work/n).read_bytes() for n in ('manifest.json','PAGE-QUEUE.md')]
                script='''import os, sys
from tools import migrate_queue as m
if sys.argv[5] == 'archive':
    original=m.md._write_new
    def kill_after(path,data):
        original(path,data)
        if path.name == 'manifest.json': os.kill(os.getpid(),9)
    m.md._write_new=kill_after
else:
    original=m._verify_archive
    def kill_after(*args):
        original(*args)
        os.kill(os.getpid(),9)
    m._verify_archive=kill_after
m.apply(sys.argv[1],sys.argv[2],sys.argv[3],sys.argv[4],True)
'''
                proc=subprocess.run([sys.executable,'-c',script,str(src),str(work/'plan.json'),plan['manifest_sha256'],plan['markdown_sha256'],checkpoint],check=False)
                self.assertEqual(proc.returncode,-signal.SIGKILL); self.assertTrue((work/'.queue.lock').exists())
                run=next((work/'migrations').iterdir()); self.assertFalse((work/md.MARKER).exists())
                self.assertEqual([(work/n).read_bytes() for n in ('manifest.json','PAGE-QUEUE.md')],before)
                if checkpoint=='prepared':
                    self.assertEqual(migration.inspect(src,run.name)['journal']['phase'],'prepared')
                    self.assertEqual(migration.recover(src,run.name,True,clear_stale_lock=True)['status'],'complete')
                else:
                    with self.assertRaises((ValueError,OSError)): migration.recover(src,run.name,True,clear_stale_lock=True)
                    with self.assertRaisesRegex(ValueError,'архив миграции'):
                        migration.apply(src,work/'plan.json',plan['manifest_sha256'],plan['markdown_sha256'],True)
                    self.assertEqual(len(list((work/'migrations').iterdir())),1)
                    self.assertEqual([(work/n).read_bytes() for n in ('manifest.json','PAGE-QUEUE.md')],before)

    def test_hard_process_exit_requires_explicit_stale_lock_recovery(self):
        with tempfile.TemporaryDirectory(dir='.') as t:
            src,data=setup(Path(t).absolute()); work=src/'.work'; plan=migration.create_plan(src,work/'plan.json')
            script = """import os, sys
from tools import migrate_queue as m
m._replace_queue = lambda *args: os.kill(os.getpid(), 9)
m.apply(sys.argv[1],sys.argv[2],sys.argv[3],sys.argv[4],True)
"""
            proc=subprocess.run([sys.executable,'-c',script,str(src),str(work/'plan.json'),plan['manifest_sha256'],plan['markdown_sha256']],check=False)
            self.assertEqual(proc.returncode,-signal.SIGKILL); self.assertTrue((work/'.queue.lock').exists())
            run=next((work/'migrations').iterdir()); self.assertEqual(migration.inspect(src,run.name)['queue_state'],'legacy')
            with self.assertRaises(OSError): migration.recover(src,run.name,True)
            self.assertEqual(migration.recover(src,run.name,True,clear_stale_lock=True)['status'],'complete')
            self.assertFalse((work/'.queue.lock').exists())

    def test_fault_after_markdown_replacement_recovers_forward(self):
        with tempfile.TemporaryDirectory(dir='.') as t:
            src,data=setup(Path(t).absolute()); work=src/'.work'; plan=migration.create_plan(src,work/'plan.json')
            with patch('tools.migrate_queue.md._write_head',side_effect=OSError('injected')):
                with self.assertRaises(migration.MigrationUncertain): migration.apply(src,work/'plan.json',plan['manifest_sha256'],plan['markdown_sha256'],True)
            run=next((work/'migrations').iterdir())
            self.assertEqual(migration.inspect(src,run.name)['queue_state'],'proposal')
            with self.assertRaises(ValueError): md.validate_file(src,work/'PAGE-QUEUE.md')
            self.assertEqual(migration.recover(src,run.name,True)['status'],'complete')
            self.assertEqual(migration.inspect(src,run.name)['journal']['phase'],'complete')

    def test_recovery_refuses_external_change(self):
        with tempfile.TemporaryDirectory(dir='.') as t:
            src,data=setup(Path(t).absolute()); work=src/'.work'; plan=migration.create_plan(src,work/'plan.json')
            with patch('tools.migrate_queue._replace_queue',side_effect=OSError('injected')):
                with self.assertRaises(migration.MigrationUncertain): migration.apply(src,work/'plan.json',plan['manifest_sha256'],plan['markdown_sha256'],True)
            run=next((work/'migrations').iterdir()); (work/'PAGE-QUEUE.md').write_text('external editor')
            with self.assertRaises(ValueError): migration.recover(src,run.name,True)
            self.assertEqual((work/'PAGE-QUEUE.md').read_text(),'external editor')

if __name__=='__main__': unittest.main()
