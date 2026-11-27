"""Diagnostic coverage matrix and static checks bound to current snapshots.

This is deliberately not a trusted evidence or publication eligibility gate.
"""
from __future__ import annotations
from pathlib import Path
from urllib.parse import urlsplit

from . import queue_md as md
from .lifecycle import _site_root
from .queue import check_manifest
from .screen_audit import VIEWPORTS
from .snapshot import take_snapshot, read_snapshot_prefix
from .core import LFS


def diagnostic(source, site):
    source=Path(source).absolute(); work=source/'.work'; marker=md._path(work,work/md.MARKER)
    if md._safe_read(marker)!=b'queue-md-v1\n': raise ValueError('Marker очереди повреждён')
    md._guard_incomplete_migrations(work)
    path=md._path(work,work/'PAGE-QUEUE.md'); raw=md._safe_read(path)
    compiled=md.compile_queue(raw.decode('utf8'),source)
    # Even diagnostic runs must be associated with a committed queue revision.
    # A directly edited file or damaged HEAD must not silently become evidence.
    recorded_requirements = md._recorded_requirements(work, raw)
    data=md.parse(raw.decode('utf8')); meta={x['key']:x['value'] for x in data['meta']}
    site=_site_root(site); before=take_snapshot(site,'delivery')
    fake={'pages':[{'id':p['id'],'output':p['output'],'confirmation':p['confirmation']} for p in data['pages']],
          'discovery':{'status':meta['discovery_status']}}
    template_policy=None
    if 'template_policy' in meta:
        from .templates import parse_policy
        policy_raw=md._safe_read(md._path(work,work/meta['template_policy']))
        if md.sha(policy_raw)!=compiled['semantic']['template_policy_sha256']:
            raise ValueError('Template policy изменилась во время проверки')
        template_policy=parse_policy(policy_raw,{p['output'] for p in data['pages']})
    from .snapshot_access import SnapshotAccess
    static=check_manifest(site,fake,template_policy,snapshot_access=SnapshotAccess(site,before))
    issues=list(static.get('issues',[])); warnings=list(static.get('warnings',[]))+list(compiled['warnings'])
    entries=[]
    aliases={p['id']:[] for p in data['pages']}
    for alias in data['aliases']: aliases[alias['page_id']].append(alias['reference_route'])
    for page in data['pages']:
        for route in [page['reference_route'],*aliases[page['id']]]:
            for width,height in VIEWPORTS:
                entries.append({'page_id':page['id'],'route':route,'viewport':[width,height], 'state':'initial',
                                'required':page['required']=='true','execution':'not_run','outcome':'unknown',
                                'reason':'Браузерный run и происхождение эталона не подтверждены', 'artifacts':[]})
        if page['required']=='true' and page['confirmation']=='confirmed' and not (site/page['output']).is_file():
            issues.append(f"Нет обязательной страницы {page['output']}")
        for state in [s for s in data['states'] if s['page_id']==page['id']]:
            for size in state['viewports'].split(','):
                width,height=map(int,size.split('x'))
                entries.append({'page_id':page['id'],'route':page['reference_route'],'viewport':[width,height],
                                'state':state['state_id'],'required':state['required']=='true',
                                'execution':'not_run','outcome':'unknown',
                                'reason':'Нет сценария' if not state['scenario'] else 'Сценарий и assertions не выполнены', 'artifacts':[]})
    resources=[]; snapshot_entries={entry['path']:entry for entry in before['entries']}
    for r in data['resources']:
        loc=r['location']; u=urlsplit(loc); required=r['required']=='true'
        if u.scheme:
            observation='external_unverified'
            if required: warnings.append(f"Внешний ресурс {r['id']} не проверен: доступ и права неизвестны")
        else:
            p=site/loc; entry=snapshot_entries.get(loc)
            if entry is None or entry['type']!='file':
                observation='missing'
                if required: issues.append(f"Нет обязательного ресурса {r['id']}: {loc}")
            else:
                is_pointer=read_snapshot_prefix(p,entry,len(LFS))==LFS
                observation='lfs_pointer' if is_pointer else 'present'
                if required and is_pointer: issues.append(f"Обязательный ресурс {r['id']} является LFS-указателем")
        # The location can contain secrets, especially in a URL query. Expose
        # the ID and observation, not the external location or credentials.
        resources.append({'id':r['id'],'scope':r['scope'],'required':required,
                          'declared_status':r['status'],'observation':observation})
    if meta['discovery_status']=='confirmed' and recorded_requirements != compiled['requirements_hash']:
        warnings.append('Подтверждение не соответствует зафиксированным требованиям или сценариям')
    if meta['discovery_status']!='confirmed': warnings.append('Инвентаризация не подтверждена')
    if compiled['freshness']!='current': warnings.append('Привязка очереди к исходнику устарела или неизвестна')
    if not entries: warnings.append('Матрица пуста; отсутствие страниц не является полной проверкой')
    if (md._safe_read(path)!=raw or md._recorded_requirements(work, raw)!=recorded_requirements
            or take_snapshot(site,'delivery')['digest']!=before['digest']):
        raise ValueError('Очередь, HEAD или candidate изменился во время проверки')
    after=md.compile_queue(raw.decode('utf8'),source)
    if after['requirements_hash']!=compiled['requirements_hash'] or after['source_snapshot_current']!=compiled['source_snapshot_current']:
        raise ValueError('Источник или сценарии изменились во время проверки')
    return {'status':'FAIL' if issues else 'INCOMPLETE', 'operation':'not_applied', 'issues':issues,
            'warnings':list(dict.fromkeys(warnings)), 'freshness':compiled['freshness'],
            'source_snapshot':compiled['source_snapshot_current'], 'requirements_hash':compiled['requirements_hash'],
            'queue_sha256':md.sha(raw),'delivery_snapshot':before['digest'], 'static':static,
            'coverage':{'planned':len(entries),'executed':0,'entries':entries}, 'resources':resources,
            'reference_provenance':'unknown','eligible':False,
            'next':'Матрица только диагностическая: выполните браузерные и ручные проверки; публикация заблокирована.'}
