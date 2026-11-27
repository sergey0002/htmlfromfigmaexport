"""Bounded reads of candidate text, tied to an existing delivery snapshot.

This avoids following a replaced final component where supported; it does not
secure ancestor directories against hostile concurrent mutation.
"""
from pathlib import Path
from .snapshot import read_snapshot_file, read_snapshot_prefix

# Parser input bound, not a total site size, CPU, memory, or wall-time limit.
MAX_TEXT_BYTES = 8 * 1024 * 1024


class SnapshotAccess:
    def __init__(self, root, snapshot):
        self.root=Path(root).resolve()
        self.entries={item['path']:item for item in snapshot['entries']}

    def entry(self, path):
        path=Path(path)
        try: rel=path.relative_to(self.root).as_posix()
        except ValueError: raise ValueError('Путь находится вне candidate snapshot')
        return self.entries.get(rel)

    def is_file(self, path):
        entry=self.entry(path)
        return bool(entry and entry['type']=='file')

    def text(self, path):
        entry=self.entry(path)
        if entry is None: raise ValueError('Файл отсутствует в candidate snapshot')
        return read_snapshot_file(path,entry,MAX_TEXT_BYTES).decode('utf8')

    def prefix(self, path, limit):
        entry=self.entry(path)
        if entry is None: raise ValueError('Файл отсутствует в candidate snapshot')
        return read_snapshot_prefix(path,entry,limit)

    def bytes(self, path):
        entry=self.entry(path)
        if entry is None: raise ValueError('Файл отсутствует в candidate snapshot')
        return read_snapshot_file(path,entry,MAX_TEXT_BYTES)

    def legacy_files(self):
        from .core import IGNORED
        for rel,entry in sorted(self.entries.items()):
            parts=rel.split('/')
            if entry['type']=='file' and not any(part in IGNORED for part in parts) and parts[0]!='.work':
                yield self.root/rel
