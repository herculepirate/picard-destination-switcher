"""Everything else in an album's folder goes with it: covers, logs, cue sheets, booklets, and
the folders holding them - wherever they sit in the album's folder.

Picard's own "Move additional files" looks only in the folder each audio file sits in, and
never takes a folder. A set of discs keeps its covers, rip logs and booklets beside its disc
folders:

    Album/                  <- covers/, Album.log, booklet.pdf: Picard never looks here
      covers/
      CD1/  01.flac ...     <- "Move additional files" looks here only
      CD2/  01.flac ...

When the last audio file of an album has been saved somewhere else and its old album folder
holds no audio file any more (anywhere in it), what is left there is moved into the album's
new folder. A folder still holding music (an album saved in part, an artist's folder of
several albums) is never touched.

Pure Python: no Qt, no Picard.
"""
from __future__ import annotations

import os
import re
import shutil

AUDIO_EXT = {'.flac', '.mp3', '.m4a', '.mp4', '.ogg', '.opus', '.oga', '.wv', '.ape', '.wav', '.aif',
             '.aiff', '.aifc', '.dsf', '.dff', '.wma', '.mpc', '.tta', '.tak', '.ofr', '.spx', '.mka', '.m4b'}

# a disc's own folder: "CD1", "CD 2", "Disc 01", "Disk 1 - The Early Years", "DVD", "Side A"
# ("Vol. 2" and "Part 1" are left out: as often a whole album as one of its discs)
DISC_DIR = re.compile(
    r'^\s*[\[(]?\s*(?:cd|disc|disk|dvd|sacd|bd|blu-?ray|vinyl|lp|side|tape|cassette)'
    r'\s*[-_.#]?\s*(?:\d{1,3}|[a-h])?\b.*$', re.I)


def is_disc_dir(name: str) -> bool:
    return bool(DISC_DIR.match(name or ''))


def album_root(dirs) -> str | None:
    """The album's own folder, from the folders its audio files are in: the one folder; or the
    folder holding its disc folders. None when they are spread otherwise (not swept)."""
    dirs = {os.path.normpath(d) for d in dirs if d}
    if len(dirs) == 1:
        d = next(iter(dirs))
        return os.path.dirname(d) if is_disc_dir(os.path.basename(d)) else d
    parents = {os.path.dirname(d) for d in dirs}
    if len(parents) == 1 and all(is_disc_dir(os.path.basename(d)) for d in dirs):
        return parents.pop()
    return None


def album_dirs(pairs) -> tuple[set, set]:
    """({old folders}, {new folders}) of an album's files, from [(old name, new name)]."""
    old, new = set(), set()
    for before, after in pairs:
        if before:
            old.add(os.path.normpath(os.path.dirname(before)))
        if after:
            new.add(os.path.normpath(os.path.dirname(after)))
    return old, new


def holds_audio(root: str) -> bool:
    for _dir, _sub, names in os.walk(root):
        if any(os.path.splitext(n)[1].lower() in AUDIO_EXT for n in names):
            return True
    return False


def _inside(path: str, folder: str) -> bool:
    path, folder = os.path.normpath(path), os.path.normpath(folder)
    return path == folder or path.startswith(folder.rstrip(os.sep) + os.sep)


def plan(old_root: str | None, new_root: str | None, old_dirs=(), new_dirs=()) -> list[tuple[str, str]]:
    """[(what, where to)] of what is left in OLD_ROOT to move into NEW_ROOT. Nothing when: either
    is unknown, they are one folder or one is inside the other, OLD_ROOT still holds audio, or
    is gone. An old disc folder left behind with only its leftovers goes into the new folder
    of that disc when one is known (CD1 -> CD1), else into NEW_ROOT under its own name."""
    if not old_root or not new_root or not os.path.isdir(old_root):
        return []
    if _inside(new_root, old_root) or _inside(old_root, new_root):
        return []
    if holds_audio(old_root):
        return []
    new_by_name = {os.path.basename(d).casefold(): d for d in new_dirs if os.path.dirname(os.path.normpath(d)) == os.path.normpath(new_root)}
    out = []
    for entry in sorted(os.listdir(old_root)):
        src = os.path.join(old_root, entry)
        if os.path.isdir(src) and is_disc_dir(entry) and entry.casefold() in new_by_name:
            out.append((src, new_by_name[entry.casefold()]))
        else:
            out.append((src, os.path.join(new_root, entry)))
    return out


def apply(moves, overwrite: bool = False) -> tuple[list, list]:
    """Move each (what, where). A folder is merged into one already there; a file already
    there is kept (and the one left behind) unless OVERWRITE. Returns (moved, skipped)."""
    moved, skipped = [], []
    for src, dst in moves:
        if os.path.isdir(src):
            if os.path.isdir(dst):
                sub = [(os.path.join(src, n), os.path.join(dst, n)) for n in sorted(os.listdir(src))]
                m, s = apply(sub, overwrite)
                moved += m
                skipped += s
                try:
                    os.rmdir(src)
                except OSError:
                    pass
                continue
            if os.path.exists(dst):
                skipped.append((src, dst))
                continue
        elif os.path.exists(dst):
            if not overwrite or os.path.isdir(dst):
                skipped.append((src, dst))
                continue
            os.remove(dst)
        try:
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.move(src, dst)
            moved.append((src, dst))
        except OSError:
            skipped.append((src, dst))
    return moved, skipped


def remove_if_empty(folder: str) -> bool:
    """FOLDER removed when nothing is left in it (empty sub-folders too)."""
    if not os.path.isdir(folder):
        return False
    for d, subs, names in os.walk(folder, topdown=False):
        if names:
            return False
        for s in subs:
            try:
                os.rmdir(os.path.join(d, s))
            except OSError:
                return False
    try:
        os.rmdir(folder)
        return True
    except OSError:
        return False
