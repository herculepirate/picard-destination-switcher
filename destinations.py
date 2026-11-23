"""The destinations you name, and how the toolbar shows them. Pure Python: no Qt, no Picard.

A destination is {"name": "Lossless", "path": "/music/lossless"}. They are kept in the plugin's
settings as JSON text, in the order you put them.
"""
from __future__ import annotations

import json
import os


def load(text) -> list[dict]:
    """The destinations from the settings' JSON text; [] for none or unreadable text."""
    try:
        data = json.loads(text or '[]')
    except (TypeError, ValueError):
        return []
    out = []
    for d in data if isinstance(data, list) else []:
        if isinstance(d, dict) and str(d.get('path') or '').strip():
            path = str(d['path']).strip()
            out.append({'name': str(d.get('name') or '').strip() or default_name(path), 'path': path})
    return out


def dump(items) -> str:
    """The destinations as the settings' JSON text (empty paths left out)."""
    return json.dumps([{'name': str(d.get('name') or '').strip() or default_name(str(d.get('path') or '')),
                        'path': str(d.get('path') or '').strip()}
                       for d in items or () if str(d.get('path') or '').strip()], ensure_ascii=False)


def default_name(path: str) -> str:
    """A folder's own name ("lossless" for /music/lossless)."""
    p = str(path or '').rstrip('/\\')
    return os.path.basename(p) or p


def same_folder(a: str, b: str) -> bool:
    """Two folder paths are one (a trailing slash, "~" and "." aside)."""
    def norm(p):
        p = os.path.expanduser(str(p or '').strip())
        return os.path.normpath(p) if p else ''
    return bool(norm(a)) and norm(a) == norm(b)


def index_of(items, current: str) -> int:
    """Which destination Picard's current folder is (-1: none of them)."""
    return next((i for i, d in enumerate(items) if same_folder(d['path'], current)), -1)


def label(d: dict) -> str:
    """The dropdown's text: the name you gave it."""
    return d['name']


def scripts(naming_scripts: dict) -> list[tuple[str, str]]:
    """[(id, title)] of Picard's file naming scripts, sorted by title as Picard's menu has them."""
    out = []
    for sid, s in (naming_scripts or {}).items():
        title = (s.get('title') if isinstance(s, dict) else getattr(s, 'title', '')) or str(sid)
        out.append((str(sid), str(title)))
    return sorted(out, key=lambda x: x[1].casefold())
