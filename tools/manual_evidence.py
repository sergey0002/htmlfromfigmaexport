"""Non-authenticated manual observations bound to current input snapshots.

An attestation records a claim, not proof that a person actually inspected it.
"""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path

from . import queue_md as md
from .coverage import diagnostic


class ManualRecordUncertain(OSError):
    pass


_BINDINGS=('source_snapshot','queue_sha256','requirements_hash','delivery_snapshot')
_FIELDS={'version','kind','actor','scope','actions','outcome','limitations','time',*_BINDINGS,
         'reference_provenance','verified_identity','publication_eligible'}


def create(source, site, output, actor, scope, actions, outcome, limitations):
    if outcome not in ('pass','fail','incomplete'): raise ValueError('Недопустимый исход ручной проверки')
    for value in (actor,scope,actions,limitations):
        if not isinstance(value,str) or not value.strip() or len(value)>4000: raise ValueError('Нужны actor, scope, actions и limitations длиной до 4000 символов')
    source=Path(source).absolute(); work=source/'.work'
    root=md._path(work,work/'manual-attestations',existing=False)
    path=md._path(work,output,existing=False)
    if path.parent!=root or path.exists() or path.name.startswith('.') or path.suffix!='.json': raise ValueError('Нужен новый .json непосредственно в .work/manual-attestations')
    baseline=diagnostic(source,site)
    entry={'version':1,'kind':'manual-attestation','actor':actor.strip(),'scope':scope.strip(),
           'actions':actions.strip(),'outcome':outcome,'limitations':limitations.strip(),
           'time':datetime.now(timezone.utc).isoformat(),'queue_sha256':baseline['queue_sha256'],
           'source_snapshot':baseline['source_snapshot'],'requirements_hash':baseline['requirements_hash'],
           'delivery_snapshot':baseline['delivery_snapshot'],'reference_provenance':'external-unverified',
           'verified_identity':False,'publication_eligible':False}
    raw=(json.dumps(entry,ensure_ascii=False,indent=2)+'\n').encode('utf8')
    current=diagnostic(source,site)
    if any(current[k]!=baseline[k] for k in _BINDINGS):
        raise ValueError('Источник, очередь, требования или candidate изменились при подготовке заявления')
    try:
        root.mkdir(exist_ok=True)
        md._write_new(path,raw); md._sync_dir(root)
    except Exception as exc:
        raise ManualRecordUncertain(f'Ручная запись могла быть создана частично: {path}; проверить перед повтором: {exc}') from exc
    return {'path':str(path),'sha256':md.sha(raw),'attestation':entry,'operation':'applied'}


def inspect(source, site, path, expected_hash):
    source=Path(source).absolute(); work=source/'.work'; path=md._path(work,path)
    if path.parent!=work/'manual-attestations' or not md.HEX.fullmatch(expected_hash or ''): raise ValueError('Нужны корректная запись и её sha256')
    raw=md._safe_read(path)
    if md.sha(raw)!=expected_hash: raise ValueError('Аттестация изменена')
    entry=json.loads(raw.decode('utf8'))
    if (not isinstance(entry,dict) or set(entry)!=_FIELDS or type(entry.get('version')) is not int or entry['version']!=1 or
            entry['kind']!='manual-attestation' or entry['reference_provenance']!='external-unverified' or
            entry['verified_identity'] is not False or entry['publication_eligible'] is not False or
            entry['outcome'] not in ('pass','fail','incomplete') or
            any(not isinstance(entry[key],str) or not entry[key].strip() or len(entry[key])>4000 for key in ('actor','scope','actions','limitations','time')) or
            any(not isinstance(entry[key],str) or not md.HEX.fullmatch(entry[key]) for key in _BINDINGS)):
        raise ValueError('Неизвестный или некорректный формат аттестации')
    current=diagnostic(source,site)
    changes=[k for k in _BINDINGS if entry[k]!=current[k]]
    return {'path':str(path),'sha256':expected_hash, 'freshness':'stale' if changes else 'current',
            'changed':changes, 'attestation':entry,'publication_eligible':False}
