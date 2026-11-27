"""Read-only inventory for a restricted pnpm lockfile v9.

No package manager, project code, dependency installation or network is used.
This is not pnpm's resolver and must never be used to authorize execution.
"""
from __future__ import annotations

import re
from pathlib import Path

from . import locked_npm, queue_md as md
from .snapshot import take_snapshot

MAX_LOCK = 4_000_000
MAX_NODES = 100_000
MAX_DEPTH = 50
MAX_PACKAGES = 5000
SEMVER = r'(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)(?:-[A-Za-z0-9.-]+)?(?:\+[A-Za-z0-9.-]+)?'
ID = re.compile(r'^('+locked_npm.NAME+r')@('+SEMVER+r')$')
PEER = re.compile(r'^\([A-Za-z0-9@/._+()\-]+\)$')


def _parse_yaml(raw):
    try:
        import yaml
    except ImportError as exc:
        raise ValueError('Для статического pnpm inventory требуется PyYAML из tools/requirements.txt') from exc

    class StrictLoader(yaml.SafeLoader):
        def __init__(self, text):
            super().__init__(text)
            self.nodes_seen=0
            self.depth=0

        def compose_node(self, parent, index):
            event=self.peek_event()
            if isinstance(event,yaml.events.AliasEvent) or getattr(event,'anchor',None) is not None:
                raise ValueError('YAML anchors и aliases не поддерживаются')
            self.nodes_seen+=1
            self.depth+=1
            try:
                if self.nodes_seen>MAX_NODES or self.depth>MAX_DEPTH:
                    raise ValueError('Превышен лимит структуры YAML')
                node=super().compose_node(parent,index)
                if isinstance(node,yaml.ScalarNode) and len(node.value)>4096:
                    raise ValueError('Слишком длинный YAML scalar')
                return node
            finally:
                self.depth-=1

        def construct_mapping(self, node, deep=False):
            if not isinstance(node,yaml.MappingNode): raise ValueError('Ожидался YAML mapping')
            result={}
            for key_node,value_node in node.value:
                key=self.construct_object(key_node,deep=deep)
                if not isinstance(key,str) or key=='<<': raise ValueError('Ключи YAML должны быть уникальными строками')
                if key in result: raise ValueError('Повторный ключ YAML')
                result[key]=self.construct_object(value_node,deep=deep)
            return result

    try:
        text=raw.decode('utf8')
        parsed=yaml.load(text,Loader=StrictLoader)
    except (UnicodeError, yaml.YAMLError, RecursionError) as exc:
        raise ValueError('Некорректный pnpm YAML') from exc
    if not isinstance(parsed,dict): raise ValueError('pnpm lock должен быть объектом')
    return parsed


def _identity(value, *, peer_allowed):
    if not isinstance(value,str) or len(value)>1024: raise ValueError('Некорректный идентификатор версии pnpm')
    base,sep,rest=value.partition('(')
    match=ID.fullmatch(base)
    if not match: raise ValueError('Поддерживаются только registry имена с точными semver версиями')
    if sep:
        suffix='('+rest
        if not peer_allowed or not PEER.fullmatch(suffix): raise ValueError('Неизвестный формат peer-контекста pnpm')
        depth=0
        for ch in suffix:
            if ch=='(': depth+=1
            elif ch==')':
                depth-=1
                if depth<0: raise ValueError('Некорректный peer-контекст pnpm')
            if depth>16: raise ValueError('Слишком глубокий peer-контекст pnpm')
        if depth: raise ValueError('Некорректный peer-контекст pnpm')
    return match.group(1),match.group(2),base


def _mapping(value, label):
    if not isinstance(value,dict): raise ValueError(f'{label}: ожидался объект')
    return value


def _inventory(source, project='.'):
    source=Path(source).absolute()
    md._path(source/'.work',source/'.work'/'_probe',existing=False)
    if project=='.': root=source
    elif isinstance(project,str) and md._relpath(project): root=md._path(source,source/project)
    else: raise ValueError('Недопустимый путь pnpm project')
    if not root.is_dir(): raise ValueError('pnpm project не найден')
    before=take_snapshot(source,'source'); entries={e['path']:e for e in before['entries']}
    def read(name):
        path=md._path(source,root/name)
        key=path.relative_to(source).as_posix()
        if key not in entries or entries[key]['type']!='file': raise ValueError('Файл не входит в source snapshot')
        raw=md._safe_read(path,MAX_LOCK)
        if md.sha(raw)!=entries[key]['sha256']: raise ValueError('Файл изменился при чтении')
        return raw
    package_raw=read('package.json'); lock_raw=read('pnpm-lock.yaml')
    package=locked_npm._json(package_raw,'package.json'); lock=_parse_yaml(lock_raw)
    if lock.get('lockfileVersion')!='9.0': raise ValueError('Поддерживается только pnpm lockfile v9.0')
    if set(lock)-{'lockfileVersion','settings','importers','packages','snapshots'}:
        raise ValueError('Неизвестные функции lockfile; inventory ограничен обычным реестром без patch/catalog/override')
    importers=_mapping(lock.get('importers'),'importers')
    if set(importers)!={'.'}: raise ValueError('Workspaces и дополнительные importers не поддерживаются')
    importer=_mapping(importers['.'],'importer')
    if set(importer)-{'dependencies','devDependencies','optionalDependencies'}:
        raise ValueError('Неизвестные поля importer')
    packages=_mapping(lock.get('packages'),'packages'); snapshots=_mapping(lock.get('snapshots'),'snapshots')
    if not packages or not snapshots or len(packages)>MAX_PACKAGES or len(snapshots)>MAX_PACKAGES:
        raise ValueError('Неизвестный размер packages/snapshots')
    metadata={}
    for key,item in packages.items():
        name,version,base=_identity(key,peer_allowed=False); item=_mapping(item,'package metadata')
        resolution=_mapping(item.get('resolution'),'resolution')
        if set(resolution)!={'integrity'}: raise ValueError('Поддерживается только registry resolution с integrity')
        digest=locked_npm._sha512(resolution['integrity'])
        metadata[base]={'name':name,'version':version,'sha512':digest,
                        'os':item.get('os'), 'cpu':item.get('cpu'), 'libc':item.get('libc')}
        for field in ('os','cpu','libc'):
            if item.get(field) is not None: locked_npm._compatible(item[field], 'linux' if field=='os' else 'x64' if field=='cpu' else 'glibc')
    graph={}; optional={}; edge_counts={'dependencies':0,'optionalDependencies':0}
    for key,item in snapshots.items():
        _,_,base=_identity(key,peer_allowed=True)
        if base not in metadata: raise ValueError('Для snapshot нет package metadata')
        item=_mapping(item,'snapshot')
        if set(item)-{'dependencies','optionalDependencies','optional','transitivePeerDependencies'}:
            raise ValueError('Неизвестные поля snapshot pnpm')
        if 'optional' in item and type(item['optional']) is not bool: raise ValueError('Некорректное поле optional')
        edges=[]
        for kind in edge_counts:
            dependencies=_mapping(item.get(kind,{}),kind)
            for name,version in dependencies.items():
                target=name+'@'+version if isinstance(version,str) else ''
                _identity(target,peer_allowed=True)
                edges.append((target,kind)); edge_counts[kind]+=1
        graph[key]=edges; optional[key]=item.get('optional',False)
    roots=[]; root_details=[]; root_counts={}
    for kind in ('dependencies','devDependencies','optionalDependencies'):
        declared=_mapping(package.get(kind,{}),kind)
        locked=_mapping(importer.get(kind,{}),kind)
        if set(declared)!=set(locked): raise ValueError(f'package.json и pnpm importer различаются: {kind}')
        root_counts[kind]=len(locked)
        for name,fields in locked.items():
            fields=_mapping(fields,'importer dependency')
            if set(fields)!={'specifier','version'} or fields['specifier']!=declared[name] or not isinstance(fields['version'],str):
                raise ValueError('Specifier package.json и pnpm lock не совпадают')
            target=name+'@'+fields['version']; _identity(target,peer_allowed=True)
            roots.append(target); root_details.append((target,kind))
    for key in roots:
        if key not in graph: raise ValueError('Отсутствует snapshot импортируемого пакета')
    for edges in graph.values():
        for target,_ in edges:
            if target not in graph: raise ValueError('Зависимость snapshot отсутствует в lock')
    reachable=set(); todo=list(roots)
    while todo:
        key=todo.pop()
        if key in reachable: continue
        reachable.add(key); todo.extend(target for target,_ in graph[key])
    if take_snapshot(source,'source')['digest']!=before['digest']:
        raise ValueError('Source изменился при чтении pnpm lock')
    result={'version':1,'kind':'pnpm-lock-inventory','project':str(root),'source_snapshot':before['digest'],
            'package_sha256':md.sha(package_raw),'lock_sha256':md.sha(lock_raw),'lockfile_version':'9.0',
            'packages':len(metadata),'snapshots':len(graph),'reachable_snapshots':len(reachable),
            'unreachable_snapshots':len(graph)-len(reachable),'root_dependencies':root_counts,'edges':edge_counts,
            'optional_snapshots':sum(optional.values()), 'executed_project':False,'installed_dependencies':False,
            'network_access':False,'isolated':False,'publication_eligible':False,
            'limitations':['Это статическая ограниченная проверка структуры, не pnpm resolver и не frozen install.',
                           'Не проверяются удовлетворение semver, peers, overrides, platform/libc, scripts и содержимое registry.',
                           'Зависимости не подготовлены; изоляция и происхождение не подтверждены.']}
    return result,metadata,graph,root_details


def inventory(source, project='.'):
    return _inventory(source,project)[0]


def cache_tarballs(source, project='.', allow_network=False, selected_platform=False):
    """Populate a verified content cache, never a pnpm installation.

    By default all metadata packages are included; the optional platform filter
    is conservative and uses the same selection rules as the tree experiment.
    """
    import hashlib
    import urllib.parse

    source=Path(source).absolute(); work=source/'.work'
    current,metadata,graph,roots=_inventory(source,project)
    if selected_platform:
        from . import pnpm_tree
        chosen,_=pnpm_tree._select(metadata,graph,roots)
        bases={_identity(key,peer_allowed=True)[2] for key in chosen}
        metadata={key:value for key,value in metadata.items() if key in bases}
    cache=md._path(work,work/'npm-tar-cache',existing=False)
    touched=False; downloaded=0; fetched=0; reused=0
    try:
        for item in metadata.values():
            path=md._path(work,cache/(item['sha512']+'.tgz'),existing=False)
            if path.exists():
                raw=md._safe_read(path,locked_npm.MAX_TARBALL); reused+=1
            else:
                if not allow_network: raise ValueError('Не все tarballs есть в кэше; сеть требует явного разрешения')
                # The lock inventory accepts only registry semver identities;
                # URLs are derived, never taken from untrusted YAML strings.
                package=urllib.parse.quote(item['name'],safe='@/')
                stem=urllib.parse.quote(item['name'].rsplit('/',1)[-1],safe='')
                version=urllib.parse.quote(item['version'],safe='')
                url=f'https://registry.npmjs.org/{package}/-/{stem}-{version}.tgz'
                try: raw=locked_npm._download(url,locked_npm.MAX_TARBALL)
                except (OSError,ValueError) as exc: raise ValueError('Не удалось загрузить tarball из разрешённого registry') from exc
                downloaded+=len(raw)
                if downloaded>locked_npm.MAX_TOTAL_DOWNLOAD: raise ValueError('Превышен лимит загрузки')
                if hashlib.sha512(raw).hexdigest()!=item['sha512']: raise ValueError('Integrity загруженного tarball не совпадает')
                touched=True; cache.mkdir(exist_ok=True)
                try: md._write_new(path,raw); md._sync_dir(cache)
                except FileExistsError:
                    if md._safe_read(path,locked_npm.MAX_TARBALL)!=raw: raise ValueError('Кэш изменён параллельно')
                fetched+=1
            if hashlib.sha512(raw).hexdigest()!=item['sha512']: raise ValueError('Integrity tarball в кэше не совпадает')
        if inventory(source,project)!=current: raise ValueError('Source или lock изменились при подготовке кэша')
        return {'operation':'applied' if touched else 'not_applied','source_snapshot':current['source_snapshot'],
                'lock_sha256':current['lock_sha256'],'cache':str(cache),'packages_checked':len(metadata),
                'archives_fetched':fetched,'archives_reused':reused,'bytes_downloaded':downloaded,
                'network_requested':allow_network,'selected_platform':selected_platform,
                'executed_project':False,'installed_dependencies':False,
                'isolated':False,'publication_eligible':False,
                'limitations':[('Выбраны только совместимые достижимые пакеты для Linux x64 glibc; это не полная семантика pnpm.' if selected_platform else 'Кэш включает все пакеты lock, в том числе несовместимые и необязательные.'),
                               'Архивы проверены только относительно integrity lock; это не установка pnpm и не проверка доверия.',
                               'Структура node_modules, peer resolution, native bindings и lifecycle-скрипты не подготовлены.']}
    except Exception as exc:
        if touched:
            raise locked_npm.DependenciesUncertain(f'Кэш мог быть частично обновлён: {cache}: {exc}') from exc
        raise
