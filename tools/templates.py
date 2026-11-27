"""Compare duplicated static blocks with CMS snippets without executing PHP."""
from __future__ import annotations
from html.parser import HTMLParser
import json
import re
from urllib.parse import urljoin, urlsplit


class Blocks(HTMLParser):
    def __init__(self, document_path, snippet=False):
        super().__init__(convert_charrefs=True)
        self.path='/'+document_path.lstrip('/')
        self.snippet=snippet; self.active='SNIPPET' if snippet else None
        self.blocks={'SNIPPET':[], 'HEADER':[], 'FOOTER':[]}; self.markers=[]
    def _append(self, token):
        if self.active: self.blocks[self.active].append(token)
    def handle_comment(self, data):
        name=data.strip()
        if name in ('HEADER:START','HEADER:END','FOOTER:START','FOOTER:END'):
            self.markers.append(name)
            if name.endswith(':START'): self.active=name.split(':')[0]
            else: self.active=None
    def _attrs(self,attrs):
        result=[]
        for name,val in attrs:
            if name in ('href','src') and val and not urlsplit(val).scheme and not val.startswith('//'):
                val=urljoin(self.path,val)
            result.append((name,val))
        return tuple(sorted(result,key=lambda x:x[0]))
    def handle_starttag(self,tag,attrs): self._append(('start',tag,self._attrs(attrs)))
    def handle_startendtag(self,tag,attrs): self._append(('empty',tag,self._attrs(attrs)))
    def handle_endtag(self,tag): self._append(('end',tag))
    def handle_data(self,data):
        if data.strip(): self._append(('text',' '.join(data.split())))


def _policy_token(value):
    """Decode the canonical, single-token representation used by policy v2."""
    if not isinstance(value,list) or len(value)<2: raise ValueError('Некорректный token template-policy')
    kind=value[0]
    if kind=='text':
        if len(value)!=2 or not isinstance(value[1],str) or not value[1] or len(value[1])>2000 or ' '.join(value[1].split())!=value[1]:
            raise ValueError('Некорректный текстовый token template-policy')
        return ('text',value[1])
    if kind not in ('start','empty') or len(value)!=3 or not isinstance(value[1],str) or not re.fullmatch(r'[a-z][a-z0-9:._-]{0,127}',value[1]) or not isinstance(value[2],list) or len(value[2])>100:
        raise ValueError('Некорректный token элемента template-policy')
    attrs=[]
    for pair in value[2]:
        if (not isinstance(pair,list) or len(pair)!=2 or not isinstance(pair[0],str) or
                not re.fullmatch(r'[a-z_:][a-z0-9:._-]{0,127}',pair[0]) or
                (pair[1] is not None and (not isinstance(pair[1],str) or len(pair[1])>2000))):
            raise ValueError('Некорректный атрибут token template-policy')
        attrs.append(tuple(pair))
    names=[key for key,_ in attrs]
    if names!=sorted(set(names)): raise ValueError('Атрибуты token должны быть уникальными и отсортированными')
    return (kind,value[1],tuple(attrs))


def _unique_json_pairs(pairs):
    result={}
    for key,value in pairs:
        if key in result: raise ValueError('Повторный ключ JSON template-policy')
        result[key]=value
    return result


def parse_policy(raw, outputs):
    """Validate explicitly scoped navigation and exact token substitutions."""
    from .queue import local_route, safe_output
    try: data=json.loads(raw.decode('utf8'),object_pairs_hook=_unique_json_pairs)
    except (UnicodeError, ValueError) as exc: raise ValueError('Некорректный JSON template-policy') from exc
    if not isinstance(data,dict) or type(data.get('version'))!=int or data['version'] not in (1,2):
        raise ValueError('Неизвестный формат template-policy')
    keys={'version','exceptions'} if data['version']==1 else {'version','exceptions','substitutions'}
    if set(data)!=keys or not isinstance(data['exceptions'],list) or len(data['exceptions'])>1000:
        raise ValueError('Неизвестный формат template-policy')
    seen=set()
    for item in data['exceptions']:
        keys={'output','block','href','add_class','aria_current','reason'}
        if not isinstance(item,dict) or set(item)!=keys: raise ValueError('Некорректная запись template-policy')
        output=item['output']; block=item['block']; href=item['href']; cls=item['add_class']; aria=item['aria_current']; reason=item['reason']
        if (not isinstance(output,str) or not safe_output(output) or output not in outputs or block not in ('HEADER','FOOTER')
                or not isinstance(href,str) or not local_route(href)
                or not isinstance(cls,str) or (cls and not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_-]{0,79}',cls))
                or aria not in ('','page') or not (cls or aria) or not isinstance(reason,str) or not reason.strip() or len(reason)>1000):
            raise ValueError('Некорректное ограниченное исключение template-policy')
        key=(output,block,href)
        if key in seen: raise ValueError('Повторное исключение template-policy')
        seen.add(key)
    if data['version']==2:
        substitutions=data['substitutions']; seen=set()
        if not isinstance(substitutions,list) or len(substitutions)>1000:
            raise ValueError('Некорректный список замен template-policy')
        for item in substitutions:
            if not isinstance(item,dict) or set(item)!={'output','block','index','before','after','reason'}:
                raise ValueError('Некорректная замена template-policy')
            output=item['output']; block=item['block']; index=item['index']; reason=item['reason']
            if (not isinstance(output,str) or not safe_output(output) or output not in outputs or block not in ('HEADER','FOOTER') or
                    type(index)!=int or not 0<=index<=1000000 or not isinstance(reason,str) or not reason.strip() or len(reason)>1000):
                raise ValueError('Некорректная область или обоснование замены template-policy')
            before=_policy_token(item['before']); after=_policy_token(item['after'])
            if before==after or before[0]!=after[0] or (before[0]!='text' and before[1]!=after[1]):
                raise ValueError('Замена может изменить только текст или атрибуты одного элемента')
            key=(output,block,index)
            if key in seen: raise ValueError('Повторная замена token template-policy')
            seen.add(key)
    return data


def _substitute_tokens(tokens, substitutions):
    result=list(tokens)
    for rule in substitutions:
        index=rule['index']; before=_policy_token(rule['before']); after=_policy_token(rule['after'])
        if index>=len(result) or result[index]!=before:
            raise ValueError(f'Исходный token {index} не совпадает с template-policy')
        result[index]=after
    return result


def _normalise_active(tokens, exceptions, expected):
    """Apply permitted additions only to the uniquely named anchor in a block."""
    found={x['href']:0 for x in exceptions}; rules={x['href']:x for x in exceptions}; result=[]
    for token in tokens:
        if len(token)==3 and token[0] in ('start','empty') and token[1]=='a':
            attrs=token[2]; names=[name for name,_ in attrs]
            if len(set(names))!=len(names): raise ValueError('Повторные атрибуты ссылки недопустимы при policy')
            values=dict(attrs); href=values.get('href'); rule=rules.get(href)
            if rule:
                found[href]+=1
                classes=(values.get('class') or '').split()
                if expected:
                    if rule['add_class']:
                        if rule['add_class'] in classes: raise ValueError('Разрешённый класс уже присутствует в шаблоне')
                        classes.append(rule['add_class'])
                    if rule['aria_current']:
                        if 'aria-current' in values: raise ValueError('aria-current уже присутствует в шаблоне')
                        values['aria-current']=rule['aria_current']
                if 'class' in values or (expected and rule['add_class']): values['class']=' '.join(sorted(classes))
                token=(token[0],token[1],tuple(sorted(values.items())))
        result.append(token)
    if any(n!=1 for n in found.values()): raise ValueError('Каждое исключение должно соответствовать ровно одной ссылке')
    return result


def inspect_tokens(site, page, block, offset=0, limit=100):
    """Expose paginated parsed tokens for a policy proposal, without edits."""
    from pathlib import Path
    from .queue import safe_output
    from .lifecycle import _site_root
    from .snapshot import take_snapshot
    from .snapshot_access import SnapshotAccess
    if (not safe_output(page) or block not in ('HEADER','FOOTER') or type(offset)!=int or offset<0 or
            type(limit)!=int or not 1<=limit<=100):
        raise ValueError('Недопустимая страница, блок или пагинация')
    site=_site_root(site); before=take_snapshot(site,'delivery'); access=SnapshotAccess(site,before)
    snippet=site/'template'/(block.lower()+'.php'); document=site/Path(page)
    if not access.is_file(snippet) or not access.is_file(document): raise ValueError('Нет страницы или статической заготовки в snapshot')
    raw=access.text(snippet)
    if '<?' in raw: raise ValueError('PHP-код или processing instruction в заготовке запрещён')
    template=Blocks('index.html',snippet=True); template.feed(raw); template.close()
    candidate=Blocks(page); candidate.feed(access.text(document)); candidate.close()
    if candidate.markers!=['HEADER:START','HEADER:END','FOOTER:START','FOOTER:END']:
        raise ValueError('Некорректные маркеры header/footer')
    def window(tokens):
        result=[]
        for index,token in enumerate(tokens[offset:offset+limit],start=offset):
            value=json.loads(json.dumps(token,ensure_ascii=False))
            try: _policy_token(value); replaceable=True
            except ValueError: replaceable=False
            result.append({'index':index,'token':value,'replaceable':replaceable})
        return {'total':len(tokens),'items':result}
    result={'site_snapshot':before['digest'],'page':page,'block':block,'offset':offset,'limit':limit,
            'template':window(template.blocks['SNIPPET']),'candidate':window(candidate.blocks[block])}
    if take_snapshot(site,'delivery')['digest']!=before['digest']:
        raise ValueError('Candidate изменился при чтении token')
    return result


def compare_template(site, pages, policy=None, *, snapshot_access=None):
    """Compare all parsed tokens, applying only exact, explicit policy rules."""
    issues=[]; warnings=[]; reference={}
    is_file=snapshot_access.is_file if snapshot_access else lambda p: p.is_file()
    read_text=snapshot_access.text if snapshot_access else lambda p: p.read_text(encoding='utf8')
    if (site/'template').is_symlink(): return ['template/: symlink запрещён'], []
    for block in ('HEADER','FOOTER'):
        path=site/'template'/(block.lower()+'.php')
        if not is_file(path): warnings.append(f'Отсутствует template/{block.lower()}.php'); continue
        if path.is_symlink(): issues.append(f'template/{block.lower()}.php: symlink запрещён'); continue
        text=read_text(path)
        if '<?' in text: issues.append(f'template/{block.lower()}.php: PHP-код запрещён в статической заготовке'); continue
        parser=Blocks('index.html',snippet=True); parser.feed(text)
        reference[block]=parser.blocks['SNIPPET']
        if not reference[block]: issues.append(f'template/{block.lower()}.php: пустой шаблон')
    for path in pages:
        output=path.relative_to(site).as_posix()
        parser=Blocks(output); parser.feed(read_text(path))
        if parser.markers != ['HEADER:START','HEADER:END','FOOTER:START','FOOTER:END']: continue
        for block in reference:
            rules=[x for x in policy['exceptions'] if x['output']==output and x['block']==block] if policy else []
            substitutions=[x for x in policy.get('substitutions',[]) if x['output']==output and x['block']==block] if policy else []
            for rule in substitutions:
                warnings.append(f"{output}: явное отличие {block.lower()} token {rule['index']}: {rule['reason']}")
            try:
                base=_substitute_tokens(reference[block],substitutions)
                expected=_normalise_active(base,rules,True) if rules else base
                actual=_normalise_active(parser.blocks[block],rules,False) if rules else parser.blocks[block]
                if actual!=expected:
                    issues.append(f'{output}: {block.lower()} не соответствует template/{block.lower()}.php с учётом относительных путей и явных исключений')
            except ValueError as exc: issues.append(f'{output}: {block.lower()}: {exc}')
    return issues,warnings
