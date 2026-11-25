"""Small, conservative CLI. No installation or execution of export code."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from .core import analyze, check_site
from .browser import compare


def main(argv=None):
    parser = argparse.ArgumentParser(description='Инвентаризация и проверки Figma → vanilla')
    subs = parser.add_subparsers(dest='command', required=True)
    a = subs.add_parser('analyze'); a.add_argument('--source', default='source')
    c = subs.add_parser('check'); c.add_argument('--site', default='vanilla')
    b = subs.add_parser('compare'); b.add_argument('--reference', required=True); b.add_argument('--candidate', required=True)
    b.add_argument('--width', type=int, default=390); b.add_argument('--height', type=int, default=844)
    b.add_argument('--threshold', type=float, default=0.01); b.add_argument('--output', default='.work/compare')
    b.add_argument('--scenario', help='JSON-файл: список безопасных действий')
    for p in (a, c, b): p.add_argument('--report', help='Путь JSON-отчёта'); p.add_argument('--json', action='store_true')
    args = parser.parse_args(argv)
    if args.command == 'analyze': result = analyze(Path(args.source))
    elif args.command == 'check': result = check_site(Path(args.site))
    else:
        actions = None
        if args.scenario:
            try:
                actions = json.loads(Path(args.scenario).read_text(encoding='utf8'))
                if not isinstance(actions, list): raise ValueError('сценарий должен быть массивом')
            except (OSError, UnicodeError, ValueError) as e:
                print(f'BLOCKED: некорректный сценарий: {e}')
                return 3
        result = compare(args.reference, args.candidate, args.width, args.height, Path(args.output), args.threshold, actions)
    result = {'schema_version': 1, 'command': args.command, **result}
    data = json.dumps(result, ensure_ascii=False, indent=2)
    if args.report:
        path = Path(args.report).resolve(); work = Path('.work').resolve()
        if not path.is_relative_to(work) or path == work or path.exists():
            print('BLOCKED: отчёт должен быть новым файлом внутри .work/')
            return 3
        path.parent.mkdir(parents=True, exist_ok=True); path.write_text(data + '\n', encoding='utf8')
    if args.json: print(data)
    else:
        print(f"{result['status']}: {args.command}")
        for issue in result.get('issues', []) + result.get('mismatches', []): print(f'  - {issue}')
        for warning in result.get('warnings', []): print(f'  WARN: {warning}')
        if result.get('next'): print(result['next'])
        if args.report: print(f'Отчёт: {args.report}')
    return {'INCOMPLETE': 2, 'BLOCKED': 3, 'FAIL': 1, 'PASS': 0}[result['status']]


if __name__ == '__main__':
    raise SystemExit(main())
