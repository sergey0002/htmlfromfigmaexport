"""Integrity records for diagnostic browser runs, not authenticated evidence.

Hashes detect change relative to a caller-retained record hash. They cannot prove
who ran a test, that an endpoint served the claimed source, or that coverage is
complete. No record created here can enable publication.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from . import queue_md as md
from .coverage import diagnostic
from .snapshot import take_snapshot
from .png_integrity import inspect as inspect_png
from .tool_identity import current as tool_identity

MAX_SUMMARY = 32_000_000
_BINDINGS=('source_snapshot','queue_sha256','requirements_hash','delivery_snapshot')
_RECORD_FIELDS={'version','kind','recorded_at','audit_directory','summary_sha256','artifacts_snapshot',
                'artifact_files','bindings','config','config_sha256','toolchain','toolchain_sha256',
                'scenario_sha256','started_at','finished_at','browser_versions','coverage_sha256',
                'coverage_planned','coverage_executed','reported_status','static_reference_binding',
                'reference_provenance','authenticated','publication_eligible'}


class RunRecordUncertain(OSError):
    pass


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf8')


def _sha(value):
    return hashlib.sha256(value).hexdigest()


def _audit_path(work, directory):
    directory = md._path(work, directory)
    if directory.parent != work/'audits-md' or not directory.is_dir() or directory.name.startswith('.'):
        raise ValueError('Нужен каталог запуска непосредственно в .work/audits-md')
    return directory


def matrix_key(entry):
    if not isinstance(entry,dict): raise ValueError('Некорректная запись матрицы')
    viewport=entry.get('viewport')
    if not isinstance(viewport,list) or len(viewport)!=2 or any(type(v)!=int or v<1 or v>20000 for v in viewport):
        raise ValueError('Некорректный viewport записи')
    if any(not isinstance(entry.get(k),str) or not entry[k] for k in ('page_id','route','state')):
        raise ValueError('Некорректный ключ записи матрицы')
    return (entry['page_id'],entry['route'],tuple(viewport),entry['state'])


def _validate_matrix(summary, current):
    """Verify the recorded plan, not the authenticity of claimed execution."""
    planned=current['coverage']['entries']; expected={matrix_key(row):row for row in planned}
    if len(expected)!=len(planned): raise ValueError('Повторные ключи исходной матрицы')
    seen=set()
    for row in summary['coverage']['entries']:
        key=matrix_key(row)
        if key in seen or key not in expected: raise ValueError('Матрица запуска содержит лишний или повторный ключ')
        seen.add(key)
        if type(row.get('required'))!=bool or row['required']!=expected[key]['required']:
            raise ValueError('Обязательность в матрице запуска не совпадает с очередью')
    if seen!=set(expected): raise ValueError('Матрица запуска неполна относительно очереди')


def _validate_observations(summary, directory, snapshot):
    """Cross-check matrix, child reports and artifact inventory, not provenance."""
    rows={matrix_key(row):row for row in summary['coverage']['entries']}
    files={entry['path']:entry for entry in snapshot['entries'] if entry['type']=='file'}
    def check_images(folder, viewport, name, prefix, comparison):
        if not isinstance(comparison,dict): raise ValueError('Некорректная запись снимка')
        dimensions={}
        for key in ('reference_size','candidate_size','canvas_size'):
            value=comparison.get(key)
            if (not isinstance(value,list) or len(value)!=2 or
                    any(type(v) is not int or not 1<=v<=20000 for v in value) or value[0]*value[1]>12_000_000):
                raise ValueError('Некорректные размеры снимка')
            dimensions[key]=value
        if dimensions['canvas_size']!=[max(dimensions['reference_size'][i],dimensions['candidate_size'][i]) for i in range(2)]:
            raise ValueError('Размер canvas не соответствует снимкам')
        if prefix!='full' and (dimensions['reference_size']!=list(viewport) or dimensions['candidate_size']!=list(viewport)):
            raise ValueError('Размер поэкранного снимка не соответствует viewport')
        for side in ('reference','candidate','diff','overlay','heatmap'):
            path=comparison.get(side)
            expected=(Path(f'{viewport[0]}x{viewport[1]}')/name/f'{prefix}-{side}.png').as_posix()
            if not isinstance(path,str) or Path(path).as_posix()!=expected:
                raise ValueError('Недопустимый путь снимка состояния')
            entry=files.get((Path(folder.name)/expected).as_posix())
            if entry is None or entry['size']<1:
                raise ValueError('Снимок состояния отсутствует или пуст')
            actual=inspect_png(folder/Path(expected),entry)
            claimed=dimensions[side+'_size'] if side in ('reference','candidate') else dimensions['canvas_size']
            if actual!=claimed: raise ValueError('Размер PNG не соответствует сводке снимка')
    observed=set(); routes=set(); folders=set()
    for run in summary['runs']:
        page=run.get('page_id'); route=run.get('route'); folder=run.get('artifact_directory')
        if not isinstance(page,str) or not isinstance(route,str) or not isinstance(folder,str):
            raise ValueError('Некорректная запись дочернего запуска')
        route_key=(page,route)
        if route_key in routes or not any(key[:2]==route_key for key in rows):
            raise ValueError('Повторный или незапланированный маршрут дочернего запуска')
        routes.add(route_key)
        path=Path(folder)
        if not path.is_absolute() or path.parent!=directory or path.name.startswith('.') or path in folders:
            raise ValueError('Недопустимый каталог дочерних артефактов')
        folders.add(path)
        viewports=run['result'].get('viewports',[])
        if not isinstance(viewports,list): raise ValueError('Некорректные viewport дочернего запуска')
        for viewport in viewports:
            if (not isinstance(viewport,dict) or type(viewport.get('width')) is not int or
                    type(viewport.get('height')) is not int or not isinstance(viewport.get('states'),list)):
                raise ValueError('Некорректный viewport дочернего запуска')
            for state in viewport['states']:
                if (not isinstance(state,dict) or not isinstance(state.get('name'),str) or
                        state.get('status') not in ('OK','REVIEW','FAIL','BLOCKED')):
                    raise ValueError('Некорректное состояние дочернего запуска')
                key=(page,route,(viewport['width'],viewport['height']),state['name'])
                if key not in rows or key in observed: raise ValueError('Лишнее или повторное состояние дочернего запуска')
                observed.add(key); row=rows[key]; status=state['status']
                execution='blocked' if status=='BLOCKED' else 'executed'
                outcome='unknown' if status=='BLOCKED' else 'fail' if status=='FAIL' else 'review'
                if row['execution']!=execution or row['outcome']!=outcome or row['artifacts']!=[folder]:
                    raise ValueError('Матрица противоречит дочерним состояниям или путям артефактов')
                if execution=='executed':
                    if path.is_symlink() or not path.is_dir():
                        raise ValueError('Каталог выполненного состояния отсутствует или является ссылкой')
                    screens=state.get('screens'); name=state['name']; size=(viewport['width'],viewport['height'])
                    if not isinstance(screens,list) or not 1<=len(screens)<=100:
                        raise ValueError('Выполненное состояние не содержит поэкранных снимков')
                    for index,screen in enumerate(screens,start=1):
                        if not isinstance(screen,dict) or type(screen.get('index')) is not int or screen['index']!=index:
                            raise ValueError('Непоследовательные номера снимков')
                        check_images(path,size,name,f'{index:03d}',screen)
                    for key in ('action','fullpage'):
                        if state.get(key) is not None: check_images(path,size,name,'action' if key=='action' else 'full',state[key])
    for key,row in rows.items():
        if key not in observed and (row['execution']!='not_run' or row['outcome']!='unknown' or row['artifacts']):
            raise ValueError('Матрица заявляет состояние без дочернего результата')


def _expected_scenarios(work, queue_sha256):
    raw=md._safe_read(md._path(work,work/'PAGE-QUEUE.md'))
    if md.sha(raw)!=queue_sha256: raise ValueError('Очередь изменилась при проверке сценариев')
    queue=md.parse(raw.decode('utf8'))
    return {state['scenario']:md._scenario_hash(work,state['scenario']) for state in queue['states'] if state['scenario']}


def _summary(work, directory, expected_sha256):
    if not isinstance(expected_sha256, str) or not md.HEX.fullmatch(expected_sha256):
        raise ValueError('Нужен sha256 байтов summary.json')
    raw = md._safe_read(md._path(work, directory/'summary.json'), MAX_SUMMARY)
    if _sha(raw) != expected_sha256:
        raise ValueError('summary.json изменился')
    data = json.loads(raw.decode('utf8'))
    if not isinstance(data, dict) or data.get('kind') != 'diagnostic-browser-matrix' or type(data.get('schema_version')) is not int or data.get('schema_version') != 1:
        raise ValueError('Неизвестный формат диагностического запуска')
    if data.get('reference_provenance') != 'external-unverified' or data.get('eligible') is not False:
        raise ValueError('Недопустимый provenance или eligibility')
    if not isinstance(data.get('config'), dict) or _sha(_canonical(data['config'])) != data.get('config_sha256'):
        raise ValueError('Конфигурация запуска повреждена')
    if not isinstance(data.get('toolchain'),dict) or _sha(_canonical(data['toolchain']))!=data.get('toolchain_sha256'):
        raise ValueError('Отсутствует или повреждена версия инструментария; повторите аудит')
    for key in ('source_snapshot', 'queue_sha256', 'requirements_hash', 'delivery_snapshot'):
        if not isinstance(data.get(key),str) or not md.HEX.fullmatch(data[key]):
            raise ValueError(f'Недопустимый hash: {key}')
    scenarios=data.get('scenario_sha256')
    if not isinstance(scenarios,dict) or any(not isinstance(k,str) or not md._relpath(k) or (v is not None and (not isinstance(v,str) or not md.HEX.fullmatch(v))) for k,v in scenarios.items()):
        raise ValueError('Некорректные hashes сценариев')
    coverage=data.get('coverage')
    if not isinstance(coverage,dict) or not isinstance(coverage.get('entries'),list):
        raise ValueError('Нет матрицы coverage')
    entries=coverage['entries']
    if (data.get('status') not in ('INCOMPLETE','FAIL','BLOCKED') or
            any(not isinstance(entry,dict) or
                (entry.get('execution'),entry.get('outcome')) not in (('not_run','unknown'),('blocked','unknown'),
                                                                       ('executed','review'),('executed','pass'),('executed','fail')) or
                not isinstance(entry.get('reason'),str) or not isinstance(entry.get('artifacts'),list) or
                any(not isinstance(path,str) for path in entry['artifacts']) for entry in entries) or
            type(coverage.get('planned')) is not int or coverage['planned']!=len(entries) or
            type(coverage.get('executed')) is not int or coverage['executed']!=sum(entry['execution']=='executed' for entry in entries)):
        raise ValueError('Некорректная статистика диагностической матрицы')
    runs=data.get('runs')
    if (not isinstance(runs,list) or any(not isinstance(row,dict) or not isinstance(row.get('result'),dict) or
            row['result'].get('status') not in ('INCOMPLETE','FAIL','BLOCKED') for row in runs)):
        raise ValueError('Некорректные результаты дочерних запусков')
    versions=data.get('browser_versions')
    if (not isinstance(versions,list) or any(not isinstance(v,str) or not v for v in versions) or
            versions!=sorted(set(versions)) or
            any(row['result'].get('browser_version') is not None and not isinstance(row['result']['browser_version'],str) for row in runs) or
            versions!=sorted({row['result']['browser_version'] for row in runs if row['result'].get('browser_version')})):
        raise ValueError('Некорректные версии браузера дочерних запусков')
    try:
        started=datetime.fromisoformat(data['started_at']); finished=datetime.fromisoformat(data['finished_at'])
        if started.utcoffset() is None or finished.utcoffset() is None or finished<started: raise ValueError('Время не упорядочено')
    except (ValueError,TypeError,KeyError) as exc:
        raise ValueError('Некорректное время диагностического запуска') from exc
    issues=data.get('issues')
    if not isinstance(issues,list) or any(not isinstance(issue,str) for issue in issues):
        raise ValueError('Некорректный список проблем запуска')
    failed=any(row['outcome']=='fail' for row in entries) or any(row['result']['status']=='FAIL' for row in runs)
    blocked=bool(issues) or any(row['execution']=='blocked' for row in entries) or any(row['result']['status']=='BLOCKED' for row in runs)
    if (failed and data['status']!='FAIL') or (blocked and data['status']=='INCOMPLETE'):
        raise ValueError('Итоговый статус противоречит ошибке или блокировке дочернего запуска')
    return raw, data


def _static_binding(source, work, directory):
    from . import static_reference
    path=md._path(work,directory/'static-reference-binding.json',existing=False)
    if not path.exists(): return None
    raw=md._safe_read(path)
    binding=json.loads(raw.decode('utf8'))
    keys={'version','kind','record','record_sha256','reference_snapshot','source_snapshot','isolated'}
    if (not isinstance(binding,dict) or set(binding)!=keys or binding['version']!=1
            or binding['kind']!='static-reference-binding' or binding['isolated'] is not False
            or not isinstance(binding['record'],str)):
        raise ValueError('Некорректная привязка статического эталона')
    info=static_reference.inspect(source,binding['record'],binding['record_sha256'])
    if (info['freshness']!='current' or info['record']['reference_snapshot']!=binding['reference_snapshot']
            or info['record']['source_snapshot']!=binding['source_snapshot']):
        raise ValueError('Привязка статического эталона устарела')
    return {'sha256':_sha(raw),'binding':binding}


def seal(source, site, directory, expected_summary_sha256, output=None):
    """Record one complete diagnostic directory, without conferring trust."""
    source=Path(source).absolute(); work=source/'.work'
    directory=_audit_path(work, directory)
    raw, summary=_summary(work,directory,expected_summary_sha256)
    if tool_identity()[1]!=summary['toolchain_sha256']:
        raise ValueError('Инструментарий изменился после запуска; выполните аудит повторно')
    current=diagnostic(source,site)
    bindings=_BINDINGS
    if any(summary[k] != current[k] for k in bindings):
        raise ValueError('Запуск устарел относительно очереди, source, сценариев или candidate')
    _validate_matrix(summary,current)
    before=take_snapshot(directory,'delivery')
    _validate_observations(summary,directory,before)
    if summary['scenario_sha256']!=_expected_scenarios(work,current['queue_sha256']):
        raise ValueError('Список сценариев отсутствует, отличается от очереди или устарел')
    binding=_static_binding(source,work,directory)
    if md._safe_read(md._path(work,directory/'summary.json'),MAX_SUMMARY)!=raw:
        raise ValueError('Отчёт изменился при записи')
    if take_snapshot(directory,'delivery')['digest']!=before['digest']:
        raise ValueError('Артефакты изменились при записи')
    after=diagnostic(source,site)
    if (any(after[k]!=current[k] for k in bindings) or _static_binding(source,work,directory)!=binding
            or tool_identity()[1]!=summary['toolchain_sha256']):
        raise ValueError('Исходные данные, статический эталон или инструментарий изменились при записи')
    root=md._path(work,work/'run-records',existing=False)
    path=md._path(work,output or root/(uuid.uuid4().hex+'.json'),existing=False)
    if path.parent!=root or path.exists() or path.suffix!='.json' or path.name.startswith('.'):
        raise ValueError('Нужен новый .json непосредственно в .work/run-records')
    record={'version':1,'kind':'diagnostic-browser-run-record',
            'recorded_at':datetime.now(timezone.utc).isoformat(),
            'audit_directory':directory.relative_to(work).as_posix(),
            'summary_sha256':expected_summary_sha256,'artifacts_snapshot':before['digest'],
            'artifact_files':sum(e['type']=='file' for e in before['entries']),
            'bindings':{k:summary[k] for k in bindings},
            'config':summary['config'],'config_sha256':summary['config_sha256'],
            'toolchain':summary['toolchain'],'toolchain_sha256':summary['toolchain_sha256'],
            'scenario_sha256':summary['scenario_sha256'],
            'started_at':summary.get('started_at'),'finished_at':summary.get('finished_at'),
            'browser_versions':summary.get('browser_versions',[]),
            'coverage_sha256':_sha(_canonical(summary['coverage'])),
            'coverage_planned':summary['coverage'].get('planned'),
            'coverage_executed':summary['coverage'].get('executed'),
            'reported_status':summary.get('status'), 'static_reference_binding':binding,
            'reference_provenance':'external-unverified', 'authenticated':False,'publication_eligible':False}
    encoded=(json.dumps(record,ensure_ascii=False,indent=2)+'\n').encode('utf8')
    try:
        root.mkdir(exist_ok=True)
        md._write_new(path,encoded); md._sync_dir(root)
    except Exception as exc:
        raise RunRecordUncertain(f'Запись или каталог могли быть созданы частично: {path}; проверить перед повтором: {exc}') from exc
    return {'path':str(path),'sha256':_sha(encoded),'record':record,'operation':'applied'}


def inspect(source, site, file, expected_sha256):
    source=Path(source).absolute(); work=source/'.work'
    path=md._path(work,file)
    if path.parent!=work/'run-records' or not isinstance(expected_sha256,str) or not md.HEX.fullmatch(expected_sha256):
        raise ValueError('Нужна запись в .work/run-records и её sha256')
    raw=md._safe_read(path,MAX_SUMMARY)
    if _sha(raw)!=expected_sha256: raise ValueError('Запись запуска изменена')
    record=json.loads(raw.decode('utf8'))
    if (not isinstance(record,dict) or set(record)!=_RECORD_FIELDS or type(record.get('version')) is not int or record['version']!=1 or
            record.get('kind')!='diagnostic-browser-run-record' or record.get('reference_provenance')!='external-unverified' or
            record.get('authenticated') is not False or record.get('publication_eligible') is not False or
            not isinstance(record.get('recorded_at'),str) or
            any(type(record.get(k)) is not int or record[k]<0 for k in ('artifact_files','coverage_planned','coverage_executed')) or
            any(not isinstance(record.get(k),str) or not md.HEX.fullmatch(record[k]) for k in ('summary_sha256','artifacts_snapshot','coverage_sha256'))):
        raise ValueError('Неизвестная или повреждённая запись запуска')
    rel=record.get('audit_directory')
    if not isinstance(rel,str) or not md._relpath(rel): raise ValueError('Недопустимый путь запуска')
    bindings=record.get('bindings')
    keys=_BINDINGS
    if not isinstance(bindings,dict) or set(bindings)!=set(keys) or any(not isinstance(bindings.get(k),str) or not md.HEX.fullmatch(bindings[k]) for k in keys):
        raise ValueError('Некорректные привязки запуска')
    current=diagnostic(source,site)
    changed=[k for k in keys if current[k]!=bindings[k]]
    artifact_error=None
    try:
        directory=_audit_path(work,work/rel)
        _,summary=_summary(work,directory,record.get('summary_sha256'))
        snapshot=take_snapshot(directory,'delivery')
        if snapshot['digest']!=record.get('artifacts_snapshot'):
            changed.append('artifacts')
        if sum(entry['type']=='file' for entry in snapshot['entries'])!=record['artifact_files']:
            changed.append('record_mismatch')
        if _sha(_canonical(summary['coverage']))!=record.get('coverage_sha256'):
            changed.append('coverage')
        if (summary['coverage']['planned']!=record['coverage_planned'] or
                summary['coverage']['executed']!=record['coverage_executed'] or
                summary['status']!=record['reported_status'] or
                any(summary.get(k)!=record[k] for k in ('started_at','finished_at','browser_versions'))):
            changed.append('record_mismatch')
        if not changed:
            _validate_matrix(summary,current)
            _validate_observations(summary,directory,snapshot)
            if summary['scenario_sha256']!=_expected_scenarios(work,current['queue_sha256']):
                changed.append('scenarios')
        if _static_binding(source,work,directory)!=record.get('static_reference_binding'):
            changed.append('static_reference_binding')
        if (any(summary[k]!=bindings[k] for k in keys) or summary['config']!=record.get('config')
                or summary['config_sha256']!=record.get('config_sha256')
                or summary['toolchain']!=record.get('toolchain') or summary['toolchain_sha256']!=record.get('toolchain_sha256')
                or summary['scenario_sha256']!=record.get('scenario_sha256')):
            changed.append('record_mismatch')
        if tool_identity()[1]!=record.get('toolchain_sha256'):
            changed.append('toolchain')
        scenarios=record.get('scenario_sha256')
        if not isinstance(scenarios,dict): raise ValueError('Некорректные сценарии записи')
        if any(md._scenario_hash(work,scenario)!=digest for scenario,digest in scenarios.items()):
            changed.append('scenarios')
    except (ValueError,OSError,UnicodeError,TypeError,KeyError) as exc:
        changed.append('artifacts'); artifact_error=str(exc)
    return {'path':str(path),'sha256':expected_sha256,'record':record,
            'freshness':'stale' if changed else 'current','changed':list(dict.fromkeys(changed)),
            'artifact_error':artifact_error,'authenticated':False,'publication_eligible':False,
            'operation':'not_applied'}
