"""Identity of local diagnostic code and runtime; not proof of authenticity."""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
import platform
from pathlib import Path

from . import queue_md as md


def current():
    root=Path(__file__).resolve().parent
    files={}
    for path in sorted(root.glob('*.py')):
        files[path.name]=md.sha(md._safe_read(path))
    packages={}
    for name in ('playwright','Pillow','PyYAML','tree-sitter','tree-sitter-javascript','tree-sitter-typescript'):
        try: packages[name]=importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError: packages[name]=None
    identity={'schema':'diagnostic-toolchain-v1','python':platform.python_version(),
              'implementation':platform.python_implementation(), 'system':platform.system(),
              'machine':platform.machine(),'packages':packages,'files':files}
    raw=json.dumps(identity,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf8')
    return identity,hashlib.sha256(raw).hexdigest()
