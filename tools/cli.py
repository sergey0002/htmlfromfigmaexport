"""CLI for inventory, static checks and opt-in browser audits."""
from __future__ import annotations
import argparse
import json
import uuid
from pathlib import Path
from .core import analyze, check_site
from .browser import compare
from .screen_audit import load_scenarios
from .audit_runner import run as run_audit


def main(argv=None):
    parser = argparse.ArgumentParser(description='Инвентаризация и проверки Figma → vanilla')
    subs = parser.add_subparsers(dest='command', required=True)
    a = subs.add_parser('analyze'); a.add_argument('--source', default='source')
    c = subs.add_parser('check'); c.add_argument('--site', default='vanilla')
    b = subs.add_parser('compare'); b.add_argument('--reference', required=True); b.add_argument('--candidate', required=True)
    b.add_argument('--width', type=int, default=390); b.add_argument('--height', type=int, default=844)
    b.add_argument('--threshold', type=float, default=0.01); b.add_argument('--output', default='.work/compare')
    b.add_argument('--scenario', help='JSON-файл: список безопасных действий')
    d = subs.add_parser('browser-audit', help='Поэкранная сверка мобильного, планшета и десктопа')
    d.add_argument('--source', default='source'); d.add_argument('--site', default='vanilla')
    d.add_argument('--reference-url'); d.add_argument('--candidate-url')
    d.add_argument('--trust-source', action='store_true', help='Разрешить запуск проверенного Vite-кода в копии (не песочница)')
    d.add_argument('--route', default='/'); d.add_argument('--scenario', help='JSON массив состояний для двух страниц')
    d.add_argument('--font-css', help='Явно подставить локальные шрифты эталону для контролируемой сверки')
    d.add_argument('--threshold', type=float, default=0.001); d.add_argument('--channel-tolerance', type=int, default=12)
    d.add_argument('--output')
    for p in (a, c, b, d): p.add_argument('--report', help='Путь JSON-отчёта'); p.add_argument('--json', action='store_true')
    args = parser.parse_args(argv)
    if args.command == 'analyze': result = analyze(Path(args.source))
    elif args.command == 'check': result = check_site(Path(args.site))
    elif args.command == 'browser-audit':
        try:
            scenarios = load_scenarios(Path(args.scenario) if args.scenario else None)
        except (OSError, UnicodeError, ValueError) as e:
            print(f'BLOCKED: некорректный сценарий: {e}')
            return 3
        output = Path(args.output) if args.output else Path('.work/browser-audits') / uuid.uuid4().hex
        result = run_audit(Path(args.source), Path(args.site), output, scenarios, args.route, args.threshold,
                           Path(args.font_css) if args.font_css else None, args.trust_source,
                           args.reference_url, args.candidate_url, args.channel_tolerance)
        result['artifact_directory'] = str(output)
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
        from .audit_runner import brief_report
        brief = brief_report(result)
        for warning in brief['warnings']: print(f'  WARN: {warning}')
        if brief['warnings_total'] > len(brief['warnings']): print(f"  ... ещё предупреждений: {brief['warnings_total']-len(brief['warnings'])}; подробности в summary.json")
        if result.get('coverage'):
            coverage = result['coverage']
            print(f"  Состояний: {coverage['states_checked']}/{coverage['states_planned']}; экранов: {coverage['screens_compared']}")
            brief = brief_report(result)
            for item in brief['notable']:
                size = 'x'.join(map(str, item['viewport']))
                if 'issue' in item:
                    print(f"  {size}/{item['state']}: {item['issue']}")
                else:
                    print(f"  {size}/{item['state']}/{item.get('kind', 'экран '+str(item.get('screen', '')))}: {item['status']} {item['difference_ratio']:.2%}, карта {item['heatmap']}")
            if brief['notable_total'] > len(brief['notable']): print(f"  ... ещё записей: {brief['notable_total'] - len(brief['notable'])}; полный отчёт в summary.json")
        if result.get('artifact_directory'): print(f"Артефакты: {result['artifact_directory']}")
        if result.get('next'): print(result['next'])
        if args.report: print(f'Отчёт: {args.report}')
    return {'INCOMPLETE': 2, 'BLOCKED': 3, 'FAIL': 1, 'PASS': 0}[result['status']]


if __name__ == '__main__':
    raise SystemExit(main())
