import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from tools import queue_md as md, readiness
from tools.coverage import diagnostic
from tools.templates import parse_policy, inspect_tokens
from tools.cli import main
from tools.snapshot import take_snapshot


def setup(base):
    source=base/'source'; source.mkdir(); (source/'index.html').write_text('source')
    work=source/'.work'; work.mkdir(); site=work/'staging'/'candidate'; site.mkdir(parents=True); (site/'template').mkdir()
    header='<header><nav><a href="index.html" class="nav">Home</a></nav></header>'
    footer='<footer>Footer</footer>'
    (site/'template'/'header.php').write_text(header); (site/'template'/'footer.php').write_text(footer)
    active=header.replace('class="nav"','class="active nav" aria-current="page"')
    (site/'index.html').write_text('<!doctype html><html lang="en"><head><title>Site</title><meta name="viewport" content="width=device-width"></head><body><!-- HEADER:START -->'+active+'<!-- HEADER:END --><main><h1>Home</h1></main><!-- FOOTER:START -->'+footer+'<!-- FOOTER:END --></body></html>')
    data=md.parse(md.template(source)); data['pages']=[dict(zip(md.TABLES['pages'],['home','Home','/','index.html','confirmed','true','built','reviewed','']))]
    for row in data['meta']:
        if row['key']=='discovery_status': row['value']='confirmed'
        if row['key']=='confirmation_reason': row['value']='reviewed'
    policy={'version':1,'exceptions':[{'output':'index.html','block':'HEADER','href':'/index.html','add_class':'active','aria_current':'page','reason':'Current page navigation'}]}
    return source,work,site,data,policy


class TemplatePolicyTests(unittest.TestCase):
    def test_narrow_exception_and_unapproved_changes(self):
        with tempfile.TemporaryDirectory(dir='.') as t:
            src,work,site,data,policy=setup(Path(t).absolute()); proposal=work/'p.md'
            proposal.write_text(md.render(data)); md.commit(src,proposal,'absent','initial')
            no_policy=diagnostic(src,site); self.assertEqual(no_policy['status'],'FAIL')
            # Changing confirmed requirements requires a review revision.
            for row in data['meta']:
                if row['key']=='discovery_status': row['value']='review_required'
            data['meta'].append({'key':'template_policy','value':'template-policy.json'})
            (work/'template-policy.json').write_text(json.dumps(policy))
            proposal.write_text(md.render(data)); prev=md.sha((work/'PAGE-QUEUE.md').read_bytes())
            transition=md.commit(src,proposal,prev,'review intentional navigation')
            for row in data['meta']:
                if row['key']=='discovery_status': row['value']='confirmed'
            proposal.write_text(md.render(data)); md.commit(src,proposal,transition['sha256'],'confirmed after review')
            result=diagnostic(src,site); self.assertEqual(result['status'],'INCOMPLETE',result['issues'])
            page=site/'index.html'; page.write_text(page.read_text().replace('aria-current="page"','aria-current="page" aria-label="unexpected"'))
            result=diagnostic(src,site); self.assertEqual(result['status'],'FAIL')
            self.assertTrue(any('не соответствует' in x for x in result['issues']))

    def test_multipage_relative_links_with_explicit_per_page_navigation(self):
        with tempfile.TemporaryDirectory(dir='.') as t:
            src,work,site,data,policy=setup(Path(t).absolute()); (site/'nested').mkdir()
            shared='<header><nav><a class="nav" href="index.html">Home</a><a class="nav" href="nested/about.html">About</a></nav></header>'
            (site/'template/header.php').write_text(shared); footer=(site/'template/footer.php').read_text()
            def page(header):
                return '<!doctype html><html lang="en"><head><title>Test</title><meta name="viewport" content="width=device-width"></head><body><!-- HEADER:START -->'+header+'<!-- HEADER:END --><main><h1>Content</h1></main><!-- FOOTER:START -->'+footer+'<!-- FOOTER:END --></body></html>'
            home=shared.replace('class="nav" href="index.html"','class="nav active" aria-current="page" href="index.html"')
            nested=shared.replace('href="index.html"','href="../index.html"').replace('href="nested/about.html"','href="about.html"')
            nested=nested.replace('class="nav" href="about.html"','class="nav active" aria-current="page" href="about.html"')
            (site/'index.html').write_text(page(home)); (site/'nested/about.html').write_text(page(nested))
            data['pages'].append(dict(zip(md.TABLES['pages'],['about','About','/about','nested/about.html','confirmed','true','built','reviewed',''])))
            policy['exceptions'].append({'output':'nested/about.html','block':'HEADER','href':'/nested/about.html','add_class':'active','aria_current':'page','reason':'Current page'})
            (work/'policy.json').write_text(json.dumps(policy)); data['meta'].append({'key':'template_policy','value':'policy.json'})
            proposal=work/'p.md'; proposal.write_text(md.render(data)); md.commit(src,proposal,'absent','initial')
            result=diagnostic(src,site); self.assertEqual(result['status'],'INCOMPLETE',result['issues'])
            (site/'nested/about.html').write_text(page(nested.replace('>About</a>','>Changed</a>')))
            result=diagnostic(src,site); self.assertEqual(result['status'],'FAIL')
            self.assertTrue(any('nested/about.html' in issue and 'не соответствует' in issue for issue in result['issues']))

    def test_v2_explicit_text_and_attribute_changes_with_navigation(self):
        with tempfile.TemporaryDirectory(dir='.') as t:
            src,work,site,data,v1=setup(Path(t).absolute())
            page=site/'index.html'; page.write_text(page.read_text().replace('aria-current="page"','aria-current="page" aria-label="Home page"').replace('<footer>Footer</footer>','<footer>Local footer</footer>'))
            policy={'version':2,'exceptions':v1['exceptions'],'substitutions':[
                {'output':'index.html','block':'HEADER','index':2,
                 'before':['start','a',[['class','nav'],['href','/index.html']]],
                 'after':['start','a',[['aria-label','Home page'],['class','nav'],['href','/index.html']]],'reason':'Accessible name for this page'},
                {'output':'index.html','block':'FOOTER','index':1,'before':['text','Footer'],'after':['text','Local footer'],'reason':'Reviewed local footer'}]}
            (work/'policy.json').write_text(json.dumps(policy)); data['meta'].append({'key':'template_policy','value':'policy.json'})
            proposal=work/'p.md'; proposal.write_text(md.render(data)); md.commit(src,proposal,'absent','initial')
            result=diagnostic(src,site); self.assertEqual(result['status'],'INCOMPLETE',result['issues'])
            self.assertTrue(any('Reviewed local footer' in x for x in result['warnings']))
            page.write_text(page.read_text().replace('Home page','Unexpected'))
            self.assertEqual(diagnostic(src,site)['status'],'FAIL')
            page.write_text(page.read_text().replace('Unexpected','Home page'))
            template=site/'template/footer.php'; template.write_text('<footer>Changed baseline</footer>')
            result=diagnostic(src,site); self.assertEqual(result['status'],'FAIL')
            self.assertTrue(any('Исходный token' in issue for issue in result['issues']))

    def test_v2_policy_rejects_ambiguous_or_overbroad_substitutions(self):
        rule={'output':'index.html','block':'HEADER','index':3,'before':['text','Home'],'after':['text','Start'],'reason':'Reviewed'}
        policy={'version':2,'exceptions':[],'substitutions':[rule]}
        def parse(value): return parse_policy(json.dumps(value).encode(),{'index.html'})
        parse(policy)
        changes=[{'index':True},{'index':-1},{'index':1000001},{'output':'other.html'},
                 {'block':'OTHER'},{'reason':' '},{'before':['text',' Home']},
                 {'after':['text','Home']},{'after':['start','b',[]]},
                 {'before':['end','a'],'after':['end','b']},
                 {'before':['start','a',[]],'after':['start','button',[]]},
                 {'before':['start','a',[['href','/x'],['class','a']]],'after':['start','a',[]]},
                 {'before':['start','a',[['href','/x'],['href','/x']]],'after':['start','a',[]]}]
        for change in changes:
            with self.subTest(change=change),self.assertRaises(ValueError):
                parse({'version':2,'exceptions':[],'substitutions':[{**rule,**change}]})
        with self.assertRaises(ValueError): parse({'version':2,'exceptions':[],'substitutions':[rule,rule]})
        with self.assertRaises(ValueError): parse({'version':2,'exceptions':[],'substitutions':[rule],'unknown':True})
        with self.assertRaises(ValueError): parse_policy(b'{"version":1,"version":1,"exceptions":[]}',{'index.html'})

    def test_token_inspection_is_paginated_read_only_and_can_prepare_policy(self):
        with tempfile.TemporaryDirectory(dir='.') as t:
            src,work,site,data,policy=setup(Path(t).absolute()); before=take_snapshot(site,'delivery')['digest']
            item=inspect_tokens(site,'index.html','HEADER',2,1)
            self.assertEqual(item['site_snapshot'],before); self.assertEqual(item['template']['total'],7)
            self.assertEqual(item['template']['items'],[{'index':2,'token':['start','a',[['class','nav'],['href','/index.html']]],'replaceable':True}])
            self.assertEqual(item['candidate']['items'][0]['token'][2][0],['aria-current','page'])
            self.assertEqual(take_snapshot(site,'delivery')['digest'],before)
            out=io.StringIO()
            with contextlib.redirect_stdout(out):
                code=main(['template-tokens','--site',str(site),'--page','index.html','--block','HEADER','--offset','2','--limit','1','--json'])
            result=json.loads(out.getvalue()); self.assertEqual(code,2); self.assertEqual(result['operation'],'not_applied')
            self.assertEqual(result['template_tokens'],item); self.assertTrue(any('чувствительные' in x for x in result['warnings']))
            for args in (('../index.html','HEADER',0,1),('index.html','HEADER',-1,1),('index.html','HEADER',0,101),('index.html','WRONG',0,1)):
                with self.subTest(args=args),self.assertRaises(ValueError): inspect_tokens(site,*args)
            page=site/'index.html'; page.write_text(page.read_text().replace('HEADER:END','HEADER:WRONG'))
            with self.assertRaisesRegex(ValueError,'маркеры'): inspect_tokens(site,'index.html','HEADER')

    def test_policy_change_invalidates_requirements_and_requires_review(self):
        with tempfile.TemporaryDirectory(dir='.') as t:
            src,work,site,data,policy=setup(Path(t).absolute()); data['meta'].append({'key':'template_policy','value':'policy.json'})
            policy_file=work/'policy.json'; policy_file.write_text(json.dumps(policy))
            proposal=work/'p.md'; proposal.write_text(md.render(data)); committed=md.commit(src,proposal,'absent','initial')
            before=md.compile_queue(proposal.read_text(),src)['requirements_hash']
            policy['exceptions'][0]['reason']='different reason'; policy_file.write_text(json.dumps(policy))
            after=md.compile_queue(proposal.read_text(),src)['requirements_hash']; self.assertNotEqual(before,after)
            state=readiness.evaluate(src,site)
            self.assertTrue(any('не соответствуют' in x for x in state['blockers']))
            with self.assertRaisesRegex(ValueError,'review_required'): md.commit(src,proposal,committed['sha256'],'bypass')

    def test_missing_or_ambiguous_target_is_not_silently_ignored(self):
        with tempfile.TemporaryDirectory(dir='.') as t:
            src,work,site,data,policy=setup(Path(t).absolute()); data['meta'].append({'key':'template_policy','value':'policy.json'})
            policy['exceptions'][0]['href']='/unmatched.html'; (work/'policy.json').write_text(json.dumps(policy))
            proposal=work/'p.md'; proposal.write_text(md.render(data)); md.commit(src,proposal,'absent','initial')
            result=diagnostic(src,site); self.assertEqual(result['status'],'FAIL')
            self.assertTrue(any('ровно одной ссылке' in x for x in result['issues']))

    def test_policy_schema_is_closed_and_paths_are_limited(self):
        with tempfile.TemporaryDirectory(dir='.') as t:
            src,work,site,data,policy=setup(Path(t).absolute()); raw=lambda:json.dumps(policy).encode()
            parse_policy(raw(),{'index.html'})
            for change in ({'add_class':'active other'}, {'href':'//evil.invalid/'}, {'output':'../index.html'}, {'aria_current':'true'}, {'reason':''}):
                modified={**policy['exceptions'][0],**change}; value={'version':1,'exceptions':[modified]}
                with self.subTest(change=change),self.assertRaises(ValueError): parse_policy(json.dumps(value).encode(),{'index.html'})
            policy['exceptions'].append(dict(policy['exceptions'][0]))
            with self.assertRaises(ValueError): parse_policy(raw(),{'index.html'})
            data['meta'].append({'key':'template_policy','value':'missing.json'})
            with self.assertRaises(ValueError): md.compile_queue(md.render(data),src)

if __name__=='__main__': unittest.main()
