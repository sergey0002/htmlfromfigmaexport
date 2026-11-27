"""Report execution policy without starting arbitrary project code."""
from __future__ import annotations
import os
import platform
import shutil
from . import cgroup_probe


def inspect():
    return {'platform':platform.system(), 'architecture':platform.machine(),
            'resource_controls':cgroup_probe.inspect() if platform.system()=='Linux' else {
                'status':'unknown','reason':'Только Linux cgroup v2; текущая ОС не проверена',
                'delegation_verified':False,'aggregate_limits_verified':False,'disk_quota':'unknown','executes_project':False},
            'tools':{name:bool(shutil.which(name)) for name in ('unshare','ip','node','npm')},
            'profiles':{
                'managed-isolated':{'available':False,'reason':'Нет проверенного универсального backend и разделения доверия browser/reference/candidate.'},
                'managed-local':{'available':False,'reason':'Нет согласованной оценки риска и разрешения на запуск экспорта без изоляции.'},
                'managed-static-diagnostic':{'available':True,'reason':'Только копия явно выбранных статических файлов; браузер исполняет JS. Нет ОС-изоляции или доверенной приёмки, требуется подтверждение риска и подходящая среда.'},
                'external-unverified':{'available':True,'reason':'Только диагностический URL, provenance и безопасность необходимо проверять отдельно.'}},
            'executes_project':False}
