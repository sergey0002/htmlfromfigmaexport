import contextlib
import io
import json
import os
import signal
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools import queue_md as md
from tools.cli import main
from tools.queue import save, load


def run(*args):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf): code = main([*args, '--json'])
    return code, json.loads(buf.getvalue())


def fixture(base):
    src = base/'source'; src.mkdir(); (src/'index.html').write_text('hello')
    (src/'.work').mkdir()
    return src


def page():
    return dict(zip(md.TABLES['pages'], ['home','Главная','/','index.html','confirmed','true','pending','исследование','']))


class MarkdownQueueTests(unittest.TestCase):
    def test_empty_template_parse_and_new_queue_commit(self):
        with tempfile.TemporaryDirectory(dir='.') as tmp:
            src = fixture(Path(tmp).absolute()); proposal = src/'.work/proposal.md'
            code, created = run('queue-md','template','--source',str(src),'--output',str(proposal))
            self.assertEqual(code, 2); self.assertEqual(created['operation'],'applied'); self.assertEqual(md.parse(proposal.read_text())['pages'], [])
            code, checked = run('queue-md','validate','--source',str(src),'--file',str(proposal))
            self.assertEqual(code, 2); self.assertEqual(checked['queue']['freshness'], 'current')
            self.assertFalse(checked['queue']['eligible'])
            code, applied = run('queue-md','commit','--source',str(src),'--file',str(proposal),'--expect-absent','--reason','initial queue')
            self.assertEqual(code, 2); self.assertEqual(applied['operation'], 'applied')
            self.assertEqual((src/'.work/PAGE-QUEUE.md').read_bytes(),proposal.read_bytes())
            self.assertEqual((src/'.work/.queue-md-active').read_text(), 'queue-md-v1\n')
            self.assertEqual(len(list((src/'.work/queue-history').iterdir())),1)
            self.assertEqual(run('queue-md','commit','--source',str(src),'--file',str(proposal),'--expect-absent','--reason','no overwrite')[0],3)

    def test_template_prevalidation_and_partial_creation(self):
        with tempfile.TemporaryDirectory(dir='.') as tmp:
            base=Path(tmp).absolute(); src=base/'source'; src.mkdir(); (src/'index.html').write_text('hello'); work=src/'.work'
            for out in (base/'outside',work/'missing'/'proposal.md',work/'PAGE-QUEUE.md',work/'manifest.json'):
                code,result=run('queue-md','template','--source',str(src),'--output',str(out))
                self.assertEqual(code,3); self.assertEqual(result['operation'],'not_applied'); self.assertFalse(work.exists())
            proposal=work/'proposal.md'
            def partial(path,data): path.write_bytes(data[:7]); raise OSError('disk full')
            with patch('tools.queue_md._write_new',side_effect=partial):
                code,result=run('queue-md','template','--source',str(src),'--output',str(proposal))
            self.assertEqual(code,4); self.assertEqual(result['operation'],'unknown'); self.assertEqual(len(proposal.read_bytes()),7)
            self.assertFalse((work/'PAGE-QUEUE.md').exists())

    def test_history_partial_write_refuses_first_or_later_commit_and_recovery(self):
        for existing in (False,True):
            with self.subTest(existing=existing), tempfile.TemporaryDirectory(dir='.') as tmp:
                src=fixture(Path(tmp).absolute()); work=src/'.work'; proposal=work/'proposal.md'; md.write_template(src,proposal)
                first=md.commit(src,proposal,'absent','initial') if existing else None
                proposal.write_text(proposal.read_text()+'notes\n'); expected=first['sha256'] if first else 'absent'
                original=md._write_new
                def partial(path,data):
                    if path.parent==work/'queue-history': path.write_bytes(data[:12]); raise OSError('injected history failure')
                    return original(path,data)
                args=['queue-md','commit','--source',str(src),'--file',str(proposal),'--reason','test']
                args+=['--expected-sha256',expected] if first else ['--expect-absent']
                with patch('tools.queue_md._write_new',side_effect=partial): code,result=run(*args)
                self.assertEqual(code,4); self.assertEqual(result['operation'],'unknown')
                files=list((work/'queue-history').iterdir()); partial_files=[p for p in files if p.stat().st_size==12]; self.assertEqual(len(partial_files),1)
                self.assertEqual((work/'PAGE-QUEUE.md').exists(),existing)
                if existing: self.assertEqual(md.sha((work/'PAGE-QUEUE.md').read_bytes()),expected)
                self.assertEqual(run(*args)[0],3); self.assertEqual(len(list((work/'queue-history').iterdir())),len(files))
                if existing:
                    valid=next(p for p in files if p not in partial_files)
                    with self.assertRaisesRegex(ValueError,'история'): md.recover_commit(src,valid,expected,True)

    @unittest.skipUnless(os.name=='posix', 'SIGKILL semantics require POSIX')
    def test_sigkill_during_history_write_does_not_allow_blind_retry(self):
        for point in ('partial','complete'):
            with self.subTest(point=point), tempfile.TemporaryDirectory(dir='.') as tmp:
                src=fixture(Path(tmp).absolute()); work=src/'.work'; proposal=work/'p.md'; md.write_template(src,proposal)
                script='''import os, sys
from tools import queue_md as m
original=m._write_new
def interrupted(path,data):
    if path.parent.name=='queue-history':
        if sys.argv[3]=='partial': path.write_bytes(data[:12])
        else: original(path,data)
        os.kill(os.getpid(),9)
    return original(path,data)
m._write_new=interrupted
m.commit(sys.argv[1],sys.argv[2],'absent','initial')
'''
                proc=subprocess.run([sys.executable,'-c',script,str(src),str(proposal),point],check=False)
                self.assertEqual(proc.returncode,-signal.SIGKILL); self.assertTrue((work/'.queue.lock').exists())
                self.assertFalse((work/'PAGE-QUEUE.md').exists()); self.assertFalse((work/md.MARKER).exists())
                history=next((work/'queue-history').iterdir())
                with self.assertRaises(OSError): md.commit(src,proposal,'absent','retry')
                # Test fixture only: all subprocesses have exited and their files are preserved.
                (work/'.queue.lock').unlink()
                if point=='partial':
                    with self.assertRaisesRegex(ValueError,'история'): md.commit(src,proposal,'absent','retry')
                    with self.assertRaises(ValueError): md.recover_commit(src,history,'absent',True)
                    self.assertFalse((work/'PAGE-QUEUE.md').exists())
                else:
                    self.assertEqual(md.recover_commit(src,history,'absent',True)['status'],'recovered')
                    self.assertEqual((work/'PAGE-QUEUE.md').read_bytes(),proposal.read_bytes())

    def test_inconsistent_history_hash_blocks_commit_and_validation_binding(self):
        with tempfile.TemporaryDirectory(dir='.') as tmp:
            src=fixture(Path(tmp).absolute()); work=src/'.work'; proposal=work/'p.md'; md.write_template(src,proposal)
            first=md.commit(src,proposal,'absent','first'); history=next((work/'queue-history').iterdir())
            entry=json.loads(history.read_text()); entry['after']='different'; history.write_text(json.dumps(entry))
            with self.assertRaisesRegex(ValueError,'история'): md.commit(src,proposal,first['sha256'],'second')
            with self.assertRaisesRegex(ValueError,'история'): md._recorded_requirements(work,(work/'PAGE-QUEUE.md').read_bytes())
            self.assertEqual(md.sha((work/'PAGE-QUEUE.md').read_bytes()),first['sha256'])

    def test_cas_conflict_history_and_free_text(self):
        with tempfile.TemporaryDirectory(dir='.') as tmp:
            src = fixture(Path(tmp).absolute()); proposal = src/'.work/p.md'
            md.write_template(src,proposal); first = md.commit(src,proposal,'absent','first')
            proposal.write_text(proposal.read_text()+'Agent notes\n')
            with self.assertRaisesRegex(ValueError,'Конфликт'): md.commit(src,proposal,'0'*64,'change')
            self.assertNotIn('Agent notes',(src/'.work/PAGE-QUEUE.md').read_text())
            second = md.commit(src,proposal,first['sha256'],'notes')
            self.assertEqual(first['requirements_hash'],second['requirements_hash'])
            self.assertIn('+Agent notes', second['diff'])
            self.assertEqual(len(list((src/'.work/queue-history').iterdir())),2)

    def test_fixed_requirements_vector(self):
        with tempfile.TemporaryDirectory(dir='.') as tmp:
            src=fixture(Path(tmp).absolute()); data=md.parse(md.template(src))
            for row in data['meta']:
                if row['key']=='source_snapshot': row['value']='0'*64
            result=md.compile_queue(md.render(data),src)
            self.assertEqual(result['requirements_hash'],'66ad11756056cd95e62c40e8db81eb08e9a3a0b83ff7f715d2522e074aff87c3')
            self.assertEqual(result['freshness'],'stale')

    def test_confirmed_gate_and_escaping(self):
        with tempfile.TemporaryDirectory(dir='.') as tmp:
            src=fixture(Path(tmp).absolute()); data=md.parse(md.template(src)); data['pages']=[page()]
            data['pages'][0]['title']='A | B \\ C'
            meta={x['key']:x for x in data['meta']}; meta['discovery_status']['value']='confirmed'; meta['confirmation_reason']['value']='reviewed'
            text=md.render(data); self.assertEqual(md.parse(text)['pages'][0]['title'],'A | B \\ C')
            data['issues'].append(dict(zip(md.TABLES['issues'],['i1','/unknown','decision_required','open','',''])))
            with self.assertRaisesRegex(ValueError,'confirmed'): md.parse(md.render(data))
            data['issues']=[]; data['pages'][0]['confirmation']='candidate'
            with self.assertRaisesRegex(ValueError,'confirmed'): md.parse(md.render(data))

    def test_reject_bad_structure_routes_fields_and_traversal(self):
        with tempfile.TemporaryDirectory(dir='.') as tmp:
            src=fixture(Path(tmp).absolute()); data=md.parse(md.template(src)); data['pages']=[page()]
            text=md.render(data)
            for broken in (text.replace('## states','## state'), text.replace('QUEUE:BEGIN v1','QUEUE:BEGIN v9'), text.replace('| home |','| home | extra |',1), text.replace('Главная','bad\\q')):
                with self.subTest(broken=broken[:50]), self.assertRaises(ValueError): md.parse(broken)
            data['aliases']=[dict(zip(md.TABLES['aliases'], ['home','/','test','test']))]
            with self.assertRaises(ValueError): md.parse(md.render(data))
            data['pages'][0]['reference_route']='/foo'
            data['aliases']=[dict(zip(md.TABLES['aliases'], ['home','/%66oo','test','test']))]
            with self.assertRaises(ValueError): md.parse(md.render(data))
            data['aliases']=[]; data['states']=[dict(zip(md.TABLES['states'], ['home','menu','true','390x844','../secret']))]
            with self.assertRaises(ValueError): md.parse(md.render(data))

    def test_requirements_hash_progress_vs_requirements_and_scenario(self):
        with tempfile.TemporaryDirectory(dir='.') as tmp:
            src=fixture(Path(tmp).absolute()); data=md.parse(md.template(src)); data['pages']=[page()]
            data['states']=[dict(zip(md.TABLES['states'], ['home','menu','true','390x844','scenario.json']))]
            scenario=src/'.work/scenario.json'; scenario.write_text('one')
            h=lambda: md.compile_queue(md.render(data),src)['requirements_hash']
            original=h(); data['pages'][0]['work_status']='built'; self.assertEqual(h(), original)
            data['pages'][0]['required']='false'; data['pages'][0]['optional_reason']='optional'; self.assertNotEqual(h(), original)
            data['pages'][0]['required']='true'; data['pages'][0]['optional_reason']=''; self.assertEqual(h(), original)
            scenario.write_text('two'); self.assertNotEqual(h(),original)

    def test_confirmed_revision_requires_review_after_requirement_or_scenario_change(self):
        with tempfile.TemporaryDirectory(dir='.') as tmp:
            src=fixture(Path(tmp).absolute()); work=src/'.work'; data=md.parse(md.template(src)); data['pages']=[page()]
            data['states']=[dict(zip(md.TABLES['states'], ['home','menu','true','390x844','scenario.json']))]
            (work/'scenario.json').write_text('original')
            for row in data['meta']:
                if row['key']=='discovery_status': row['value']='confirmed'
                if row['key']=='confirmation_reason': row['value']='reviewed'
            proposal=work/'p.md'; proposal.write_text(md.render(data)); result=md.commit(src,proposal,'absent','confirm')
            self.assertTrue(md.validate_file(src,work/'PAGE-QUEUE.md')['confirmation_current'])
            (work/'scenario.json').write_text('different')
            self.assertFalse(md.validate_file(src,work/'PAGE-QUEUE.md')['confirmation_current'])
            with self.assertRaisesRegex(ValueError,'review_required'): md.commit(src,proposal,result['sha256'],'changed scenario')
            for row in data['meta']:
                if row['key']=='discovery_status': row['value']='review_required'
            proposal.write_text(md.render(data)); result=md.commit(src,proposal,result['sha256'],'review scenario')
            for row in data['meta']:
                if row['key']=='discovery_status': row['value']='confirmed'
            proposal.write_text(md.render(data)); md.commit(src,proposal,result['sha256'],'reconfirmed')
            self.assertTrue(md.validate_file(src,work/'PAGE-QUEUE.md')['confirmation_current'])

    def test_legacy_not_overwritten_and_v1_writer_checks_marker(self):
        with tempfile.TemporaryDirectory(dir='.') as tmp:
            src=fixture(Path(tmp).absolute()); work=src/'.work'; proposal=work/'p.md'; md.write_template(src,proposal)
            legacy={'schema_version':1,'source':{},'discovery':{'status':'unconfirmed'},'pages':[],'unresolved_links':[]}
            save(work/'manifest.json',legacy,create=True); before=(work/'PAGE-QUEUE.md').read_bytes()
            with self.assertRaisesRegex(ValueError,'v1'): md.commit(src,proposal,'absent','test')
            self.assertEqual((work/'PAGE-QUEUE.md').read_bytes(),before)
            (work/md.MARKER).write_text('broken')
            with self.assertRaises(ValueError): load(work/'manifest.json')
            with self.assertRaises(ValueError): save(work/'manifest.json',legacy)
            self.assertEqual((work/'PAGE-QUEUE.md').read_bytes(),before)

    def test_uncertain_first_commit_after_marker(self):
        with tempfile.TemporaryDirectory(dir='.') as tmp:
            src=fixture(Path(tmp).absolute()); proposal=src/'.work/p.md'; md.write_template(src,proposal)
            with patch('tools.queue_md.os.replace',side_effect=OSError('injected')):
                with self.assertRaises(md.CommitUncertain): md.commit(src,proposal,'absent','test')
            self.assertTrue((src/'.work'/md.MARKER).exists())
            with self.assertRaisesRegex(ValueError,'Незавершённая'): md.commit(src,proposal,'absent','test')

    def test_recover_interrupted_commit_from_selected_history(self):
        with tempfile.TemporaryDirectory(dir='.') as tmp:
            src=fixture(Path(tmp).absolute()); proposal=src/'.work/p.md'; md.write_template(src,proposal)
            with patch('tools.queue_md.os.replace',side_effect=OSError('injected')):
                with self.assertRaises(md.CommitUncertain): md.commit(src,proposal,'absent','test')
            work=src/'.work'; history=next((work/'queue-history').iterdir())
            with self.assertRaises(ValueError): md.recover_commit(src,history,'absent',False)
            result=md.recover_commit(src,history,'absent',True)
            self.assertEqual(result['status'],'recovered')
            self.assertEqual(md.recover_commit(src,history,result['sha256'],True)['status'],'already_complete')
            (work/'PAGE-QUEUE.md').write_text('external change')
            with self.assertRaises(ValueError): md.recover_commit(src,history,result['sha256'],True)
            self.assertEqual((work/'PAGE-QUEUE.md').read_text(),'external change')

    def test_direct_editor_stale_source_and_symlink_are_blocked(self):
        with tempfile.TemporaryDirectory(dir='.') as tmp:
            src=fixture(Path(tmp).absolute()); data=md.parse(md.template(src)); data['pages']=[page()]
            for m in data['meta']:
                if m['key']=='discovery_status': m['value']='confirmed'
                if m['key']=='confirmation_reason': m['value']='reviewed'
            proposal=src/'.work/p.md'; proposal.write_text(md.render(data)); (src/'index.html').write_text('changed')
            with self.assertRaisesRegex(ValueError,'snapshot'): md.commit(src,proposal,'absent','test')
            link=src/'.work/link'; link.symlink_to(proposal)
            with self.assertRaises(ValueError): md.validate_file(src,link)

if __name__ == '__main__': unittest.main()
