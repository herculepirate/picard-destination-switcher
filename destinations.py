"""The destinations you name, and how the toolbar shows them. Pure Python: no Qt, no Picard.

A destination is {"name": "Lossless", "path": "/music/lossless", "script": "<naming script id>",
"colour": "green"}; "script" is optional - the file naming script chosen with that folder (""
keeps the current one) - and so is "colour" ("" automatic, as TagMender colours its profiles;
"none" none). They are kept in the plugin's settings as JSON text, in the order you put them.
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
            out.append({'name': str(d.get('name') or '').strip() or default_name(path), 'path': path,
                        'script': str(d.get('script') or '').strip(),
                        'colour': str(d.get('colour') or '').strip()})
    return out


def dump(items) -> str:
    """The destinations as the settings' JSON text (empty paths left out)."""
    out = []
    for d in items or ():
        path = str(d.get('path') or '').strip()
        if not path:
            continue
        item = {'name': str(d.get('name') or '').strip() or default_name(path), 'path': path}
        for key in ('script', 'colour'):
            if str(d.get(key) or '').strip():
                item[key] = str(d[key]).strip()
        out.append(item)
    return json.dumps(out, ensure_ascii=False)


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


def linked_script(d: dict, naming_scripts: dict) -> str:
    """The naming script chosen with destination D: its id when Picard still has that script,
    else "" (the current script stays)."""
    sid = str((d or {}).get('script') or '')
    return sid if sid and sid in (naming_scripts or {}) else ''


# ---- colours, as TagMender gives its profiles (gui/common.py, gui/style.py) ----------------------
# name -> (label, light tint, dark tint, dot)
TINTS = {'green': ('Green', '#EDF7F0', '#233F2C', '#34C759'),
         'orange': ('Orange', '#FDF1E5', '#4A3519', '#FF9500'),
         'blue': ('Blue', '#EEF3FB', '#223A5C', '#0A84FF'),
         'purple': ('Purple', '#F6F2FB', '#3B2E57', '#AF52DE'),
         'teal': ('Teal', '#EAF6F6', '#1B3D40', '#30B0C7'),
         'pink': ('Pink', '#FCEFF5', '#4D2640', '#FF2D7A'),
         'amber': ('Amber', '#FCF6E1', '#3E3714', '#FFCC00'),
         'red': ('Red', '#FDF1F0', '#4E2828', '#FF3B30'),
         'grey': ('Grey', '#F3F4F6', '#31373F', '#8E8E93')}
# a name that gives its colour (TagMender's NAME_COLOURS), then the colours given in turn
NAME_COLOURS = (('lossyless', 'green'), ('extreme', 'orange'))
AUTO_COLOURS = ('blue', 'purple', 'teal', 'pink', 'amber', 'grey', 'red', 'green', 'orange')
AUTO, NONE = '', 'none'


def name_colour(name: str) -> str:
    low = str(name or '').lower()
    return next((c for word, c in NAME_COLOURS if word in low), '')


def colours(items, profiles=None) -> list[str]:
    """Each destination's colour, as TagMender colours its profiles: its own ("none": none),
    else - automatic - the colour of TagMender's profile saving to that folder (PROFILES:
    tagmender_profiles()), else its name's ("lossyless" green, "extreme" orange), else the
    next of AUTO_COLOURS not taken, destinations in the order of their names - so a folder
    keeps its colour while the list stays the same."""
    own = [str(d.get('colour') or AUTO) for d in items]
    if profiles:
        by_profile = tagmender_colours(profiles)
        for i, d in enumerate(items):
            if not own[i]:
                got = tagmender_colour_for(d, profiles, by_profile)
                if got is not None:
                    own[i] = got or NONE
    rule = [name_colour(d.get('name')) for d in items]
    taken = {c for c in own if c and c != NONE} | {r for o, r in zip(own, rule) if r and not o}
    free = [c for c in AUTO_COLOURS if c not in taken] or list(AUTO_COLOURS)
    out = [''] * len(items)
    k = 0
    for i in sorted(range(len(items)), key=lambda i: str(items[i].get('name') or '').lower()):
        if own[i] == NONE:
            out[i] = ''
        elif own[i]:
            out[i] = own[i] if own[i] in TINTS else ''
        elif rule[i]:
            out[i] = rule[i]
        else:
            out[i] = free[k % len(free)]
            k += 1
    return out


def tint(colour: str, dark: bool) -> str:
    """The wash a bar of that colour is painted with ("" for none)."""
    t = TINTS.get(colour)
    return (t[2] if dark else t[1]) if t else ''


def dot(colour: str) -> str:
    t = TINTS.get(colour)
    return t[3] if t else ''


# ---- TagMender's own profiles: a folder one of them saves to takes that profile's colour ---------
TAGMENDER_PROFILES = os.path.join('~', '.config', 'tagmender', 'profiles')


def tagmender_profiles(folder: str = TAGMENDER_PROFILES) -> list[dict]:
    """[{"name", "destination", "colour"}] of TagMender's profiles ([] when there are none)."""
    folder = os.path.expanduser(folder)
    out = []
    try:
        names = sorted(f[:-5] for f in os.listdir(folder) if f.endswith('.json'))
    except OSError:
        return []
    for name in names:
        try:
            with open(os.path.join(folder, name + '.json'), encoding='utf-8') as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            continue
        if isinstance(data, dict):
            out.append({'name': name, 'destination': str(data.get('destination') or ''),
                        'colour': data.get('colour') if isinstance(data.get('colour'), str) else None})
    return out


def tagmender_colours(profiles) -> dict:
    """Each TagMender profile's colour, as TagMender gives it (gui/common.py _colours): its own
    ("none": none), else its name's, else the next free colour, profiles ("default" too) in the
    order of their names."""
    names = sorted(['default'] + [p['name'] for p in profiles], key=str.lower)
    own = {p['name']: (p.get('colour') or '').strip() or None for p in profiles}
    rule = {n: name_colour(n) for n in names}
    taken = {c for c in own.values() if c and c != NONE} | {rule[n] for n in names if rule[n] and own.get(n) is None}
    free = [c for c in AUTO_COLOURS if c not in taken] or list(AUTO_COLOURS)
    out, k = {}, 0
    for n in names:
        o = own.get(n)
        if o is not None:
            out[n] = '' if o == NONE else o
            if not rule[n]:
                k += 1
        elif rule[n]:
            out[n] = rule[n]
        else:
            out[n] = free[k % len(free)]
            k += 1
    return out


def tagmender_colour_for(d: dict, profiles, by_profile: dict) -> str | None:
    """The colour of the TagMender profile saving to D's folder (one named like D first), or
    None when no profile saves there."""
    there = [p for p in profiles if same_folder(p['destination'], d.get('path'))]
    if not there:
        return None
    word = str(d.get('name') or '').lower()
    there.sort(key=lambda p: (word not in p['name'].lower(), p['name'].lower()))
    return by_profile.get(there[0]['name'], '')
