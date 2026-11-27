"""Diagnostic browser matrix for the committed Markdown queue.

Results are not trusted evidence: external endpoint provenance, assertions and
manual inspection have not been proven by this command.
"""
from __future__ import annotations
import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from . import queue_md as md
from .audit_runner import run
from .browser import loopback_url
from .coverage import diagnostic
from .lifecycle import serve_site
from .screen_audit import VIEWPORTS, load_scenarios
from .snapshot import take_snapshot
from .tool_identity import current as tool_identity


class AuditUncertain(OSError):
    """An audit artifact directory or some of its files may exist."""


def audit(source, site, reference_url, output=None):
    source=Path(source).absolute(); work=source/'.work'; site=Path(site).absolute()
    url=urlsplit(reference_url)
    if not loopback_url(reference_url) or url.path not in ('', '/') or url.query or url.fragment:
        raise ValueError('Нужен базовый локальный URL эталона с портом без пути и query')
    started=datetime.now(timezone.utc).isoformat()
    toolchain,toolchain_hash=tool_identity()
    config={'schema':'browser-matrix-config-v1','reference_url':reference_url,
            'reference_profile':'external-unverified','candidate_profile':'managed-static-unverified',
            'viewport_sizes':[list(size) for size in VIEWPORTS], 'pixel_threshold':0.001,
            'channel_tolerance':12, 'locale':'ru-RU','device_scale_factor':1,
            'reduced_motion':'reduce','service_workers':'block','font_override':None}
    config_hash=hashlib.sha256(json.dumps(config,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode('utf8')).hexdigest()
    baseline=diagnostic(source,site)
    queue=md._safe_read(md._path(work,work/'PAGE-QUEUE.md'))
    if md.sha(queue)!=baseline['queue_sha256']: raise ValueError('Очередь изменилась перед аудитом')
    committed=md._recorded_requirements(work,queue)
    parsed=md.parse(queue.decode('utf8'))
    if len(parsed['pages']) > 100 or len(parsed['aliases']) + len(parsed['pages']) > 100 or len(parsed['states']) > 300: raise ValueError('Слишком большая матрица для одного запуска')
    root=md._path(work,work/'audits-md',existing=False)
    out=md._path(work,output or root/uuid.uuid4().hex,existing=False)
    if out.parent!=root or out.exists() or out.name.startswith('.'): raise ValueError('Нужен новый каталог непосредственно в .work/audits-md')
    try:
        root.mkdir(exist_ok=True)
        out.mkdir(mode=0o700)
        records=[]; warnings=list(baseline['warnings']); issues=list(baseline['issues'])
        matrix=baseline['coverage']['entries']
        by_key={(e['page_id'],e['route'],tuple(e['viewport']),e['state']):e for e in matrix}
        if len(by_key)!=len(matrix): raise ValueError('Повторные записи матрицы')
        observed=set()
        standard={f'{w}x{h}':w for w,h in VIEWPORTS}
        with serve_site(site) as candidate:
            for page in parsed['pages']:
                if page['confirmation']!='confirmed': continue
                selected=[]
                for state in (x for x in parsed['states'] if x['page_id']==page['id']):
                    if not state['scenario']:
                        continue
                    try:
                        path=md._path(work,work/state['scenario'])
                        scenarios=load_scenarios(path)
                        match=[s for s in scenarios if s['name']==state['state_id']]
                        sizes=state['viewports'].split(',')
                        if len(match)!=1 or any(size not in standard for size in sizes):
                            raise ValueError('Состояние отсутствует в сценарии или viewport не поддерживается')
                        item=dict(match[0]); widths=[standard[size] for size in sizes]
                        if 'viewports' in item and set(item['viewports'])!=set(widths):
                            raise ValueError('Viewport сценария отличается от очереди')
                        item['viewports']=widths
                        selected.append(item)
                    except (ValueError,OSError,UnicodeError) as exc:
                        warnings.append(f"{page['id']}/{state['state_id']}: {exc}")
                if len(selected)>30: raise ValueError('Не более 30 сценариев на страницу')
                routes=[page['reference_route']]+[a['reference_route'] for a in parsed['aliases'] if a['page_id']==page['id']]
                for index,route in enumerate(routes):
                    folder=out/(page['id']+'-'+str(index))
                    result=run(source,site,folder,selected if index==0 else [],'/',0.001,None,False,
                               reference_url,candidate,12,route,'/'+page['output'],work)
                    if (not isinstance(result,dict) or result.get('status') not in ('INCOMPLETE','FAIL','BLOCKED') or
                            any(not isinstance(result.get(k,[]),list) or any(not isinstance(x,str) for x in result.get(k,[])) for k in ('issues','warnings')) or
                            not isinstance(result.get('viewports',[]),list)):
                        raise ValueError('Неизвестный формат результата дочернего браузерного запуска')
                    records.append({'page_id':page['id'],'route':route,'artifact_directory':str(folder),'result':result})
                    issues.extend(result.get('issues',[])); warnings.extend(result.get('warnings',[]))
                    for viewport in result.get('viewports',[]):
                        if (not isinstance(viewport,dict) or type(viewport.get('width')) is not int or
                                type(viewport.get('height')) is not int or not isinstance(viewport.get('states'),list)):
                            raise ValueError('Некорректный viewport дочернего запуска')
                        for state in viewport['states']:
                            if (not isinstance(state,dict) or not isinstance(state.get('name'),str) or
                                    state.get('status') not in ('OK','REVIEW','FAIL','BLOCKED')):
                                raise ValueError('Неизвестный статус состояния дочернего запуска')
                            key=(page['id'],route,(viewport['width'],viewport['height']),state['name'])
                            if key not in by_key or key in observed: raise ValueError('Лишняя или повторная запись состояния дочернего запуска')
                            observed.add(key); entry=by_key[key]; executed=state['status']!='BLOCKED'
                            entry['execution']='executed' if executed else 'blocked'
                            entry['outcome']='fail' if state['status']=='FAIL' else 'review' if executed else 'unknown'
                            entry['reason']='Диагностика: происхождение эталона и полные assertions не подтверждены' if executed else state.get('issue','Не выполнено')
                            entry['artifacts']=[str(folder)]
        scenario_hashes={s['scenario']:md._scenario_hash(work,s['scenario']) for s in parsed['states'] if s['scenario']}
        now=md.compile_queue(queue.decode('utf8'),source)
        if (md._safe_read(work/'PAGE-QUEUE.md')!=queue or committed!=md._recorded_requirements(work,queue)
                or take_snapshot(site,'delivery')['digest']!=baseline['delivery_snapshot']
                or now['requirements_hash']!=baseline['requirements_hash'] or now['source_snapshot_current']!=baseline['source_snapshot']
                or any(md._scenario_hash(work,path)!=digest for path,digest in scenario_hashes.items())
                or tool_identity()[1]!=toolchain_hash):
            raise ValueError('Источник, очередь, сценарии или candidate изменились во время аудита; отчёты не являются evidence')
        executed=sum(e['execution']=='executed' for e in matrix)
        # Preserve an overall child failure even if it produced no matching
        # viewport row. A known failure must not be hidden by another blocker.
        failed=baseline['status']=='FAIL' or any(r['result']['status']=='FAIL' for r in records) or any(e['outcome']=='fail' for e in matrix)
        blocked=bool(issues) or any(r['result']['status']=='BLOCKED' for r in records) or any(e['execution']=='blocked' for e in matrix)
        status='FAIL' if failed else 'BLOCKED' if blocked else 'INCOMPLETE'
        result={'status':status, 'schema_version':1, 'kind':'diagnostic-browser-matrix',
                'started_at':started,'finished_at':datetime.now(timezone.utc).isoformat(),
                'config':config,'config_sha256':config_hash,'toolchain':toolchain,'toolchain_sha256':toolchain_hash,
                'browser_versions':sorted({r['result']['browser_version'] for r in records if r['result'].get('browser_version')}),
                'scenario_sha256':scenario_hashes,
                'operation':'applied','issues':list(dict.fromkeys(issues)), 'warnings':list(dict.fromkeys(warnings)),
                'source_snapshot':baseline['source_snapshot'],'queue_sha256':baseline['queue_sha256'],
                'requirements_hash':baseline['requirements_hash'],'delivery_snapshot':baseline['delivery_snapshot'],
                'reference_provenance':'external-unverified','eligible':False,
                'coverage':{'planned':len(matrix),'executed':executed,'entries':matrix},
                'runs':records, 'artifact_directory':str(out),
                'next':'Результат диагностический; проверка эталона, assertions и ручное исследование обязательны.'}
        encoded=(json.dumps(result,ensure_ascii=False,indent=2)+'\n').encode('utf8')
        md._write_new(out/'summary.json',encoded); md._sync_dir(out); md._sync_dir(root)
        return result
    except Exception as exc:
        raise AuditUncertain(f'Артефакты браузерного аудита могли быть записаны частично: {out}; проверьте перед повтором: {exc}') from exc
