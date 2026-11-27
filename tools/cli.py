"""CLI for inventory, static checks and opt-in browser audits."""
from __future__ import annotations
import argparse
import contextlib
import json
import os
import stat
import hashlib
import uuid
from pathlib import Path
from .core import analyze, check_site, fingerprint
from .snapshot import take_snapshot
from . import queue_md, delivery, migrate_queue, coverage, publication, audit_markdown, manual_evidence, runner_profiles, run_store, readiness, static_reference, locked_npm, locked_pnpm, pnpm_tree, templates, synthetic_runner
from .facts import scan_facts
from .browser import compare
from .screen_audit import load_scenarios
from .audit_runner import run as run_audit, brief_report
from .queue import load, save, check_manifest
from .lifecycle import record, stale_checks, publish, serve_site, MutationUncertainError


def workspace(source):
    source = Path(source).absolute()
    for p in (source, source / '.work'):
        if p.is_symlink(): raise ValueError('Symlink рабочей области запрещён')
    if not source.is_dir(): raise ValueError('Каталог source не найден')
    return source / '.work'


def _report_location(args):
    """Preflight a report without creating directories or reserving files.

    Reports can be direct non-hidden files under a workspace, or descendants of
    its reports directory. Tool-owned directories and queue files are reserved.
    This is a cooperative-writer check, not a race-free OS sandbox.
    """
    path=Path(args.report).absolute()
    roots=[Path('.work').absolute()]
    if hasattr(args,'source'):
        roots.append(workspace(args.source).absolute())
    elif args.command=='check' and args.manifest:
        manifest=Path(args.manifest).absolute()
        if manifest.name=='manifest.json' and manifest.parent.name=='.work': roots.append(workspace(manifest.parent.parent).absolute())
    matches=[root for root in roots if path!=root and path.is_relative_to(root)]
    if not matches: raise ValueError('Отчёт должен быть новым файлом внутри рабочей папки')
    root=max(matches,key=lambda p:len(p.parts)); parts=path.relative_to(root).parts
    if (not queue_md._relpath('/'.join(parts)) or any(p.startswith('.') for p in parts) or path.suffix.lower()!='.json' or
            (len(parts)>1 and parts[0]!='reports') or
            (len(parts)==1 and parts[0].casefold() in ('manifest.json','page-queue.md'))):
        raise ValueError('Отчёт разрешён только в новом JSON-файле .work или внутри .work/reports; служебные пути запрещены')
    for item in (root,*root.parents):
        if item.is_symlink(): raise ValueError('Symlink пути отчёта запрещён')
        if item.exists() and getattr(item.lstat(),'st_file_attributes',0) & getattr(stat,'FILE_ATTRIBUTE_REPARSE_POINT',0):
            raise ValueError('Reparse point пути отчёта запрещён')
    cursor=root
    for part in parts:
        cursor=cursor/part
        if cursor.is_symlink(): raise ValueError('Symlink пути отчёта запрещён')
        if cursor.exists():
            info=cursor.lstat()
            if getattr(info,'st_file_attributes',0) & getattr(stat,'FILE_ATTRIBUTE_REPARSE_POINT',0): raise ValueError('Reparse point пути отчёта запрещён')
            if cursor!=path and not cursor.is_dir(): raise ValueError('Родитель отчёта не является каталогом')
    if root.exists() and not root.is_dir(): raise ValueError('Рабочая область не является каталогом')
    if path.exists(): raise ValueError('Отчёт уже существует; перезапись запрещена')
    for name in ('output','site','root','audit','file','selection','manifest','plan','scenario','font_css','history','reference_record','run_record','manual_record','delivery_record','evidence'):
        value=getattr(args,name,None)
        if not value: continue
        other=Path(value).absolute()
        if path==other or path.is_relative_to(other) or other.is_relative_to(path):
            raise ValueError(f'Путь отчёта пересекается с --{name.replace("_", "-")}')
    return path,root


def main(argv=None):
    parser = argparse.ArgumentParser(description='Инвентаризация и проверки Figma → vanilla')
    subs = parser.add_subparsers(dest='command', required=True)
    a = subs.add_parser('analyze'); a.add_argument('--source', default='source'); a.add_argument('--include-source-text', action='store_true', help='Показать потенциально чувствительные scripts и значения')
    snap = subs.add_parser('snapshot', help='Версионированный снимок файлов без исполнения проекта')
    snap.add_argument('--root', required=True); snap.add_argument('--kind', choices=['source','delivery'], default='source')
    profiles = subs.add_parser('runner-profiles', help='Политика запуска без выполнения исходника')
    synth = subs.add_parser('runner-synthetic', help='Управляемый эксперимент только на встроенной синтетической фикстуре')
    synth.add_argument('--allow-fixture-registry-network',action='store_true',help='Разрешить сеть registry для синтетических зависимостей')
    synth.add_argument('--timeout',type=int,default=120,help='Таймаут в секундах (1–180)')
    manual = subs.add_parser('manual-attest', help='Записать ручное наблюдение, не автоматическую приёмку')
    manual.add_argument('--source',default='source'); manual.add_argument('--site',required=True); manual.add_argument('--output',required=True)
    manual.add_argument('--actor',required=True); manual.add_argument('--scope',required=True); manual.add_argument('--actions',required=True)
    manual.add_argument('--outcome',choices=['pass','fail','incomplete'],required=True); manual.add_argument('--limitations',required=True)
    mi = subs.add_parser('manual-inspect', help='Проверить привязку ручного наблюдения')
    mi.add_argument('--source',default='source'); mi.add_argument('--site',required=True); mi.add_argument('--file',required=True); mi.add_argument('--sha256',required=True)
    pp = subs.add_parser('pnpm-lock-inventory', help='Статически проверить ограниченный pnpm lock v9 без запуска и установки')
    pp.add_argument('--source',default='source'); pp.add_argument('--project',default='.')
    pc = subs.add_parser('pnpm-lock-cache', help='Проверить или скачать tarballs pnpm lock v9 без установки и исполнения')
    pc.add_argument('--source',default='source'); pc.add_argument('--project',default='.'); pc.add_argument('--allow-registry-network',action='store_true'); pc.add_argument('--selected-platform',action='store_true',help='Только консервативный выбор Linux x64 glibc')
    pt = subs.add_parser('pnpm-tree-prepare', help='Экспериментальное offline дерево pnpm lock v9 без запуска')
    pt.add_argument('--source',default='source'); pt.add_argument('--project',default='.'); pt.add_argument('--output',required=True)
    pi = subs.add_parser('pnpm-tree-inspect', help='Проверить целостность экспериментального дерева pnpm')
    pi.add_argument('--source',default='source'); pi.add_argument('--file',required=True); pi.add_argument('--sha256',required=True)
    np = subs.add_parser('npm-lock-plan', help='Разобрать npm lock v3 без установки и выполнения кода')
    np.add_argument('--source',default='source'); np.add_argument('--project',default='.')
    ni = subs.add_parser('npm-lock-prepare', help='Подготовить tarballs без npm и lifecycle scripts')
    ni.add_argument('--source',default='source'); ni.add_argument('--project',default='.'); ni.add_argument('--output',required=True); ni.add_argument('--allow-registry-network',action='store_true')
    nx = subs.add_parser('npm-lock-inspect', help='Проверить свежесть подготовленных зависимостей')
    nx.add_argument('--source',default='source'); nx.add_argument('--file',required=True); nx.add_argument('--sha256',required=True)
    sr = subs.add_parser('reference-materialize', help='Скопировать выбранные статические файлы эталона без исполнения')
    sr.add_argument('--source',default='source'); sr.add_argument('--selection',required=True); sr.add_argument('--output',required=True)
    si = subs.add_parser('reference-inspect', help='Сверить снимки копии статического эталона и source')
    si.add_argument('--source',default='source'); si.add_argument('--file',required=True); si.add_argument('--sha256',required=True)
    seal = subs.add_parser('run-seal', help='Зафиксировать hashes диагностического запуска без подтверждения provenance')
    seal.add_argument('--source',default='source'); seal.add_argument('--site',required=True); seal.add_argument('--audit',required=True); seal.add_argument('--summary-sha256',required=True); seal.add_argument('--output')
    ri = subs.add_parser('run-inspect', help='Проверить целостность и актуальность записи запуска')
    ri.add_argument('--source',default='source'); ri.add_argument('--site',required=True); ri.add_argument('--file',required=True); ri.add_argument('--sha256',required=True)
    bs = subs.add_parser('browser-audit-static-md', help='Диагностика статической копии; НЕ ОС-изоляция')
    bs.add_argument('--source',default='source'); bs.add_argument('--site',required=True); bs.add_argument('--reference-record',required=True); bs.add_argument('--reference-sha256',required=True); bs.add_argument('--acknowledge-browser-code',action='store_true'); bs.add_argument('--output')
    bmd = subs.add_parser('browser-audit-md', help='Диагностическая браузерная матрица Markdown-очереди')
    bmd.add_argument('--source',default='source'); bmd.add_argument('--site',required=True); bmd.add_argument('--reference-url',required=True); bmd.add_argument('--output')
    ready = subs.add_parser('readiness', help='Свести обязательную матрицу и непроверенные заявления; не разрешает публикацию')
    ready.add_argument('--source',default='source'); ready.add_argument('--site',required=True)
    ready.add_argument('--run-record'); ready.add_argument('--run-sha256'); ready.add_argument('--manual-record'); ready.add_argument('--manual-sha256')
    cov = subs.add_parser('coverage', help='Диагностическая матрица и статическая проверка Markdown-очереди')
    cov.add_argument('--source', default='source'); cov.add_argument('--site', required=True)
    tokens = subs.add_parser('template-tokens', help='Показать потенциально чувствительные token страницы и заготовки без изменений')
    tokens.add_argument('--site',required=True); tokens.add_argument('--page',required=True)
    tokens.add_argument('--block',choices=['HEADER','FOOTER'],required=True)
    tokens.add_argument('--offset',type=int,default=0); tokens.add_argument('--limit',type=int,default=100)
    mat = subs.add_parser('materialize', help='Создать непроверенный delivery по явному списку файлов')
    mat.add_argument('--source', default='source'); mat.add_argument('--site', required=True); mat.add_argument('--selection', required=True); mat.add_argument('--output', required=True)
    mat.add_argument('--permission-profile', choices=['private','web-readable'], default='private', help='По умолчанию приватные права; web-readable доступен только в POSIX')
    mat.add_argument('--acknowledge-world-readable', action='store_true', help='Подтвердить возможную доступность выбранных файлов другим локальным пользователям')
    dsc = subs.add_parser('discover'); dsc.add_argument('--source', default='source'); dsc.add_argument('--offset', type=int, default=0); dsc.add_argument('--limit', type=int, default=100); dsc.add_argument('--file', help='Точный относительный путь анализируемого файла'); dsc.add_argument('--include-source-text', action='store_true', help='Включить потенциально чувствительные исходные фрагменты')
    md = subs.add_parser('queue-md', help='Ограниченная редактируемая Markdown-очередь для новых проектов')
    md_sub = md.add_subparsers(dest='md_command', required=True)
    for name in ('template', 'validate', 'commit', 'inspect-legacy', 'migrate-dry-run', 'migrate-apply', 'migration-inspect', 'migration-recover', 'recover-commit'):
        p = md_sub.add_parser(name); p.add_argument('--source', default='source')
        p.add_argument('--report'); p.add_argument('--json', action='store_true')
        if name in ('template', 'migrate-dry-run'): p.add_argument('--output', required=True)
        elif name in ('validate', 'commit'): p.add_argument('--file', required=True)
        elif name == 'recover-commit':
            p.add_argument('--history',required=True); p.add_argument('--acknowledge-offline-writers',action='store_true')
            expected = p.add_mutually_exclusive_group(required=True)
            expected.add_argument('--expected-sha256'); expected.add_argument('--expect-absent',action='store_true')
        elif name == 'migrate-apply':
            p.add_argument('--plan', required=True); p.add_argument('--expected-manifest-sha256', required=True); p.add_argument('--expected-markdown-sha256', required=True)
            p.add_argument('--acknowledge-offline-writers', action='store_true')
        elif name in ('migration-inspect', 'migration-recover', 'recover-commit'):
            p.add_argument('--id', required=True)
            if name == 'migration-recover':
                p.add_argument('--acknowledge-offline-writers', action='store_true')
                p.add_argument('--clear-stale-lock', action='store_true', help='Только после проверки, что внешних писателей нет')
        if name == 'commit':
            expected = p.add_mutually_exclusive_group(required=True)
            expected.add_argument('--expected-sha256'); expected.add_argument('--expect-absent', action='store_true')
            p.add_argument('--reason', required=True)
    q = subs.add_parser('queue'); q.add_argument('--source', default='source')
    u = subs.add_parser('queue-update'); u.add_argument('--source', default='source'); u.add_argument('--page'); u.add_argument('--work-status', choices=['pending','in_progress','built','blocked']); u.add_argument('--confirm-page', action='store_true'); u.add_argument('--confirm-discovery', action='store_true'); u.add_argument('--resolve-link'); u.add_argument('--resolution', choices=['missing','duplicate','not-a-page']); u.add_argument('--reason')
    rec=subs.add_parser('record-check', help='Сохранить результат проверки с отпечатками')
    rec.add_argument('--source',default='source'); rec.add_argument('--site',required=True); rec.add_argument('--page'); rec.add_argument('--kind',required=True,choices=['static','browser','manual']); rec.add_argument('--status',required=True,choices=['checked','incomplete','fail','blocked','review']); rec.add_argument('--evidence',required=True)
    plan=subs.add_parser('publish-plan', help='Только диагностический diff; применение заблокировано')
    plan.add_argument('--source',default='source'); plan.add_argument('--delivery-record',required=True); plan.add_argument('--target',default='vanilla')
    plan.add_argument('--run-record'); plan.add_argument('--run-sha256'); plan.add_argument('--manual-record'); plan.add_argument('--manual-sha256')
    apply_pub=subs.add_parser('publish-apply', help='Применение плана: пока заблокировано eligibility gate')
    apply_pub.add_argument('--source',default='source'); apply_pub.add_argument('--plan',required=True); apply_pub.add_argument('--sha256',required=True); apply_pub.add_argument('--acknowledge-offline-writers',action='store_true')
    inspect_pub=subs.add_parser('publication-inspect', help='Проверить journal публикации без изменения файлов')
    inspect_pub.add_argument('--source',default='source'); inspect_pub.add_argument('--id',required=True)
    restore_pub=subs.add_parser('publication-restore', help='Явно восстановить проверенный backup из журнала')
    restore_pub.add_argument('--source',default='source'); restore_pub.add_argument('--id',required=True); restore_pub.add_argument('--acknowledge-offline-writers',action='store_true'); restore_pub.add_argument('--clear-stale-lock',action='store_true')
    old=restore_pub.add_mutually_exclusive_group(required=True); old.add_argument('--expected-target-sha256'); old.add_argument('--expect-target-absent',action='store_true')
    pub=subs.add_parser('publish', help='Временно отключён до реализации проверяемой поставки')
    pub.add_argument('--source',default='source'); pub.add_argument('--site',required=True); pub.add_argument('--replace-existing',action='store_true')
    c = subs.add_parser('check'); c.add_argument('--site', default='vanilla'); c.add_argument('--manifest')
    b = subs.add_parser('compare'); b.add_argument('--source',default='source'); b.add_argument('--reference', required=True); b.add_argument('--candidate', required=True)
    b.add_argument('--width', type=int, default=390); b.add_argument('--height', type=int, default=844)
    b.add_argument('--threshold', type=float, default=0.01); b.add_argument('--output')
    b.add_argument('--scenario', help='JSON-файл: список безопасных действий')
    d = subs.add_parser('browser-audit', help='Поэкранная сверка мобильного, планшета и десктопа')
    d.add_argument('--source', default='source'); d.add_argument('--site', default='vanilla')
    d.add_argument('--reference-url'); d.add_argument('--candidate-url')
    d.add_argument('--trust-source', action='store_true', help='Автозапуск без ОС-изоляции отключён')
    d.add_argument('--route', default=None); d.add_argument('--reference-route'); d.add_argument('--candidate-route')
    d.add_argument('--scenario'); d.add_argument('--font-css')
    d.add_argument('--threshold', type=float, default=0.001); d.add_argument('--channel-tolerance', type=int, default=12)
    d.add_argument('--output')
    batch = subs.add_parser('browser-audit-site', help='Пакетная проверка подтверждённых страниц')
    batch.add_argument('--source', default='source'); batch.add_argument('--site', default='vanilla'); batch.add_argument('--manifest'); batch.add_argument('--reference-url', required=True); batch.add_argument('--candidate-url'); batch.add_argument('--output')
    for p in (a,snap,profiles,synth,manual,mi,pp,pc,pt,pi,np,ni,nx,sr,si,seal,ri,bmd,bs,ready,cov,tokens,mat,dsc,q,u,c,b,d,batch,rec,pub,plan,apply_pub,inspect_pub,restore_pub): p.add_argument('--report'); p.add_argument('--json', action='store_true')
    args = parser.parse_args(argv)
    report_fd = None
    if args.report:
        # Preflight first, then reserve before the command. Directory or open
        # failures after the attempt may still leave files/directories behind.
        attempted=False
        try:
            path,root=_report_location(args)
            attempted=True
            path.parent.mkdir(parents=True, exist_ok=True)
            report_fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), 0o600)
        except (OSError, ValueError, UnicodeError) as e:
            failure = {'schema_version':1, 'command':args.command, 'status':'ERROR' if attempted else 'BLOCKED',
                       'issues':[str(e)], 'operation':'not_applied', 'report_operation':'unknown' if attempted else 'not_applied'}
            print(json.dumps(failure, ensure_ascii=False) if args.json else
                  f"{failure['status']}: {e}; команда не выполнена, report_operation={failure['report_operation']}")
            return 4 if attempted else 3
    mutation_started = False
    try:
        if args.command == 'runner-profiles':
            result={'status':'INCOMPLETE','operation':'not_applied','issues':[], 'warnings':[], 'runner':runner_profiles.inspect()}
        elif args.command == 'runner-synthetic':
            result=synthetic_runner.run(args.allow_fixture_registry_network,args.timeout)
        elif args.command == 'analyze': result = analyze(Path(args.source), include_source_text=args.include_source_text)
        elif args.command == 'snapshot':
            snap_result = take_snapshot(Path(args.root), args.kind)
            result = {'status': 'INCOMPLETE', 'issues': [], 'warnings': [], 'snapshot': snap_result,
                      'next': 'Отпечаток не подтверждает качество сайта или происхождение данных.'}
        elif args.command == 'manual-attest':
            item=manual_evidence.create(args.source,args.site,args.output,args.actor,args.scope,args.actions,args.outcome,args.limitations)
            result={'status':'INCOMPLETE','operation':item['operation'],'issues':[], 'warnings':['Ручное заявление не доказывает личность или приёмку.'], 'manual':item}
        elif args.command == 'manual-inspect':
            item=manual_evidence.inspect(args.source,args.site,args.file,args.sha256)
            result={'status':'INCOMPLETE','operation':'not_applied','issues':[], 'warnings':['Это не автоматическое доказательство приёмки.'], 'manual':item}
        elif args.command == 'pnpm-lock-inventory':
            item=locked_pnpm.inventory(args.source,args.project)
            result={'status':'INCOMPLETE','operation':'not_applied','issues':[], 'warnings':item['limitations'], 'pnpm_inventory':item}
        elif args.command == 'pnpm-lock-cache':
            item=locked_pnpm.cache_tarballs(args.source,args.project,args.allow_registry_network,args.selected_platform)
            result={'status':'INCOMPLETE','operation':item['operation'],'issues':[], 'warnings':item['limitations'], 'pnpm_cache':item}
        elif args.command == 'pnpm-tree-prepare':
            item=pnpm_tree.prepare(args.source,args.project,args.output)
            result={'status':'INCOMPLETE','operation':item['operation'],'issues':[], 'warnings':item['limitations'], 'pnpm_tree':item}
        elif args.command == 'pnpm-tree-inspect':
            item=pnpm_tree.inspect(args.source,args.file,args.sha256)
            result={'status':'INCOMPLETE','operation':'not_applied','issues':[], 'warnings':['Проверка hash не доказывает происхождение или безопасность дерева.'], 'pnpm_tree':item}
        elif args.command == 'npm-lock-plan':
            item=locked_npm.plan(args.source,args.project)
            result={'status':'INCOMPLETE','operation':'not_applied','issues':[], 'warnings':item['limitations'], 'dependencies':item}
        elif args.command == 'npm-lock-prepare':
            item=locked_npm.prepare(args.source,args.project,args.output,args.allow_registry_network)
            result={'status':'INCOMPLETE','operation':item['operation'],'issues':[], 'warnings':item['limitations'], 'dependencies':item}
        elif args.command == 'npm-lock-inspect':
            item=locked_npm.inspect(args.source,args.file,args.sha256)
            result={'status':'INCOMPLETE','operation':'not_applied','issues':[], 'warnings':['Проверка относительной целостности не доказывает происхождение или безопасность зависимостей.'], 'dependency_inspect':item}
        elif args.command == 'reference-materialize':
            item=static_reference.materialize(args.source,args.selection,args.output)
            result={'status':'INCOMPLETE','operation':item['operation'],'issues':[], 'warnings':['Статическая копия не является изоляцией или проверенной приёмкой.'], 'reference':item}
        elif args.command == 'reference-inspect':
            item=static_reference.inspect(args.source,args.file,args.sha256)
            result={'status':'INCOMPLETE','operation':'not_applied','issues':[], 'warnings':['Статическая копия не является изоляцией или проверенной приёмкой.'], 'reference':item}
        elif args.command == 'run-seal':
            item=run_store.seal(args.source,args.site,args.audit,args.summary_sha256,args.output)
            result={'status':'INCOMPLETE','operation':item['operation'],'issues':[], 'warnings':['Хеш не доказывает происхождение и не разрешает публикацию.'], 'run_record':item}
        elif args.command == 'run-inspect':
            item=run_store.inspect(args.source,args.site,args.file,args.sha256)
            result={'status':'INCOMPLETE','operation':'not_applied','issues':[], 'warnings':['Запись не аутентифицирована и не разрешает публикацию.'], 'run_record':item}
        elif args.command == 'browser-audit-static-md':
            result=static_reference.audit(args.source,args.site,args.reference_record,args.reference_sha256,args.acknowledge_browser_code,args.output)
        elif args.command == 'browser-audit-md':
            result = audit_markdown.audit(args.source,args.site,args.reference_url,args.output)
        elif args.command == 'readiness':
            result=readiness.evaluate(args.source,args.site,args.run_record,args.run_sha256,args.manual_record,args.manual_sha256)
        elif args.command == 'coverage':
            result = coverage.diagnostic(args.source,args.site)
        elif args.command == 'template-tokens':
            item=templates.inspect_tokens(args.site,args.page,args.block,args.offset,args.limit)
            result={'status':'INCOMPLETE','operation':'not_applied','issues':[],
                    'warnings':['Текст и атрибуты могут содержать чувствительные данные; token не является HTML5-валидацией.'],
                    'template_tokens':item}
        elif args.command == 'materialize':
            item = delivery.materialize(args.source, args.site, args.selection, args.output,
                                        args.permission_profile, args.acknowledge_world_readable)
            warnings=['Delivery не проверен и не разрешён к публикации.']
            if args.permission_profile=='web-readable':
                warnings.append('Файлы могут быть доступны другим локальным пользователям; доступ web-сервера и безопасность содержимого не проверены.')
            result = {'status':'INCOMPLETE', 'operation':item['operation'], 'issues':[], 'warnings':warnings, 'delivery':item}
        elif args.command == 'queue-md':
            if args.md_command == 'template':
                item = queue_md.write_template(args.source, args.output)
                result = {'status':'INCOMPLETE', 'operation':item['operation'], 'artifacts':[item], 'issues':[], 'warnings':[], 'next':'Заполните предложение, проверьте и явно зафиксируйте.'}
            elif args.md_command == 'validate':
                item = queue_md.validate_file(args.source, args.file)
                result = {'status':'INCOMPLETE', 'operation':'not_applied', 'issues':[], 'warnings':item.pop('warnings'), 'queue':item, 'next':'Валидность формата не является приёмкой сайта.'}
            elif args.md_command == 'migrate-dry-run':
                item = migrate_queue.create_plan(args.source, args.output)
                result = {'status':'INCOMPLETE','operation':item['operation'],'issues':[], 'warnings':item['warnings'], 'migration_plan':item}
            elif args.md_command == 'migrate-apply':
                item = migrate_queue.apply(args.source, args.plan, args.expected_manifest_sha256, args.expected_markdown_sha256, args.acknowledge_offline_writers)
                result = {'status':'INCOMPLETE','issues':[], 'warnings':['Проверки v1 не являются evidence v2; нужно разобрать архив.'], 'migration':item, 'operation':item['operation']}
            elif args.md_command == 'migration-inspect':
                item = migrate_queue.inspect(args.source, args.id)
                result = {'status':'INCOMPLETE','operation':'not_applied','issues':[], 'warnings':[], 'migration':item}
            elif args.md_command == 'recover-commit':
                item=queue_md.recover_commit(args.source,args.history,'absent' if args.expect_absent else args.expected_sha256,args.acknowledge_offline_writers)
                result={'status':'INCOMPLETE','operation':item['operation'],'issues':[], 'warnings':[], 'recovery':item}
            elif args.md_command == 'migration-recover':
                item = migrate_queue.recover(args.source, args.id, args.acknowledge_offline_writers, args.clear_stale_lock)
                result = {'status':'INCOMPLETE','operation':item['operation'],'issues':[], 'warnings':[], 'migration':item}
            elif args.md_command == 'inspect-legacy':
                item = queue_md.inspect_legacy(args.source)
                result = {'status':'INCOMPLETE', 'operation':'not_applied', 'issues':[], 'warnings':['Legacy-данные и свободные заметки не классифицированы; перед apply необходимы dry-run и проверка.'], 'legacy':item}
            else:
                item = queue_md.commit(args.source, args.file, 'absent' if args.expect_absent else args.expected_sha256, args.reason)
                result = {'status':'INCOMPLETE', 'issues':[], 'next':'Очередь зафиксирована; evidence и публикация не включены.', **item}
        elif args.command == 'discover':
            workspace(args.source)
            if args.offset < 0 or not 1 <= args.limit <= 500:
                raise ValueError('offset должен быть >= 0, limit — от 1 до 500')
            found = scan_facts(Path(args.source), include_text=args.include_source_text, file_filter=args.file)
            total = len(found['facts'])
            result = {'status': 'INCOMPLETE', 'issues': [], 'warnings': found['warnings'],
                      'source_snapshot': found['source_snapshot'], 'snapshot_version': 2,
                      'facts_total': total, 'offset': args.offset, 'limit': args.limit,
                      'facts': found['facts'][args.offset:args.offset+args.limit],
                      'excluded': found['excluded'], 'text_included':found['text_included'], 'file_filter':found['file_filter'],
                      'next': 'Факты не являются страницами. Агент исследует источник и принимает решения; manifest не изменялся.'}
        elif args.command in ('queue','queue-update'):
            work=workspace(args.source); path=work/'manifest.json'; expected=hashlib.sha256(path.read_bytes()).hexdigest(); data=load(path)
            current=analyze(Path(args.source))
            stale=current.get('fingerprint') != data['source'].get('fingerprint')
            if args.command=='queue-update':
                if stale: raise ValueError('Исходник изменился; сначала вручную пересмотреть и обновить очередь')
                if args.page:
                    page=next((p for p in data['pages'] if p['id']==args.page),None)
                    if page is None: raise ValueError('Страница не найдена')
                    if args.work_status: page['work_status']=args.work_status
                    if args.confirm_page: page['confirmation']='confirmed'
                elif args.work_status or args.confirm_page: raise ValueError('Укажите --page')
                if args.resolve_link:
                    if not args.resolution or not args.reason or not args.reason.strip(): raise ValueError('Для решения ссылки нужны --resolution и --reason')
                    links=[x for x in data['unresolved_links'] if x.get('reference_route')==args.resolve_link]
                    if not links: raise ValueError('Неясная ссылка не найдена')
                    for link in links: link.update({'resolution':args.resolution,'resolution_reason':args.reason.strip()})
                elif args.resolution: raise ValueError('Укажите --resolve-link')
                if args.confirm_discovery:
                    if not args.reason or not args.reason.strip(): raise ValueError('Подтверждение требует --reason с основанием')
                    if data['discovery'].get('unresolved'):
                        raise ValueError('Неопределённости v1 не классифицированы; подтверждение требует миграции и разбора записей')
                    data['discovery']['status']='confirmed'; data['discovery']['confirmation_reason']=args.reason.strip()
                data=stale_checks(data,Path(args.source))
                mutation_started = True
                save(path,data,expected_hash=expected)
                expected=hashlib.sha256(path.read_bytes()).hexdigest()
            else:
                data=stale_checks(data,Path(args.source))
            result={'status':'INCOMPLETE','issues':[], 'warnings':(['Исходник изменился; очередь и проверки требуют пересмотра'] if stale else []) + data['discovery'].get('unresolved', []), 'discovery':data['discovery']['status'], 'manifest_sha256':expected, 'operation':'applied' if args.command == 'queue-update' else 'not_applied', 'pages':data['pages'], 'unresolved_links':data['unresolved_links'], 'next':'Проверить все страницы и состояния; очередь не является приёмкой.'}
        elif args.command == 'record-check':
            result=record(args.source,args.site,args.page,args.kind,args.status,args.evidence)
        elif args.command == 'publish-plan':
            item = publication.plan(args.source,args.delivery_record,args.target,args.run_record,args.run_sha256,args.manual_record,args.manual_sha256)
            result = {'status':'INCOMPLETE','operation':'not_applied','issues':[], 'warnings':item['warnings'], 'plan':item}
        elif args.command == 'publish-apply':
            item=publication.apply(args.source,args.plan,args.sha256,args.acknowledge_offline_writers)
            result={'status':'INCOMPLETE','operation':item['operation'],'issues':[], 'warnings':['Поставка не прошла полную постпроверку.'], 'publication':item}
        elif args.command == 'publication-inspect':
            item=publication.inspect(args.source,args.id)
            result={'status':'INCOMPLETE','operation':'not_applied','issues':[], 'warnings':item['limitations'], 'publication':item}
        elif args.command == 'publication-restore':
            item=publication.restore(args.source,args.id,'absent' if args.expect_target_absent else args.expected_target_sha256,args.acknowledge_offline_writers,args.clear_stale_lock)
            result={'status':'INCOMPLETE','operation':item['operation'],'issues':[], 'warnings':item['limitations'], 'publication':item}
        elif args.command == 'publish':
            result=publish(args.source,args.site,replace=args.replace_existing)
        elif args.command == 'check':
            result=check_manifest(Path(args.site),load(args.manifest)) if args.manifest else check_site(Path(args.site))
        elif args.command == 'browser-audit':
            if args.route is not None and (args.reference_route is not None or args.candidate_route is not None): raise ValueError('--route несовместим с парными маршрутами')
            if (args.reference_route is None) != (args.candidate_route is None): raise ValueError('Укажите оба парных маршрута')
            work=workspace(args.source)
            scenarios=load_scenarios(Path(args.scenario) if args.scenario else None)
            output=Path(args.output) if args.output else work/'audits'/uuid.uuid4().hex
            if args.output and output.resolve().is_relative_to(Path('.work').resolve()): work=Path('.work')
            result=run_audit(Path(args.source),Path(args.site),output,scenarios,args.route or '/',args.threshold,Path(args.font_css) if args.font_css else None,args.trust_source,args.reference_url,args.candidate_url,args.channel_tolerance,args.reference_route,args.candidate_route,work)
            result['artifact_directory']=str(output)
        elif args.command == 'browser-audit-site':
            work=workspace(args.source); data=load(args.manifest or work/'manifest.json')
            preflight=analyze(Path(args.source))
            if preflight.get('fingerprint') != data['source'].get('fingerprint'): raise ValueError('Fingerprint источника отличается от манифеста; очередь устарела')
            pages=[p for p in data['pages'] if p['confirmation']=='confirmed']
            if not pages or data['discovery']['status']!='confirmed': raise ValueError('Очередь не подтверждена')
            out=Path(args.output or work/'audits'/uuid.uuid4().hex)
            resolved=out.resolve(); root=work.resolve()
            if not resolved.is_relative_to(root) or resolved==root or out.is_symlink() or (out.exists() and (not out.is_dir() or any(out.iterdir()))): raise ValueError('Каталог отчёта должен быть новым и внутри source/.work')
            out.mkdir(parents=True,exist_ok=True)
            site=Path(args.site).absolute(); before=fingerprint(site) if site.is_dir() else None
            results=[]
            binding='external-unverified' if args.candidate_url else 'managed-static'
            with (contextlib.nullcontext(args.candidate_url) if args.candidate_url else serve_site(site)) as candidate_url:
                for page in pages:
                    missing_states=[s.get('id') for s in page.get('states',[]) if s.get('required') and not s.get('scenario')]
                    scenario_paths={s.get('scenario') for s in page.get('states',[]) if s.get('scenario')}
                    if len(scenario_paths)>1: r={'status':'BLOCKED','issues':['Укажите один JSON-файл сценариев для страницы'], 'warnings':[]}
                    elif scenario_paths:
                        sp=work/next(iter(scenario_paths))
                        if not sp.resolve().is_relative_to(work.resolve()) or sp.is_symlink(): r={'status':'BLOCKED','issues':['Недопустимый сценарий'], 'warnings':[]}
                        else:
                            try:
                                actions=load_scenarios(sp)
                                available={a['name'] for a in actions}
                                missing_states.extend(s['id'] for s in page.get('states',[]) if s.get('required') and s.get('scenario') and s['id'] not in available)
                                r=run_audit(Path(args.source),site,out/page['id'],actions,'/',0.001,None,False,args.reference_url,candidate_url,12,page['reference_route'],'/'+page['output'],work)
                            except (ValueError,OSError) as e: r={'status':'BLOCKED','issues':[str(e)],'warnings':[]}
                    else: r=run_audit(Path(args.source),site,out/page['id'],[],'/',0.001,None,False,args.reference_url,candidate_url,12,page['reference_route'],'/'+page['output'],work)
                    if missing_states: r.setdefault('warnings',[]).append('Нет сценариев обязательных состояний: '+', '.join(str(x) for x in missing_states))
                    results.append({'id':page['id'],'result':r})
            statuses=[x['result']['status'] for x in results]
            status='BLOCKED' if 'BLOCKED' in statuses else 'FAIL' if 'FAIL' in statuses else 'INCOMPLETE'
            changed = before is None or fingerprint(site)!=before or analyze(Path(args.source)).get('fingerprint') != preflight.get('fingerprint')
            if changed: status='BLOCKED'
            result={'status':status,'issues':['Источник или сайт отсутствует либо изменился во время проверки'] if changed else [], 'warnings':[], 'pages':results, 'pages_planned':len(pages), 'pages_checked':sum(1 for x in results if x['result']['status'] not in ('BLOCKED',)), 'pages_blocked':sum(1 for x in results if x['result']['status']=='BLOCKED'), 'pages_failed':sum(1 for x in results if x['result']['status']=='FAIL'), 'source_fingerprint':preflight.get('fingerprint'), 'site_fingerprint':before, 'candidate_binding':binding, 'artifact_directory':str(out), 'next':'Проверить предупреждения и ручные состояния; пакетный аудит не является полной приёмкой.'}
            (out/'summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
        else:
            actions=None
            if args.scenario:
                actions=json.loads(Path(args.scenario).read_text(encoding='utf8'))
                if not isinstance(actions,list): raise ValueError('сценарий должен быть массивом')
            work=workspace(args.source); output=Path(args.output) if args.output else work/'compare'/uuid.uuid4().hex
            if args.output and output.resolve().is_relative_to(Path('.work').resolve()): work=Path('.work')
            result=compare(args.reference,args.candidate,args.width,args.height,output,args.threshold,actions,work)
    except (MutationUncertainError, queue_md.CommitUncertain, delivery.DeliveryUncertain, migrate_queue.MigrationUncertain, publication.PublicationUncertain, audit_markdown.AuditUncertain, run_store.RunRecordUncertain, manual_evidence.ManualRecordUncertain, static_reference.ReferenceUncertain, locked_npm.DependenciesUncertain) as e:
        result={'status':'ERROR','operation':'unknown','issues':[str(e)],'warnings':[]}
    except (ValueError, OSError, UnicodeError, KeyError, TypeError) as e:
        result={'status':'ERROR' if mutation_started else 'BLOCKED', 'operation':'unknown' if mutation_started else 'not_applied', 'issues':[str(e)],'warnings':[]}
    except Exception as e:
        # Unexpected failures are not evidence that no side effect occurred.
        result={'status':'ERROR', 'operation':'unknown', 'issues':[f'Непредвиденная ошибка: {e}'], 'warnings':[]}
    result={'schema_version':1, 'command':args.command, 'operation':'not_applied',
            'execution':'blocked' if result['status']=='BLOCKED' else 'error' if result['status']=='ERROR' else 'completed',
            'outcome':result['status'].lower(), 'coverage':None, 'freshness':None,
            'issues':[], 'warnings':[], 'artifacts':[], 'next':None, **result}
    if report_fd is not None:
        # operation describes the command; report_operation describes this extra
        # file. A report does not convert a read-only command into a mutation.
        # A file cannot attest to its own successful fsync. Only stdout, after
        # syncing, reports the outcome of writing this file.
        try:
            text=json.dumps(result,ensure_ascii=False,indent=2)
            report=os.fdopen(report_fd, 'w', encoding='utf8'); report_fd=None
            with report:
                report.write(text + '\n')
                report.flush()
                os.fsync(report.fileno())
            directory=path.parent
            while True:
                queue_md._sync_dir(directory)
                if directory==root.parent: break
                directory=directory.parent
        except Exception as e:
            if report_fd is not None:
                try: os.close(report_fd)
                except OSError: pass
            failure = {'schema_version': 1, 'command': args.command, 'status': 'ERROR',
                       'operation': 'unknown', 'report_operation':'unknown', 'issues': [f'Ошибка записи отчёта: {e}'],
                       'command_result': result}
            try: failure_text=json.dumps(failure,ensure_ascii=False)
            except (TypeError,ValueError,UnicodeError):
                failure['command_result']={'status':result.get('status'),'operation':result.get('operation')}
                failure['issues'].append('Полный результат не сериализуется; сохранены только статус и operation')
                failure_text=json.dumps(failure,ensure_ascii=True,default=str)
            print(failure_text if args.json else
                  f'ERROR: report_operation=unknown; результат команды: {result.get("status")}, operation={result.get("operation")}: {e}')
            return 4
        result={**result,'report_operation':'applied'}
    text=json.dumps(result,ensure_ascii=False,indent=2)
    if args.json: print(text)
    else:
        print(f"{result['status']}: {args.command}")
        if args.report: print(f'  Отчёт: {path}; report_operation=applied')
        for issue in result.get('issues',[])+result.get('mismatches',[]): print(f'  - {issue}')
        brief=brief_report(result)
        for warning in brief['warnings']: print(f'  WARN: {warning}')
        if result.get('coverage'):
            cv=result['coverage']
            if 'states_planned' in cv: print(f"  Состояний: {cv['states_checked']}/{cv['states_planned']}; экранов: {cv['screens_compared']}")
            if 'pages_expected' in cv: print(f"  Страниц: {cv['pages_present']}/{cv['pages_expected']}; отсутствуют: {', '.join(cv['pages_missing'])}")
        if args.command == 'queue-md':
            if result.get('queue'):
                qmd=result['queue']; print(f"  SHA256: {qmd['sha256']}  requirements: {qmd['requirements_hash']}  freshness: {qmd['freshness']}")
            if result.get('legacy'):
                legacy=result['legacy']; print(f"  Состав v1: {legacy['counts']}; Markdown совпадает: {legacy['markdown_matches_render']}")
                if legacy['markdown_diff']: print(legacy['markdown_diff'])
            if result.get('migration_plan'):
                mp=result['migration_plan']; print(f"  План: {mp['plan']}  Состав: {mp['counts']}")
                print(mp['proposal_diff'])
            if result.get('diff'): print(result['diff'])
        if args.command == 'materialize' and result.get('delivery'):
            item=result['delivery']; print(f"  Delivery: {item['delivery']}  SHA256: {item['delivery_snapshot']}  Исключено: {len(item['excluded'])}")
        if args.command == 'publish-plan' and result.get('plan'):
            item=result['plan']; print(f"  Изменения: {item['diff']}\n  Применение разрешено: {item['apply_allowed']}")
            print(f"  Проверка среды (только подсказка): {item['permissions']}")
            print(f"  Метаданные delivery: {item['delivery_metadata']}  цели: {item['target_metadata']}")
            for approval in item['required_approvals']: print(f'  APPROVAL: {approval}')
            for blocker in item['blockers']: print(f'  BLOCKER: {blocker}')
        if args.command in ('publication-inspect','publication-restore','publish-apply') and result.get('publication'):
            item=result['publication']
            print(f"  Публикация: {item['publication_id']}  операция: {item['operation']}")
            if 'journal' in item and isinstance(item['journal'],dict):
                print(f"  Фаза: {item['journal']['phase']}  цель: {item['target_state']}  hash: {item['target_snapshot'] or 'absent'}")
                print(f"  Backup: {item['backup_snapshot'] or 'absent'}  корректен: {item['backup_valid']}")
                print(f"  Копия восстановления: {item['restore_copy_snapshot'] or 'absent'}  корректна: {item['restore_copy_valid']}")
                print(f"  Метаданные: цель={item['target_metadata']}  backup={item['backup_metadata']}  политика записана={item['metadata_policy_recorded']}")
            elif item.get('status'): print(f"  Состояние: {item['status']}")
        if args.command == 'runner-synthetic' and result.get('fixture'):
            item=result['fixture']; print(f"  Синтетический запуск: {item['outcome']}; код: {item['returncode']}; вывод: {item['output_bytes']} байт")
            if item['missing_markers']: print(f"  Отсутствуют маркеры: {', '.join(item['missing_markers'])}")
            print(item['log_tail'])
        if args.command == 'runner-profiles':
            runner=result['runner']; probe=runner['resource_controls']
            for name,profile in runner['profiles'].items():
                print(f"  {name}: {'available' if profile['available'] else 'blocked'} — {profile['reason']}")
            print(f"  cgroup: {probe['status']}; writable hint={probe.get('directory_write_hint')}; delegation_verified={probe['delegation_verified']}; disk_quota={probe['disk_quota']}")
            if probe.get('reason'): print(f"  cgroup: {probe['reason']}")
        if args.command == 'readiness':
            for blocker in result.get('blockers',[]): print(f'  BLOCKER: {blocker}')
            if result.get('coverage'): print(f"  Обязательных проверок без подтверждения: {result['coverage']['required_unconfirmed']}/{result['coverage']['required']}")
        if args.command == 'template-tokens' and result.get('template_tokens'):
            item=result['template_tokens']
            print(f"  Страница: {item['page']}  блок: {item['block']}  delivery snapshot: {item['site_snapshot']}")
            for side in ('template','candidate'):
                print(f"  {side}: {item[side]['total']} tokens")
                for row in item[side]['items']:
                    print(f"    {row['index']}: {json.dumps(row['token'],ensure_ascii=False)} (replaceable={row['replaceable']})")
        if args.command in ('coverage','browser-audit-md','browser-audit-static-md') and result.get('coverage'):
            cv=result['coverage']; print(f"  Покрытие: выполнено {cv['executed']}/{cv['planned']}; это не приёмка")
        if args.command == 'pnpm-lock-inventory' and result.get('pnpm_inventory'):
            item=result['pnpm_inventory']; print(f"  Пакетов: {item['packages']}; snapshots: {item['snapshots']}; reachable: {item['reachable_snapshots']}")
        if args.command == 'pnpm-lock-cache' and result.get('pnpm_cache'):
            item=result['pnpm_cache']; print(f"  Пакетов: {item['packages_checked']}; загружено: {item['archives_fetched']}; проверено в кэше: {item['archives_reused']}")
        if args.command in ('pnpm-tree-prepare','pnpm-tree-inspect') and result.get('pnpm_tree'):
            item=result['pnpm_tree']; print(f"  Дерево: {item['dependencies']}; свежесть: {item.get('freshness','не проверена')}")
            if item.get('sha256'): print(f"  Запись: {item['record']} SHA256: {item['sha256']}")
        if args.command in ('npm-lock-plan','npm-lock-prepare') and result.get('dependencies'):
            item=result['dependencies']; print(f"  Пакетов: {len(item['packages']) if isinstance(item['packages'],list) else item['packages']}; scripts не выполнялись")
            if item.get('record'): print(f"  Запись: {item['record']}  SHA256: {item['sha256']}")
        if args.command == 'npm-lock-inspect' and result.get('dependency_inspect'):
            item=result['dependency_inspect']; print(f"  Свежесть: {item['freshness']}; изменено: {', '.join(item['changed']) or 'нет'}")
        if args.command in ('reference-materialize','reference-inspect') and result.get('reference'):
            item=result['reference']; print(f"  Копия: {item['reference']}  запись: {item.get('record',item.get('path'))}  SHA256: {item['sha256']}")
            if 'freshness' in item: print(f"  Актуальность: {item['freshness']}  изменения: {item['changed']}")
        if args.command in ('run-seal','run-inspect') and result.get('run_record'):
            item=result['run_record']; print(f"  Запись: {item['path']}  SHA256: {item['sha256']}")
            if 'freshness' in item: print(f"  Актуальность: {item['freshness']}  изменения: {item['changed']}")
        if args.command == 'discover':
            print(f"  Фактов: {result.get('facts_total', 0)}; показано: {len(result.get('facts', []))}")
            for fact in result.get('facts', [])[:15]:
                print(f"  {fact['file']}:{fact['line']} [{fact['kind']}] {fact.get('text', fact.get('value', ''))[:160]}")
        if args.command in ('queue', 'queue-update'):
            for page in result.get('pages', []):
                print(f"  {page['id']}: {page['reference_route']} → {page['output']} [{page['work_status']}, {page['confirmation']}]")
        if result.get('coverage') and 'states_planned' in result['coverage']:
            for item in brief['notable']:
                size='x'.join(map(str,item['viewport']))
                if 'issue' in item: print(f"  {size}/{item['state']}: {item['issue']}")
                else: print(f"  {size}/{item['state']}: {item['status']} {item['difference_ratio']:.2%}, карта {item['heatmap']}")
        if result.get('pages_planned') is not None:
            for page in result['pages']: print(f"  {page['id']}: {page['result']['status']}")
        if result.get('artifact_directory'): print(f"Артефакты: {result['artifact_directory']}")
        if result.get('next'): print(result['next'])
    return {'INCOMPLETE':2,'BLOCKED':3,'FAIL':1,'PASS':0,'ERROR':4}[result['status']]


if __name__=='__main__': raise SystemExit(main())
