"""Run viewport audits against pre-existing, safely isolated local URLs.

This module does not provide an OS sandbox or run the exported application.
"""
from __future__ import annotations
import json
import re
import shutil
from pathlib import Path

from .screen_audit import audit_urls


def package_install(project: Path):
    """Choose a locked package-manager command, without shell or lifecycle scripts."""
    pkg = json.loads((project / 'package.json').read_text(encoding='utf8'))
    deps = {**pkg.get('dependencies', {}), **pkg.get('devDependencies', {})}
    if 'vite' not in deps or not re.fullmatch(r'vite(?:\s+--(?:host|port|strictPort|open)(?:[=\s][\w.-]+)?)*', pkg.get('scripts', {}).get('dev', '')):
        raise ValueError('Поддерживается только Vite со стандартным скриптом dev; произвольные скрипты не запускаются')
    pnpm, npm = (project/'pnpm-lock.yaml').is_file(), (project/'package-lock.json').is_file()
    if pnpm == npm: raise ValueError('Нужен ровно один pnpm-lock.yaml или package-lock.json')
    if npm: return ['npm', 'ci', '--ignore-scripts', '--no-audit', '--no-fund']
    if shutil.which('pnpm'): return ['pnpm', 'install', '--frozen-lockfile', '--ignore-scripts']
    version = ''
    manager = pkg.get('packageManager', '')
    if isinstance(manager, str) and re.fullmatch(r'pnpm@\d+\.\d+\.\d+', manager): version = manager[5:]
    mise = project / '.mise.toml'
    if not version and mise.is_file():
        match = re.search(r'^\s*"npm:pnpm"\s*=\s*"(\d+\.\d+\.\d+)"', mise.read_text(encoding='utf8'), re.M)
        if match: version = match.group(1)
    if not version: raise ValueError('Установите pnpm или укажите его точную версию в packageManager/.mise.toml')
    return ['npx', '--yes', f'pnpm@{version}', 'install', '--frozen-lockfile', '--ignore-scripts']


def brief_report(data):
    """Bounded, agent-friendly summary; full state and artifacts remain in summary.json."""
    notable = []
    for viewport in data.get('viewports', []):
        for state in viewport.get('states', []):
            for message in state.get('mismatches', []):
                notable.append({'viewport': [viewport['width'], viewport['height']], 'state': state['name'], 'issue': message})
            for kind in ('action', 'fullpage'):
                image = state.get(kind)
                if image and image.get('any_difference_ratio', 0) > 0:
                    notable.append({'viewport': [viewport['width'], viewport['height']], 'state': state['name'],
                        'kind': kind, 'status': image.get('status', 'REVIEW'),
                        'difference_ratio': image['difference_ratio'], 'any_difference_ratio': image['any_difference_ratio'],
                        'heatmap': image['heatmap'], 'overlay': image['overlay']})
            for screen in state.get('screens', []):
                if screen.get('any_difference_ratio', 0) > 0:
                    notable.append({'viewport': [viewport['width'], viewport['height']], 'state': state['name'],
                        'screen': screen['index'], 'status': screen['status'],
                        'difference_ratio': screen['difference_ratio'], 'any_difference_ratio': screen['any_difference_ratio'],
                        'heatmap': screen['heatmap'], 'overlay': screen['overlay']})
    notable.sort(key=lambda item: (item.get('issue') is not None, item.get('difference_ratio', 0), item.get('any_difference_ratio', 0)), reverse=True)
    warnings = list(dict.fromkeys(data.get('warnings', [])))
    # Prioritize incomplete full-page coverage over routine resource warnings.
    warnings.sort(key=lambda message: 'Не удалось снять/сравнить длинную страницу' in message, reverse=True)
    return {'schema_version': 1, 'status': data['status'], 'coverage': data.get('coverage'),
            'behavior': data.get('behavior'), 'issues': data.get('issues', [])[:8],
            'warnings': warnings[:8], 'warnings_total': len(warnings), 'notable': notable[:8],
            'notable_total': len(notable), 'details': 'summary.json',
            'next': data.get('next', 'Изучить отчёт и ограничения.')}


def run(source: Path, site: Path, output: Path, scenarios, route='/', threshold=0.001, font_css=None,
        trust_source=False, reference_url=None, candidate_url=None, channel_tolerance=12, reference_route=None, candidate_route=None, work_dir=None):
    raw_output = output.absolute()
    raw_work = Path(work_dir or '.work').absolute()
    if raw_work.is_symlink() or any(p.is_symlink() for p in (raw_output, *raw_output.parents) if p == raw_work or p.is_relative_to(raw_work)):
        return {'status':'BLOCKED','issues':['Символические ссылки рабочей области запрещены'], 'warnings':[]}
    output = raw_output.resolve()
    work = raw_work.resolve()
    if not output.is_relative_to(work) or output == work or (output.exists() and (not output.is_dir() or any(output.iterdir()))):
        return {'schema_version':1, 'status':'BLOCKED', 'issues':['Выберите новый или пустой подкаталог внутри .work/'], 'warnings':[]}
    output.mkdir(parents=True, exist_ok=True)
    def finish(data):
        data.setdefault('warnings', [])
        (output/'summary.json').write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n', encoding='utf8')
        (output/'brief.json').write_text(json.dumps(brief_report(data), ensure_ascii=False, indent=2)+'\n', encoding='utf8')
        return data
    if bool(reference_url) != bool(candidate_url):
        return finish({'schema_version':1,'status':'BLOCKED','issues':['Нужно указать оба URL или ни одного']})
    if reference_url:
        result = audit_urls(reference_url, candidate_url, output, scenarios, route, threshold, font_css, channel_tolerance, reference_route, candidate_route)
        return finish(result)
    if not trust_source:
        return finish({'schema_version':1,'status':'BLOCKED','issues':['Автозапуск отключён: запустите серверы в проверенной ОС-изоляции и укажите оба URL']})
    return finish({'schema_version':1,'status':'BLOCKED','issues':['Автозапуск экспорта отключён: необходима проверенная ОС-изоляция. Запустите эталон отдельно в изоляции и укажите оба URL.']})
