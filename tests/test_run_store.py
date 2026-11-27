import contextlib
import hashlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools import queue_md as md, run_store, readiness, manual_evidence, publication, delivery
from tools.audit_markdown import audit
from tools.cli import main


def setup(base):
    source=base/'source'; source.mkdir(); (source/'index.html').write_text('source')
    work=source/'.work'; work.mkdir(); site=work/'staging'/'candidate'; site.mkdir(parents=True)
    (site/'index.html').write_text('<!doctype html><html lang="en"><head><title>Test</title><meta name="viewport" content="width=device-width"></head><body><main><h1>Hello</h1></main></body></html>')
    data=md.parse(md.template(source))
    data['pages']=[dict(zip(md.TABLES['pages'],['home','Home','/','index.html','confirmed','true','built','reviewed','']))]
    data['states']=[dict(zip(md.TABLES['states'],['home','menu','true','390x844','scenario.json']))]
    (work/'scenario.json').write_text(json.dumps([{'name':'menu','reference':[],'candidate':[]}]))
    proposal=work/'proposal.md'; proposal.write_text(md.render(data)); md.commit(source,proposal,'absent','start')
    def fake(*args):
        from PIL import Image
        out=args[2]; out.mkdir(parents=True); (out/'screen.png').write_bytes(b'synthetic screenshot')
        buffer=io.BytesIO(); Image.new('RGB',(390,844),'white').save(buffer,format='PNG'); png=buffer.getvalue()
        states=[]
        for name in ('initial','menu'):
            folder=out/'390x844'/name; folder.mkdir(parents=True)
            screen={'index':1,'reference_size':[390,844],'candidate_size':[390,844],'canvas_size':[390,844]}
            for key in ('reference','candidate','diff','overlay','heatmap'):
                file=folder/f'001-{key}.png'; file.write_bytes(png)
                screen[key]=str(file.relative_to(out))
            states.append({'name':name,'status':'OK','screens':[screen]})
        return {'status':'INCOMPLETE','issues':[],'warnings':[], 'browser_version':'131',
                'viewports':[{'width':390,'height':844,'states':states}]}
    with patch('tools.audit_markdown.run',side_effect=fake): result=audit(source,site,'http://127.0.0.1:8123')
    directory=Path(result['artifact_directory']); raw=(directory/'summary.json').read_bytes()
    return source,site,work,directory,hashlib.sha256(raw).hexdigest(),result


class RunStoreTests(unittest.TestCase):
    def test_seal_and_inspect_bind_artifacts_configuration_and_scenarios(self):
        with tempfile.TemporaryDirectory(dir='.') as t:
            source,site,work,directory,summary_hash,result=setup(Path(t).absolute())
            record=run_store.seal(source,site,directory,summary_hash)
            self.assertEqual(record['operation'],'applied')
            self.assertFalse(record['record']['authenticated']); self.assertFalse(record['record']['publication_eligible'])
            self.assertEqual(record['record']['browser_versions'],['131'])
            self.assertEqual(record['record']['config_sha256'],result['config_sha256'])
            self.assertEqual(record['record']['scenario_sha256']['scenario.json'],hashlib.sha256((work/'scenario.json').read_bytes()).hexdigest())
            state=run_store.inspect(source,site,record['path'],record['sha256'])
            self.assertEqual(state['freshness'],'current'); self.assertFalse(state['publication_eligible'])
            (directory/'home-0'/'screen.png').write_bytes(b'tampered')
            state=run_store.inspect(source,site,record['path'],record['sha256'])
            self.assertEqual(state['freshness'],'stale'); self.assertIn('artifacts',state['changed'])

    def test_input_and_scenario_drift_are_visible(self):
        with tempfile.TemporaryDirectory(dir='.') as t:
            source,site,work,directory,h,_=setup(Path(t).absolute())
            rec=run_store.seal(source,site,directory,h)
            (work/'scenario.json').write_text('[]')
            (site/'index.html').write_text('changed')
            state=run_store.inspect(source,site,rec['path'],rec['sha256'])
            self.assertEqual(state['freshness'],'stale')
            self.assertIn('requirements_hash',state['changed']); self.assertIn('delivery_snapshot',state['changed'])
            self.assertIn('scenarios',state['changed'])
            with self.assertRaisesRegex(ValueError,'устарел'): run_store.seal(source,site,directory,h)

    def test_toolchain_change_invalidates_record_and_blocks_new_seal(self):
        with tempfile.TemporaryDirectory(dir='.') as t:
            source,site,work,directory,h,_=setup(Path(t).absolute()); rec=run_store.seal(source,site,directory,h)
            with patch('tools.run_store.tool_identity',return_value=({},'0'*64)):
                state=run_store.inspect(source,site,rec['path'],rec['sha256'])
                self.assertEqual(state['freshness'],'stale'); self.assertIn('toolchain',state['changed'])
                with self.assertRaisesRegex(ValueError,'Инструментарий изменился'): run_store.seal(source,site,directory,h)

    def test_summary_and_record_tampering_fails_closed(self):
        with tempfile.TemporaryDirectory(dir='.') as t:
            source,site,work,directory,h,_=setup(Path(t).absolute()); rec=run_store.seal(source,site,directory,h)
            (directory/'summary.json').write_text('{}')
            state=run_store.inspect(source,site,rec['path'],rec['sha256'])
            self.assertEqual(state['freshness'],'stale'); self.assertIn('artifacts',state['changed'])
            with self.assertRaises(ValueError): run_store.seal(source,site,directory,h)
            Path(rec['path']).write_text('{}')
            with self.assertRaisesRegex(ValueError,'изменена'): run_store.inspect(source,site,rec['path'],rec['sha256'])

    def test_malformed_counts_or_overall_pass_are_rejected(self):
        with tempfile.TemporaryDirectory(dir='.') as t:
            source,site,work,directory,h,_=setup(Path(t).absolute()); summary=directory/'summary.json'; data=json.loads(summary.read_text())
            data['coverage']['executed']=999; summary.write_text(json.dumps(data)); h=hashlib.sha256(summary.read_bytes()).hexdigest()
            with self.assertRaisesRegex(ValueError,'статистика'): run_store.seal(source,site,directory,h)
            data['coverage']['executed']=sum(e['execution']=='executed' for e in data['coverage']['entries'])
            data['status']='PASS'; summary.write_text(json.dumps(data)); h=hashlib.sha256(summary.read_bytes()).hexdigest()
            with self.assertRaisesRegex(ValueError,'статистика'): run_store.seal(source,site,directory,h)

    def test_contradictory_child_or_matrix_status_cannot_be_sealed(self):
        with tempfile.TemporaryDirectory(dir='.') as t:
            source,site,work,directory,h,_=setup(Path(t).absolute()); summary=directory/'summary.json'
            original=json.loads(summary.read_text())
            for case in ('child-fail','child-blocked','row-fail','row-blocked','issues','invalid-outcome'):
                with self.subTest(case=case):
                    data=json.loads(json.dumps(original)); data['status']='INCOMPLETE'; data['issues']=[]
                    if case=='child-fail': data['runs'][0]['result']['status']='FAIL'
                    elif case=='child-blocked': data['runs'][0]['result']['status']='BLOCKED'
                    elif case=='row-fail': data['coverage']['entries'][0]['outcome']='fail'
                    elif case=='row-blocked':
                        data['coverage']['entries'][0]['execution']='blocked'
                        data['coverage']['executed']=sum(row['execution']=='executed' for row in data['coverage']['entries'])
                    elif case=='issues': data['issues']=['unresolved error']
                    else: data['coverage']['entries'][0]['outcome']='unexpected'
                    summary.write_text(json.dumps(data)); digest=hashlib.sha256(summary.read_bytes()).hexdigest()
                    with self.assertRaises(ValueError): run_store.seal(source,site,directory,digest)

    def test_seal_rejects_incomplete_or_inconsistent_matrix_and_scenario_list(self):
        with tempfile.TemporaryDirectory(dir='.') as t:
            source,site,work,directory,_,_=setup(Path(t).absolute()); summary=directory/'summary.json'
            original=json.loads(summary.read_text())
            for case in ('missing','duplicate','extra','required','not-run-fail','blocked-review','missing-scenario','extra-scenario','bad-time','bad-versions'):
                with self.subTest(case=case):
                    data=json.loads(json.dumps(original)); rows=data['coverage']['entries']
                    if case=='missing': rows.pop()
                    elif case=='duplicate': rows.append(dict(rows[0]))
                    elif case=='extra': rows[0]['state']='invented'
                    elif case=='required': rows[0]['required']=not rows[0]['required']
                    elif case=='not-run-fail': rows[0]['execution']='not_run'; rows[0]['outcome']='fail'; data['status']='FAIL'
                    elif case=='blocked-review': rows[0]['execution']='blocked'; rows[0]['outcome']='review'; data['status']='BLOCKED'
                    elif case=='missing-scenario': data['scenario_sha256']={}
                    elif case=='extra-scenario': data['scenario_sha256']['invented.json']=None
                    elif case=='bad-time': data['finished_at']='invalid'
                    elif case=='bad-versions': data['browser_versions']=['invented']
                    data['coverage']['planned']=len(rows); data['coverage']['executed']=sum(row['execution']=='executed' for row in rows)
                    summary.write_text(json.dumps(data)); digest=hashlib.sha256(summary.read_bytes()).hexdigest()
                    out=work/'run-records'/'no.json'
                    with self.assertRaises(ValueError): run_store.seal(source,site,directory,digest,out)
                    self.assertFalse(out.exists())

    def test_record_metadata_disagreement_is_not_current_even_with_new_record_hash(self):
        with tempfile.TemporaryDirectory(dir='.') as t:
            source,site,work,directory,h,_=setup(Path(t).absolute()); sealed=run_store.seal(source,site,directory,h)
            path=Path(sealed['path']); original=json.loads(path.read_text())
            for key,value in (('artifact_files',999),('coverage_planned',999),('coverage_executed',999),
                              ('reported_status','INCOMPLETE'),('started_at','changed'),('finished_at','changed'),
                              ('browser_versions',['fake'])):
                with self.subTest(key=key):
                    record={**original,key:value}; raw=json.dumps(record).encode(); path.write_bytes(raw)
                    state=run_store.inspect(source,site,path,hashlib.sha256(raw).hexdigest())
                    self.assertEqual(state['freshness'],'stale'); self.assertIn('record_mismatch',state['changed'])
            record={**original,'verified_identity':True}; raw=json.dumps(record).encode(); path.write_bytes(raw)
            with self.assertRaises(ValueError): run_store.inspect(source,site,path,hashlib.sha256(raw).hexdigest())

    def test_inspect_does_not_accept_incomplete_rehashed_matrix_as_current(self):
        from tools.snapshot import take_snapshot
        with tempfile.TemporaryDirectory(dir='.') as t:
            source,site,work,directory,h,_=setup(Path(t).absolute()); sealed=run_store.seal(source,site,directory,h)
            summary_path=directory/'summary.json'; data=json.loads(summary_path.read_text()); rows=data['coverage']['entries']; rows.pop()
            data['coverage']['planned']=len(rows); data['coverage']['executed']=sum(row['execution']=='executed' for row in rows)
            raw=json.dumps(data).encode(); summary_path.write_bytes(raw)
            record=sealed['record']; record['summary_sha256']=hashlib.sha256(raw).hexdigest()
            record['artifacts_snapshot']=take_snapshot(directory,'delivery')['digest']
            record['coverage_sha256']=hashlib.sha256(run_store._canonical(data['coverage'])).hexdigest()
            record['coverage_planned']=data['coverage']['planned']; record['coverage_executed']=data['coverage']['executed']
            path=Path(sealed['path']); encoded=json.dumps(record).encode(); path.write_bytes(encoded)
            state=run_store.inspect(source,site,path,hashlib.sha256(encoded).hexdigest())
            self.assertEqual(state['freshness'],'stale'); self.assertIn('матрица',state['artifact_error'].lower())

    def test_matrix_child_and_artifact_paths_must_agree_before_seal(self):
        with tempfile.TemporaryDirectory(dir='.') as t:
            source,site,work,directory,_,_=setup(Path(t).absolute()); summary=directory/'summary.json'
            original=json.loads(summary.read_text())
            for case in ('missing-child','extra-child','duplicate-child','wrong-status','wrong-path','outside-path','not-run-artifacts','pass','missing-directory'):
                with self.subTest(case=case):
                    data=json.loads(json.dumps(original)); rows=data['coverage']['entries']; child=data['runs'][0]
                    if case=='missing-child': child['result']['viewports'][0]['states'].pop()
                    elif case=='extra-child': child['result']['viewports'][0]['states'].append({'name':'invented','status':'OK'})
                    elif case=='duplicate-child': data['runs'].append(json.loads(json.dumps(child)))
                    elif case=='wrong-status': child['result']['viewports'][0]['states'][0]['status']='BLOCKED'
                    elif case=='wrong-path': rows[0]['artifacts']=[str(directory/'different')]
                    elif case=='outside-path': child['artifact_directory']=str(work/'outside'); rows[0]['artifacts']=[str(work/'outside')]
                    elif case=='not-run-artifacts': next(row for row in rows if row['execution']=='not_run')['artifacts']=[str(directory/'home-0')]
                    elif case=='pass': rows[0]['outcome']='pass'
                    else:
                        missing=str(directory/'not-created'); child['artifact_directory']=missing
                        for row in rows:
                            if row['artifacts']: row['artifacts']=[missing]
                    raw=json.dumps(data).encode(); summary.write_bytes(raw)
                    with self.assertRaises(ValueError): run_store.seal(source,site,directory,hashlib.sha256(raw).hexdigest())
            summary.write_text(json.dumps(original)); digest=hashlib.sha256(summary.read_bytes()).hexdigest()
            self.assertEqual(run_store.seal(source,site,directory,digest)['operation'],'applied')

    def test_executed_state_requires_named_nonempty_screenshot_artifacts(self):
        for case in ('no-screens','wrong-index','wrong-name','outside','missing-file','empty-file','invented-fullpage'):
            with self.subTest(case=case), tempfile.TemporaryDirectory(dir='.') as t:
                source,site,work,directory,_,_=setup(Path(t).absolute()); summary=directory/'summary.json'
                data=json.loads(summary.read_text()); state=data['runs'][0]['result']['viewports'][0]['states'][0]
                screen=state['screens'][0]; file=directory/'home-0'/screen['reference']
                if case=='no-screens': state['screens']=[]
                elif case=='wrong-index': screen['index']=2
                elif case=='wrong-name': screen['reference']=screen['candidate']
                elif case=='outside': screen['reference']='../../outside.png'
                elif case=='missing-file': file.unlink()
                elif case=='empty-file': file.write_bytes(b'')
                else: state['fullpage']={key:'missing' for key in ('reference','candidate','diff','overlay','heatmap')}
                raw=json.dumps(data).encode(); summary.write_bytes(raw)
                with self.assertRaises(ValueError): run_store.seal(source,site,directory,hashlib.sha256(raw).hexdigest())
                self.assertFalse((work/'run-records').exists())

    def test_rehashed_png_corruption_and_dimension_mismatch_are_rejected(self):
        from tools.snapshot import take_snapshot
        from PIL import Image
        for case in ('corrupt','wrong-size','lying-metadata'):
            with self.subTest(case=case), tempfile.TemporaryDirectory(dir='.') as t:
                source,site,work,directory,h,_=setup(Path(t).absolute()); sealed=run_store.seal(source,site,directory,h)
                image=directory/'home-0/390x844/initial/001-reference.png'
                if case=='corrupt':
                    raw=bytearray(image.read_bytes()); raw[-1]^=1; image.write_bytes(raw)
                else:
                    output=io.BytesIO(); Image.new('RGB',(2,3)).save(output,format='PNG'); image.write_bytes(output.getvalue())
                if case=='lying-metadata':
                    summary=directory/'summary.json'; data=json.loads(summary.read_text())
                    data['runs'][0]['result']['viewports'][0]['states'][0]['screens'][0]['reference_size']=[2,3]
                    encoded=json.dumps(data).encode(); summary.write_bytes(encoded)
                    sealed['record']['summary_sha256']=hashlib.sha256(encoded).hexdigest()
                snap=take_snapshot(directory,'delivery'); rec=sealed['record']
                rec['artifacts_snapshot']=snap['digest']; rec['artifact_files']=sum(e['type']=='file' for e in snap['entries'])
                path=Path(sealed['path']); encoded=json.dumps(rec).encode(); path.write_bytes(encoded)
                state=run_store.inspect(source,site,path,hashlib.sha256(encoded).hexdigest())
                self.assertEqual(state['freshness'],'stale'); self.assertIn('artifacts',state['changed'])

    def test_rehashed_record_cannot_hide_a_missing_screenshot(self):
        from tools.snapshot import take_snapshot
        with tempfile.TemporaryDirectory(dir='.') as t:
            source,site,work,directory,h,_=setup(Path(t).absolute()); sealed=run_store.seal(source,site,directory,h)
            image=directory/'home-0/390x844/initial/001-reference.png'; image.unlink()
            snapshot=take_snapshot(directory,'delivery'); record=sealed['record']
            record['artifacts_snapshot']=snapshot['digest']
            record['artifact_files']=sum(e['type']=='file' for e in snapshot['entries'])
            path=Path(sealed['path']); encoded=json.dumps(record).encode(); path.write_bytes(encoded)
            state=run_store.inspect(source,site,path,hashlib.sha256(encoded).hexdigest())
            self.assertEqual(state['freshness'],'stale'); self.assertIn('artifacts',state['changed'])
            self.assertIn('снимок',state['artifact_error'].lower())

    def test_rehashed_summary_cannot_hide_child_observation_mismatch(self):
        from tools.snapshot import take_snapshot
        with tempfile.TemporaryDirectory(dir='.') as t:
            source,site,work,directory,h,_=setup(Path(t).absolute()); sealed=run_store.seal(source,site,directory,h)
            summary=directory/'summary.json'; data=json.loads(summary.read_text())
            data['runs'][0]['result']['viewports'][0]['states'].pop()
            raw=json.dumps(data).encode(); summary.write_bytes(raw)
            record=sealed['record']; record['summary_sha256']=hashlib.sha256(raw).hexdigest()
            record['artifacts_snapshot']=take_snapshot(directory,'delivery')['digest']
            path=Path(sealed['path']); encoded=json.dumps(record).encode(); path.write_bytes(encoded)
            state=run_store.inspect(source,site,path,hashlib.sha256(encoded).hexdigest())
            self.assertEqual(state['freshness'],'stale'); self.assertIn('artifacts',state['changed'])
            self.assertIn('дочерн',state['artifact_error'].lower())

    def test_forged_trust_or_config_are_rejected(self):
        with tempfile.TemporaryDirectory(dir='.') as t:
            source,site,work,directory,h,_=setup(Path(t).absolute()); summary=directory/'summary.json'
            data=json.loads(summary.read_text()); data['eligible']=True
            summary.write_text(json.dumps(data)); new_hash=hashlib.sha256(summary.read_bytes()).hexdigest()
            with self.assertRaisesRegex(ValueError,'provenance'): run_store.seal(source,site,directory,new_hash)
            data['eligible']=False; data['config']['locale']='en-US'; summary.write_text(json.dumps(data))
            new_hash=hashlib.sha256(summary.read_bytes()).hexdigest()
            with self.assertRaisesRegex(ValueError,'Конфигурация'): run_store.seal(source,site,directory,new_hash)

    def test_cli_and_unique_output(self):
        with tempfile.TemporaryDirectory(dir='.') as t:
            source,site,work,directory,h,_=setup(Path(t).absolute()); out=work/'run-records'/'one.json'
            buf=io.StringIO()
            with contextlib.redirect_stdout(buf):
                code=main(['run-seal','--source',str(source),'--site',str(site),'--audit',str(directory),'--summary-sha256',h,'--output',str(out),'--json'])
            data=json.loads(buf.getvalue()); self.assertEqual(code,2); self.assertEqual(data['operation'],'applied')
            digest=data['run_record']['sha256']; buf=io.StringIO()
            with contextlib.redirect_stdout(buf):
                code=main(['run-inspect','--source',str(source),'--site',str(site),'--file',str(out),'--sha256',digest,'--json'])
            self.assertEqual(code,2); self.assertEqual(json.loads(buf.getvalue())['run_record']['freshness'],'current')
            with self.assertRaises(ValueError): run_store.seal(source,site,directory,h,out)

    def test_invalid_output_does_not_create_record_root_and_mkdir_failure_is_uncertain(self):
        with tempfile.TemporaryDirectory(dir='.') as t:
            source,site,work,directory,h,_=setup(Path(t).absolute()); root=work/'run-records'
            with self.assertRaises(ValueError): run_store.seal(source,site,directory,h,work/'wrong.json')
            self.assertFalse(root.exists())
            original=Path.mkdir
            def fail_after(path,*args,**kwargs):
                result=original(path,*args,**kwargs)
                if path==root: raise OSError('synthetic failure after mkdir')
                return result
            output=io.StringIO()
            with patch.object(Path,'mkdir',autospec=True,side_effect=fail_after),contextlib.redirect_stdout(output):
                code=main(['run-seal','--source',str(source),'--site',str(site),'--audit',str(directory),'--summary-sha256',h,'--json'])
            result=json.loads(output.getvalue()); self.assertEqual(code,4); self.assertEqual(result['operation'],'unknown')
            self.assertTrue(root.is_dir()); self.assertEqual(list(root.iterdir()),[])

    def test_readiness_combines_claims_without_promoting_them_to_pass(self):
        with tempfile.TemporaryDirectory(dir='.') as t:
            source,site,work,directory,h,_=setup(Path(t).absolute())
            rec=run_store.seal(source,site,directory,h)
            claim=manual_evidence.create(source,site,work/'manual-attestations'/'manual.json','reviewer','home','inspected','pass','local fixture only')
            state=readiness.evaluate(source,site,rec['path'],rec['sha256'],claim['path'],claim['sha256'])
            self.assertFalse(state['eligible']); self.assertEqual(state['manual']['freshness'],'current')
            self.assertEqual(state['run']['freshness'],'current'); self.assertEqual(state['coverage']['required'],4)
            self.assertEqual(state['coverage']['required_unconfirmed'],4)
            self.assertTrue(all(row['outcome']!='pass' for row in state['coverage']['entries']))
            self.assertTrue(any('происхождени' in b.lower() for b in state['blockers']))
            (directory/'home-0'/'screen.png').write_bytes(b'changed')
            state=readiness.evaluate(source,site,rec['path'],rec['sha256'])
            self.assertEqual(state['run']['freshness'],'stale')
            self.assertTrue(any('устарела' in b for b in state['blockers']))
            self.assertTrue(all(row['execution']=='not_run' for row in state['coverage']['entries']))

    def test_forged_pass_and_optional_bits_do_not_bypass_requirements(self):
        with tempfile.TemporaryDirectory(dir='.') as t:
            source,site,work,directory,h,_=setup(Path(t).absolute()); summary=directory/'summary.json'
            data=json.loads(summary.read_text())
            for row in data['coverage']['entries']:
                row['execution']='executed'; row['outcome']='pass'
            data['coverage']['executed']=len(data['coverage']['entries'])
            summary.write_text(json.dumps(data)); h=hashlib.sha256(summary.read_bytes()).hexdigest()
            with self.assertRaisesRegex(ValueError,'Матрица'): run_store.seal(source,site,directory,h)
            # Required-bit inconsistency is rejected independently of observations.
            data=json.loads((directory/'summary.json').read_text())
            data['coverage']['entries'][0]['required']=False
            summary.write_text(json.dumps(data)); h=hashlib.sha256(summary.read_bytes()).hexdigest()
            with self.assertRaisesRegex(ValueError,'Обязательность'): run_store.seal(source,site,directory,h)

    def test_readiness_without_claims_and_cli(self):
        with tempfile.TemporaryDirectory(dir='.') as t:
            source,site,work,directory,h,_=setup(Path(t).absolute()); out=io.StringIO()
            with contextlib.redirect_stdout(out): code=main(['readiness','--source',str(source),'--site',str(site),'--json'])
            state=json.loads(out.getvalue()); self.assertEqual(code,1); self.assertEqual(state['status'],'FAIL'); self.assertFalse(state['eligible'])
            self.assertTrue(any('Нет зафиксированного' in b for b in state['blockers']))
            self.assertTrue(any('CMS-заготовки' in b for b in state['blockers']))
            with self.assertRaises(ValueError): readiness.evaluate(source,site,'record',None)

    def test_publication_plan_binds_current_run_but_keeps_apply_closed(self):
        old=os.getcwd()
        with tempfile.TemporaryDirectory(dir='.') as t:
            root=Path(t).absolute()
            try:
                os.chdir(root)
                source,site,work,directory,h,_=setup(root)
                selected=work/'selection.json'; selected.write_text(json.dumps(['index.html']))
                copied=delivery.materialize(source,site,selected,work/'deliveries'/'one')
                rec=run_store.seal(source,work/'deliveries'/'one',directory,h)
                plan=publication.plan(source,copied['record'],root/'vanilla',rec['path'],rec['sha256'])
                self.assertFalse(plan['apply_allowed']); self.assertEqual(plan['run']['freshness'],'current')
                self.assertEqual(plan['readiness_inputs']['run_sha256'],rec['sha256'])
                self.assertEqual(plan['coverage']['required_unconfirmed'],4)
                report=work/'plan.json'; report.write_text(json.dumps({'plan':plan})); digest=hashlib.sha256(report.read_bytes()).hexdigest()
                (directory/'home-0'/'screen.png').write_bytes(b'changed')
                with self.assertRaisesRegex(ValueError,'устарел'): publication.apply(source,report,digest,True)
                self.assertFalse((root/'vanilla').exists())
            finally: os.chdir(old)

    @unittest.skipUnless(hasattr(os,'symlink'),'symlinks unavailable')
    def test_symlink_artifacts_are_never_followed(self):
        with tempfile.TemporaryDirectory(dir='.') as t:
            source,site,work,directory,h,_=setup(Path(t).absolute())
            (directory/'evil').symlink_to(source/'index.html')
            with self.assertRaises(ValueError): run_store.seal(source,site,directory,h)
            self.assertFalse((work/'run-records').exists())

if __name__=='__main__': unittest.main()
