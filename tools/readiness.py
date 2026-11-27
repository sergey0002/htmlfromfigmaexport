"""Combine current requirements and diagnostic observations without granting trust.

All externally sourced or user-writable observations remain claims. This matrix
provides actionable blockers and never authorizes checked/publish.
"""
from __future__ import annotations

import json
from pathlib import Path

from . import queue_md as md, run_store, manual_evidence
from .coverage import diagnostic


def _key(entry):
    return run_store.matrix_key(entry)


def evaluate(source,site,run_record=None,run_sha256=None,manual_record=None,manual_sha256=None):
    if bool(run_record)!=bool(run_sha256) or bool(manual_record)!=bool(manual_sha256):
        raise ValueError('Для каждой записи нужен путь и ожидаемый sha256')
    source=Path(source).absolute(); work=source/'.work'; site=Path(site).absolute()
    base=diagnostic(source,site)
    raw=md._safe_read(md._path(work,work/'PAGE-QUEUE.md'))
    if md.sha(raw)!=base['queue_sha256']: raise ValueError('Очередь изменилась перед анализом')
    data=md.parse(raw.decode('utf8')); meta={row['key']:row['value'] for row in data['meta']}
    blockers=[]
    if meta['discovery_status']!='confirmed': blockers.append('Инвентаризация не подтверждена')
    if md._recorded_requirements(work,raw)!=base['requirements_hash']:
        blockers.append('Требования, сценарии или template policy не соответствуют зафиксированной ревизии')
    if base['freshness']!='current': blockers.append('Очередь не привязана к текущему исходнику')
    if base['issues']: blockers.append('Статическая проверка содержит ошибки')
    unchecked_resources=[r['id'] for r in base['resources'] if r['required'] and r['observation']=='external_unverified']
    if unchecked_resources:
        blockers.append('Обязательные внешние ресурсы не проверены: '+', '.join(unchecked_resources))
    unsettled_resources=[r['id'] for r in base['resources'] if r['required'] and r['declared_status']!='available']
    if unsettled_resources:
        blockers.append('В очереди обязательные ресурсы отмечены missing или unknown: '+', '.join(unsettled_resources))
    if any(p['required']=='true' and p['work_status']!='built' for p in data['pages']): blockers.append('Обязательные страницы ещё не отмечены как построенные')
    if not any(p['required']=='true' and p['confirmation']=='confirmed' for p in data['pages']): blockers.append('Нет подтверждённых обязательных страниц')
    for name in ('header.php','footer.php'):
        path=site/'template'/name
        if not path.is_file(): blockers.append(f'Нет обязательной CMS-заготовки template/{name}')
    missing=[s for s in data['states'] if s['required']=='true' and not s['scenario']]
    if missing: blockers.append('Нет сценариев для обязательных состояний: '+', '.join(f"{s['page_id']}/{s['state_id']}" for s in missing))
    entries=[dict(row) for row in base['coverage']['entries']]
    expected={_key(row):row for row in entries}
    if len(expected)!=len(entries): raise ValueError('Повторные ключи исходной матрицы')
    run_info=None; browser_status=None
    if run_record:
        run_info=run_store.inspect(source,site,run_record,run_sha256)
        if run_info['freshness']!='current':
            blockers.append('Запись браузерного запуска устарела или артефакты изменились')
        else:
            record=run_info['record']; directory=run_store._audit_path(work,work/record['audit_directory'])
            _,summary=run_store._summary(work,directory,record['summary_sha256'])
            seen=set()
            for row in summary['coverage']['entries']:
                key=_key(row)
                if key in seen or key not in expected: raise ValueError('Матрица запуска содержит лишний или повторный ключ')
                seen.add(key); target=expected[key]
                if type(row.get('required'))!=bool or row['required']!=target['required']:
                    raise ValueError('Обязательность в матрице запуска не совпадает с очередью')
                if row.get('execution') not in ('not_run','executed','blocked') or row.get('outcome') not in ('unknown','review','pass','fail'):
                    raise ValueError('Некорректный outcome матрицы')
                target['execution']=row['execution']
                # A claimed pass with unverified provenance is still review.
                target['outcome']='review' if row['outcome']=='pass' else row['outcome']
                target['reason']='Внешний эталон и происхождение запуска не подтверждены' if row['execution']=='executed' else row.get('reason','Не выполнено')
                target['artifacts']=row.get('artifacts',[])
            browser_status=summary.get('status')
            if browser_status in ('FAIL','BLOCKED'): blockers.append('Браузерный запуск завершился ошибкой или блокировкой')
    else:
        blockers.append('Нет зафиксированного браузерного запуска')
    outstanding=[row for row in entries if row['required'] and (row['execution']!='executed' or row['outcome']!='pass')]
    if outstanding: blockers.append(f'Обязательные проверки не подтверждены: {len(outstanding)} из {sum(r["required"] for r in entries)}')
    blockers.append('Происхождение эталона и изоляция браузера не подтверждены')
    manual=None
    if manual_record:
        manual=manual_evidence.inspect(source,site,manual_record,manual_sha256)
        if manual['freshness']!='current': blockers.append('Ручное заявление устарело')
        elif manual['attestation']['outcome']=='fail': blockers.append('В актуальном ручном заявлении указан fail (личность и содержание не аутентифицированы)')
        elif manual['attestation']['outcome']=='incomplete': blockers.append('В актуальном ручном заявлении указана неполная проверка')
    else: blockers.append('Нет отдельного ручного заявления о проверке')
    blockers.append('Ручное заявление и личность не аутентифицированы; полной приёмки нет')
    after=diagnostic(source,site)
    for key in ('source_snapshot','queue_sha256','requirements_hash','delivery_snapshot'):
        if after[key]!=base[key]: raise ValueError('Исходные данные изменились во время анализа')
    if run_info and run_info['freshness']=='current':
        again=run_store.inspect(source,site,run_record,run_sha256)
        if again['freshness']!='current': raise ValueError('Запуск или артефакты изменились во время анализа')
    if manual and manual['freshness']=='current':
        again=manual_evidence.inspect(source,site,manual_record,manual_sha256)
        if again['freshness']!='current': raise ValueError('Ручная запись изменилась во время анализа')
    reported_manual_failure=bool(manual and manual['freshness']=='current' and manual['attestation']['outcome']=='fail')
    observed_failure=bool(base['issues']) or browser_status=='FAIL' or any(row['outcome']=='fail' for row in entries)
    status='FAIL' if observed_failure or reported_manual_failure else 'BLOCKED' if browser_status=='BLOCKED' else 'INCOMPLETE'
    return {'status':status, 'operation':'not_applied', 'eligible':False,
            'source_snapshot':base['source_snapshot'],'queue_sha256':base['queue_sha256'],
            'requirements_hash':base['requirements_hash'],'delivery_snapshot':base['delivery_snapshot'],
            'coverage':{'planned':len(entries),'required':sum(r['required'] for r in entries),
                        'required_unconfirmed':len(outstanding),'entries':entries}, 'resources':base['resources'],
            'run':None if run_info is None else {'path':run_info['path'],'sha256':run_info['sha256'],'freshness':run_info['freshness']},
            'manual':None if manual is None else {'path':manual['path'],'sha256':manual['sha256'],'freshness':manual['freshness'],
                                                   'reported_outcome':manual['attestation']['outcome'],'verified_identity':False},
            'blockers':list(dict.fromkeys(blockers)), 'warnings':base['warnings'], 'issues':base['issues'],
            'next':'Исправьте конкретные пропуски; этот отчёт не заменяет доказанную приёмку.'}
