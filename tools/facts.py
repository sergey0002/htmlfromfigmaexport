"""Extract bounded syntactic observations, without inventing pages or routes."""
from __future__ import annotations

import hashlib
from html.parser import HTMLParser
from pathlib import Path
from .snapshot import read_snapshot_file, take_snapshot

MAX_FILE = 5_000_000
MAX_FACTS = 100_000


class TooManyFacts(ValueError):
    pass
NODE_TYPES = {'import_statement', 'call_expression', 'jsx_attribute', 'pair',
              'binary_expression', 'template_string', 'string'}


class Links(HTMLParser):
    def __init__(self, add):
        super().__init__(convert_charrefs=True)
        self.add = add

    def handle_starttag(self, tag, attrs):
        for name, value in attrs:
            if name in ('href', 'src', 'action') and value is not None:
                self.add('html_attribute', self.getpos()[0], self.getpos()[1],
                         {'tag': tag, 'attribute': name, 'value': value[:500]})


def scan_facts(source: Path, *, include_text: bool = False, file_filter: str | None = None) -> dict:
    source = Path(source).absolute()
    before = take_snapshot(source, 'source')
    if file_filter is not None and file_filter not in {e['path'] for e in before['entries'] if e['type'] == 'file'}:
        raise ValueError('Указанный файл отсутствует или исключён политикой source snapshot')
    facts, warnings = [], []
    if include_text:
        warnings.append('Фрагменты исходника могут содержать чувствительные данные; проверяйте отчёт перед передачей.')
    try:
        from tree_sitter import Language, Parser
        import tree_sitter_typescript as ts
        import tree_sitter_javascript as js
        languages = {'ts': Language(ts.language_typescript()),
                     'tsx': Language(ts.language_tsx()),
                     'js': Language(js.language())}
    except ImportError:
        languages = None
        warnings.append('AST-анализ JS/TS недоступен; HTML-факты доступны независимо.')
    for entry in before['entries']:
        if entry['type'] != 'file':
            continue
        rel = entry['path']
        if file_filter is not None and rel != file_filter:
            continue
        path = source / rel
        suffix = path.suffix.lower()
        if suffix not in ('.js', '.jsx', '.ts', '.tsx', '.html', '.htm'):
            continue
        if entry['size'] > MAX_FILE:
            warnings.append(f'{rel}: файл превышает лимит разбора {MAX_FILE} байт')
            continue
        # Do not parse bytes from a later replacement or a final-component
        # symlink: fail the entire observation rather than report mixed input.
        src = read_snapshot_file(path, entry, MAX_FILE)
        try:
            src.decode('utf8')
        except UnicodeError as exc:
            warnings.append(f'{rel}: не удалось прочитать UTF-8: {exc}')
            continue

        def add(kind, line, column, data):
            key = f'{rel}\0{kind}\0{line}\0{column}\0{data!r}'.encode('utf8')
            if len(facts) >= MAX_FACTS: raise TooManyFacts('Превышен лимит фактов; используйте фильтр конкретного файла')
            shown = data if include_text else {k:v for k,v in data.items() if k not in ('text', 'value')}
            facts.append({'id': hashlib.sha256(key).hexdigest()[:16], 'file': rel,
                          'line': line, 'column': column, 'kind': kind, **shown})

        if suffix in ('.html', '.htm'):
            add('html_file', 1, 0, {})
            parser = Links(add)
            try:
                parser.feed(src.decode('utf8'))
                parser.close()
            except TooManyFacts:
                raise
            except Exception as exc:
                warnings.append(f'{rel}: ошибка разбора HTML: {exc}')
            continue
        if languages is None:
            continue
        try:
            lang = languages['tsx' if suffix == '.tsx' else 'ts' if suffix == '.ts' else 'js']
            node = Parser(lang).parse(src).root_node
            if node.has_error:
                warnings.append(f'{rel}: AST содержит ошибки')
            stack = [node]
            while stack:
                item = stack.pop()
                if item.type in NODE_TYPES:
                    raw = src[item.start_byte:item.end_byte].decode('utf8', errors='replace')
                    add('ast_' + item.type, item.start_point.row + 1, item.start_point.column,
                        {'text': raw[:500], 'truncated': len(raw) > 500,
                         'start_byte': item.start_byte, 'end_byte': item.end_byte})
                stack.extend(reversed(item.named_children))
        except TooManyFacts:
            raise
        except Exception as exc:
            warnings.append(f'{rel}: ошибка AST: {type(exc).__name__}: {exc}')
    after = take_snapshot(source, 'source')
    if before['digest'] != after['digest']:
        raise ValueError('Исходник изменился при сборе фактов; повторите анализ')
    return {'snapshot_version': 2, 'source_snapshot': before['digest'],
            'facts': facts, 'warnings': warnings, 'excluded': before['excluded'],
            'text_included': include_text, 'file_filter': file_filter}
