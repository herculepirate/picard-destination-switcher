"""Destination Switcher: where Picard saves, and with which file naming script, from a bar above
one of Picard's panes (or a toolbar), coloured as TagMender colours its profiles - for the albums
selected in the right pane alone, or (none selected) for every album.

The bar shows and changes Picard's own settings - its destination directory (move_files_to),
Move files (move_files), Rename files (rename_files) and the active file naming script
(active_file_naming_script_id) - and follows them when they change anywhere else (Options, the
Options menu, a profile). The folders the "Save to" dropdown offers are yours, named under
Options > Plugins > Destination Switcher ("Lossless", "Lossy" ...), each with a naming script
chosen with it and a colour: the bar is tinted with the colour of the folder Picard saves to.

Picard 3 has no API for main-window widgets: the bar is put into the window the plugin api gives
(api.tagger.window) when the plugin is enabled - above the right pane (where files go), above
the left pane, or on a toolbar - and removed when it is disabled.
"""
from __future__ import annotations

import os
from functools import partial

from PyQt6 import QtCore, QtGui, QtWidgets

from picard.plugin3.api import BaseAction, OptionsPage

try:
    from . import destinations as dst
    from . import sweep
except ImportError:  # run outside Picard (tests)
    import destinations as dst
    import sweep

# the plugin's own settings, with their defaults
DEFAULTS = {
    'destinations': '[]',          # JSON: [{"name", "path", "script", "colour"}, ...]
    'placement': 'right',          # right (above the album pane) | left (above the files pane) | toolbar
    'tagmender_colours': True,     # automatic colours: TagMender's profile for that folder first
    'move_on_choose': True,        # choosing a folder turns Move files on
    'show_switches': True,         # Move files / Rename files on the bar
    'show_scripts': True,          # the naming script dropdown
    'tint_albums': True,           # each album in the right pane tinted with its folder's colour
    'sweep_album_folder': True,    # what is left in an album's old folder (covers/, logs) goes with it
}
PLACEMENTS = (('right', 'Above the right pane (where files go)'),
              ('left', 'Above the left pane (the files)'),
              ('toolbar', 'On a toolbar'))
# Picard's settings the bar shows (a change to any of them redraws it)
WATCHED = {'move_files_to', 'move_files', 'rename_files', 'file_renaming_scripts',
           'active_file_naming_script_id'}
BAR_NAME = 'destination_switcher_bar'
TOOLBAR_NAME = 'destination_switcher_toolbar'

_API = None
_BAR: 'SwitcherBar | None' = None
_HOST = None                    # the toolbar holding the bar, when placed on one
# each album's own folder and naming script: {album id: {"path", "script"}} (none: Picard's)
_ALBUMS: dict = {}
_ORIG_MAKE_FILENAME = None      # Picard's File.make_filename, while ours stands in for it
_ORIG_SAVE_AND_RENAME = None    # Picard's File._save_and_rename, while ours stands in for it
# each album's folders this session: {album key: {"old": {dirs}, "new": {dirs}}}
_SWEEP: dict = {}
_SWEEP_LOCK = __import__('threading').Lock()
_HOOKS: list = []               # (signal, slot) connected while the bar is shown
_RETINT_DUE = False
COLUMN_KEY = '~destination_switcher_saves_to'   # the "Saves to" column of the right pane
COLUMN_TITLE = 'Saves to'
MIXED, SAME = '\x00mixed', '\x00same'


def _setting():
    return _API.global_config.setting


def _own(key):
    try:
        value = _API.plugin_config[key]
    except Exception:
        value = None
    return DEFAULTS[key] if value is None else value


def _set_own(key, value) -> None:
    _API.plugin_config[key] = value


def _log():
    return getattr(_API, 'logger', None)


def _dark(widget) -> bool:
    return widget.palette().window().color().lightness() < 128


def _dot_icon(colour: str, side: int = 10) -> QtGui.QIcon:
    """A filled round dot of that colour (TagMender's dot_icon); an empty one for none."""
    px = QtGui.QPixmap(side * 2, side * 2)
    px.fill(QtGui.QColor(0, 0, 0, 0))
    c = dst.dot(colour)
    if c:
        p = QtGui.QPainter(px)
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        p.setPen(QtCore.Qt.PenStyle.NoPen)
        p.setBrush(QtGui.QColor(c))
        p.drawEllipse(2, 2, side * 2 - 4, side * 2 - 4)
        p.end()
    px.setDevicePixelRatio(2.0)
    return QtGui.QIcon(px)


def _items_and_colours():
    items = dst.load(_own('destinations'))
    profiles = dst.tagmender_profiles() if _own('tagmender_colours') else None
    return items, dst.colours(items, profiles)


# ---- each album its own folder ---------------------------------------------------------------
def _default() -> dict:
    """Picard's own folder and naming script: where an album with none of its own saves."""
    s = _setting()
    return {'path': str(s['move_files_to'] or ''), 'script': str(s['active_file_naming_script_id'] or '')}


def _album_view(window):
    views = getattr(getattr(window, 'panel', None), '_views', None)
    return views[1] if views and len(views) > 1 else None


def _album_of(obj):
    """The album an album, track or file in it belongs to (None: a cluster, an unmatched file)."""
    try:
        from picard.album import Album
    except ImportError:
        return None
    if isinstance(obj, Album):
        return obj
    for o in (obj, getattr(obj, 'parent_item', None)):        # a track; a file in a track
        album = getattr(o, 'album', None)
        if isinstance(album, Album):
            return album
    return None


def _key(album) -> str:
    return str(getattr(album, 'id', '') or id(album))


def _title(album) -> str:
    try:
        return str(album.metadata['album'] or '') or _key(album)
    except Exception:
        return _key(album)


def _selected_albums(window) -> list:
    """The albums selected in the right pane (a track selected: its album)."""
    view = _album_view(window)
    out = []
    for item in (view.selectedItems() if view is not None else ()):
        album = _album_of(getattr(item, 'obj', None))
        if album is not None and all(album is not a for a in out):
            out.append(album)
    return out


def _assign(albums, path: str, at: int = -1) -> None:
    """ALBUMS save to folder PATH (your folder AT: with the naming script linked to it)."""
    items = dst.load(_own('destinations'))
    sid = dst.linked_script(items[at], _setting()['file_renaming_scripts']) if 0 <= at < len(items) else ''
    default = _default()
    for album in albums:
        k = _key(album)
        _ALBUMS[k] = dst.chosen(_ALBUMS.get(k), default, path, sid)
    if _own('move_on_choose') and not _setting()['move_files']:
        _setting()['move_files'] = True
    log = _log()
    if log:
        log.info('Destination Switcher: %s saves to %s%s', ', '.join(_title(a) for a in albums), path,
                 f' with naming script {sid}' if sid else '')
    _changed()


def _changed() -> None:
    _retint()
    if _BAR is not None:
        _BAR.rebuild()


def _retint() -> None:
    """Each album in the right pane tinted with the colour of the folder it saves to; albums no
    longer there forget their folder."""
    global _RETINT_DUE
    _RETINT_DUE = False
    view = _album_view(getattr(getattr(_API, 'tagger', None), 'window', None)) if _API else None
    if view is None:
        return
    items, colours = _items_and_colours()
    on, dark, default, present = bool(_own('tint_albums')), _dark(view), _default(), set()
    for i in range(view.topLevelItemCount()):
        item = view.topLevelItem(i)
        album = _album_of(getattr(item, 'obj', None))
        if album is None:
            continue
        k = _key(album)
        present.add(k)
        there = dst.effective(_ALBUMS.get(k), default)
        at = dst.index_of(items, there['path'], there['script'])
        wash = dst.tint(colours[at], dark) if on and at >= 0 else ''
        brush = QtGui.QBrush(QtGui.QColor(wash)) if wash else QtGui.QBrush()
        for c in range(view.columnCount()):
            if item.background(c) != brush:
                item.setBackground(c, brush)
        _mark_column(view, item, album)
    for k in [k for k in _ALBUMS if k not in present]:
        _ALBUMS.pop(k, None)


def _where(album) -> tuple[str, str, bool, dict]:
    """(folder name, colour, own?, {"path", "script"}) of where ALBUM saves: the name you gave
    that folder (none named: the folder's own name)."""
    own = _ALBUMS.get(_key(album))
    there = dst.effective(own, _default())
    items, colours = _items_and_colours()
    at = dst.index_of(items, there['path'], there['script'])
    name = dst.label(items[at]) if at >= 0 else (dst.default_name(there['path']) if there['path'] else '')
    return name, (colours[at] if at >= 0 else ''), bool(own), there


def _column_text(obj) -> str:
    """The "Saves to" column: an album's folder (tracks and files: nothing, their album says)."""
    try:
        from picard.album import Album
    except ImportError:
        return ''
    if not isinstance(obj, Album):
        return ''
    return _where(obj)[0]


def _column_index(view):
    try:
        return view.columns.pos(COLUMN_KEY)
    except Exception:
        return -1


def _headers_updated() -> None:
    try:
        from picard.ui.itemviews.events import header_events
        header_events.headers_updated.emit()
    except Exception:
        pass


def _add_column() -> None:
    """A "Saves to" column in the right pane: each album's folder, with its colour."""
    try:
        from picard.ui.itemviews.custom_columns import make_callable_column, registry
        registry.register(make_callable_column(COLUMN_TITLE, COLUMN_KEY, _column_text, width=120),
                          add_to={'ALBUM_VIEW'})
    except Exception:
        log = _log()
        if log:
            log.error('Destination Switcher: the "Saves to" column could not be added', exc_info=True)
        return
    _headers_updated()


def _remove_column() -> None:
    try:
        from picard.ui.itemviews.custom_columns import registry
        registry.unregister(COLUMN_KEY)
    except Exception:
        return
    _headers_updated()


def _mark_column(view, item, album) -> None:
    """The "Saves to" cell of ALBUM: folder name, a dot of its colour, its path and naming script
    on hover; italic while the album follows every album (bold: a folder of its own)."""
    c = _column_index(view)
    if c < 0:
        return
    name, colour, own, there = _where(album)
    if item.text(c) != name:
        item.setText(c, name)
    item.setIcon(c, _dot_icon(colour) if colour else QtGui.QIcon())
    font = QtGui.QFont(item.font(c))
    font.setItalic(not own)
    font.setBold(own)
    item.setFont(c, font)
    title = ''
    try:
        title = dict(dst.scripts(_setting()['file_renaming_scripts'])).get(there['script'], '')
    except Exception:
        pass
    item.setToolTip(c, '\n'.join(x for x in (
        f"{name} - {'this album alone' if own else 'as every album'}",
        there['path'], f'Naming script: {title}' if title else '') if x))


def _retint_later(*_args) -> None:
    global _RETINT_DUE
    if not _RETINT_DUE:
        _RETINT_DUE = True
        QtCore.QTimer.singleShot(0, _retint)


class _Overlay:
    """Picard's settings with an album's own folder and naming script in place of Picard's."""

    def __init__(self, base, over):
        self._base, self._over = base, over

    def __getitem__(self, key):
        return self._over[key] if key in self._over else self._base[key]

    def __contains__(self, key):
        return key in self._over or key in self._base

    def get(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            return default

    def __getattr__(self, name):
        return getattr(self._base, name)


def _patch_saving() -> None:
    """When Picard names a file of an album with a folder of its own, it is given that folder
    and naming script (Picard's own settings unchanged)."""
    global _ORIG_MAKE_FILENAME
    if _ORIG_MAKE_FILENAME is not None:
        return
    try:
        from picard.config import get_config
        from picard.file import File
    except ImportError:
        return
    original = File.make_filename

    def make_filename(self, filename, metadata, settings=None, naming_format=None):
        try:
            album = _album_of(self) if _ALBUMS else None
            own = _ALBUMS.get(_key(album)) if album is not None else None
            base = get_config().setting
            if own and naming_format is None and (settings is None or settings is base):
                there = dst.effective(own, {'path': base['move_files_to'],
                                            'script': base['active_file_naming_script_id']})
                settings = _Overlay(base, {'move_files_to': there['path'],
                                           'active_file_naming_script_id': there['script']})
        except Exception:
            log = _log()
            if log:
                log.error('Destination Switcher: an album\'s own folder could not be used', exc_info=True)
        return original(self, filename, metadata, settings, naming_format)

    File.make_filename = make_filename
    _ORIG_MAKE_FILENAME = original


def _after_save(file, old_filename, new_filename) -> None:
    """A file was saved (on Picard's saving thread). When it moved and its album's old folder
    now holds no audio, what is left there goes to the album's new folder (sweep)."""
    if not new_filename or not old_filename or not _own('sweep_album_folder'):
        return
    old_dir, new_dir = os.path.dirname(old_filename), os.path.dirname(new_filename)
    if os.path.normpath(old_dir) == os.path.normpath(new_dir):
        return
    s = _setting()
    album = _album_of(file)
    key = _key(album) if album is not None else f'file:{old_dir}'
    log = _log()
    with _SWEEP_LOCK:
        rec = _SWEEP.setdefault(key, {'old': set(), 'new': set()})
        rec['old'].add(old_dir)
        rec['new'].add(new_dir)
        old_root, new_root = sweep.album_root(rec['old']), sweep.album_root(rec['new'])
        moves = sweep.plan(old_root, new_root, rec['old'], rec['new'])
        if not moves:
            return
        moved, skipped = sweep.apply(moves, overwrite=bool(s['move_overwrite_existing_files']))
        if log:
            log.info('Destination Switcher: moved %d item(s) left in %s to %s%s', len(moved), old_root,
                     new_root, f' ({len(skipped)} already there, left behind)' if skipped else '')
        if s['delete_empty_dirs'] and not skipped:
            _remove_empty_upwards(old_root)
        _SWEEP.pop(key, None)


def _remove_empty_upwards(folder: str) -> None:
    """FOLDER and its parents removed while empty, as Picard removes a moved file's folders."""
    try:
        from picard.util import emptydir
    except ImportError:
        sweep.remove_if_empty(folder)
        return
    sweep.remove_if_empty(folder)          # (its empty sub-folders, which emptydir does not take)
    head = folder
    try:
        while head:
            if os.path.isdir(head):
                emptydir.rm_empty_dir(head)
            head, tail = os.path.split(head)
            if not tail:
                break
    except (OSError, emptydir.SkipRemoveDir):
        pass


def _patch_sweep() -> None:
    global _ORIG_SAVE_AND_RENAME
    if _ORIG_SAVE_AND_RENAME is not None:
        return
    try:
        from picard.file import File
    except ImportError:
        return
    original = File._save_and_rename

    def _save_and_rename(self, old_filename, metadata):
        new_filename = original(self, old_filename, metadata)
        try:
            _after_save(self, old_filename, new_filename)
        except Exception:
            log = _log()
            if log:
                log.error('Destination Switcher: the album folder\'s other files could not be moved',
                          exc_info=True)
        return new_filename

    File._save_and_rename = _save_and_rename
    _ORIG_SAVE_AND_RENAME = original


def _unpatch_sweep() -> None:
    global _ORIG_SAVE_AND_RENAME
    if _ORIG_SAVE_AND_RENAME is None:
        return
    try:
        from picard.file import File
        File._save_and_rename = _ORIG_SAVE_AND_RENAME
    except ImportError:
        pass
    _ORIG_SAVE_AND_RENAME = None


def _unpatch_saving() -> None:
    global _ORIG_MAKE_FILENAME
    if _ORIG_MAKE_FILENAME is None:
        return
    try:
        from picard.file import File
        File.make_filename = _ORIG_MAKE_FILENAME
    except ImportError:
        pass
    _ORIG_MAKE_FILENAME = None


def _folder_menu(parent, albums) -> QtWidgets.QMenu:
    """Your folders, to choose one for ALBUMS (a right-click on albums)."""
    menu = QtWidgets.QMenu(parent)
    items, colours = _items_and_colours()
    default = _default()
    shown = {(dst.effective(_ALBUMS.get(_key(a)), default)['path'],
              dst.effective(_ALBUMS.get(_key(a)), default)['script']) for a in albums}
    for i, (d, colour) in enumerate(zip(items, colours)):
        act = menu.addAction(_dot_icon(colour), dst.label(d))
        act.setCheckable(True)
        act.setChecked(len(shown) == 1 and dst.index_of(items, *next(iter(shown))) == i)
        act.triggered.connect(partial(_assign, albums, d['path'], i))
    if any(_key(a) in _ALBUMS for a in albums):
        menu.addSeparator()
        menu.addAction('Same as every album').triggered.connect(partial(_forget, albums))
    if not items:
        menu.addAction('Name your folders…').triggered.connect(
            partial(_open_options, getattr(_API.tagger, 'window', None)))
    return menu


class SaveToAction(BaseAction):
    """Right-click on albums: Save to folder… - one of your folders for them alone."""
    TITLE = 'Save to folder…'

    def callback(self, objs):
        albums = []
        for obj in objs or ():
            album = _album_of(obj)
            if album is not None and all(album is not a for a in albums):
                albums.append(album)
        if albums:
            _folder_menu(getattr(self.tagger, 'window', None), albums).exec(QtGui.QCursor.pos())


def _untint() -> None:
    view = _album_view(getattr(getattr(_API, 'tagger', None), 'window', None)) if _API else None
    for i in range(view.topLevelItemCount() if view is not None else 0):
        item = view.topLevelItem(i)
        if _album_of(getattr(item, 'obj', None)) is not None:
            for c in range(view.columnCount()):
                item.setBackground(c, QtGui.QBrush())


def _forget(albums) -> None:
    for album in albums:
        _ALBUMS.pop(_key(album), None)
    _changed()


class SwitcherBar(QtWidgets.QFrame):
    """● Save to [folder ▾] [Browse…] [✓ Move files] [✓ Rename files] │ Naming script [script ▾] [Edit…]
    tinted with the colour of the folder Picard saves to."""

    def __init__(self, window, parent=None):
        super().__init__(parent)
        self.colour = None              # (set by rebuild: no repaint before)
        self.setObjectName(BAR_NAME)
        self.window_ = window
        self._building = False
        row = QtWidgets.QHBoxLayout(self)
        row.setContentsMargins(8, 3, 6, 3)
        row.setSpacing(6)
        self.dot = QtWidgets.QLabel(self)
        row.addWidget(self.dot)
        self.save_label = QtWidgets.QLabel('Save to:', self)
        row.addWidget(self.save_label)
        self.dest_combo = QtWidgets.QComboBox(self)
        self.dest_combo.setSizeAdjustPolicy(QtWidgets.QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.dest_combo.setMinimumContentsLength(10)
        self.dest_combo.activated.connect(self._dest_chosen)
        row.addWidget(self.dest_combo)
        self.browse_button = QtWidgets.QToolButton(self)
        self.browse_button.setText('Browse…')
        self.browse_button.setToolTip('Save to another folder (not added to your list)')
        self.browse_button.clicked.connect(self._browse)
        row.addWidget(self.browse_button)
        self.move_box = QtWidgets.QCheckBox('Move files', self)
        self.move_box.setToolTip("Picard's Move files (Options > File Naming)")
        self.move_box.toggled.connect(partial(self._switch, 'move_files'))
        self.rename_box = QtWidgets.QCheckBox('Rename files', self)
        self.rename_box.setToolTip("Picard's Rename files (Options > File Naming)")
        self.rename_box.toggled.connect(partial(self._switch, 'rename_files'))
        row.addWidget(self.move_box)
        row.addWidget(self.rename_box)
        self.script_sep = QtWidgets.QFrame(self)
        self.script_sep.setFrameShape(QtWidgets.QFrame.Shape.VLine)
        self.script_sep.setFrameShadow(QtWidgets.QFrame.Shadow.Sunken)
        row.addWidget(self.script_sep)
        self.script_label = QtWidgets.QLabel('Naming script:', self)
        row.addWidget(self.script_label)
        self.script_combo = QtWidgets.QComboBox(self)
        self.script_combo.setSizeAdjustPolicy(QtWidgets.QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.script_combo.setMinimumContentsLength(10)
        self.script_combo.activated.connect(self._script_chosen)
        row.addWidget(self.script_combo)
        self.edit_button = QtWidgets.QToolButton(self)
        self.edit_button.setText('Edit…')
        self.edit_button.setToolTip("Picard's file naming script editor")
        self.edit_button.clicked.connect(self._edit_scripts)
        row.addWidget(self.edit_button)
        row.addStretch(1)
        self.colour = ''
        self.rebuild()

    # ---- showing Picard's settings ----------------------------------------------------------
    def rebuild(self) -> None:
        self._building = True
        try:
            s = _setting()
            albums = _selected_albums(self.window_)
            default = _default()
            shown = [dst.effective(_ALBUMS.get(_key(a)), default) for a in albums] or [default]
            folders = {c['path'] for c in shown}
            scripts = {c['script'] for c in shown}
            current, active = shown[0]['path'], shown[0]['script']
            self.save_label.setText(dst.scope_label([_title(a) for a in albums]))
            items, colours = _items_and_colours()
            titles = dict(dst.scripts(s['file_renaming_scripts']))
            self.dest_combo.clear()
            for i, (d, colour) in enumerate(zip(items, colours)):
                # (data: the folder's place in your list - two of yours may share one folder)
                self.dest_combo.addItem(_dot_icon(colour), dst.label(d), i)
                sid = dst.linked_script(d, s['file_renaming_scripts'])
                tip = d['path'] + (f'\nnaming script: {titles.get(sid, sid)}' if sid else '')
                self.dest_combo.setItemData(self.dest_combo.count() - 1, tip, QtCore.Qt.ItemDataRole.ToolTipRole)
            mixed = len(folders) > 1 or (len(scripts) > 1 and
                                         len({dst.index_of(items, c['path'], c['script']) for c in shown}) > 1)
            at = -1 if mixed else dst.index_of(items, current, active)
            if mixed:
                self.dest_combo.insertItem(0, _dot_icon(''), '(several folders)', MIXED)
            elif at < 0 and current:
                # (a folder that is none of yours: shown as it is, first, uncoloured)
                self.dest_combo.insertItem(0, _dot_icon(''), f'Other: {dst.default_name(current)}', current)
                self.dest_combo.setItemData(0, current, QtCore.Qt.ItemDataRole.ToolTipRole)
            if not items:
                self.dest_combo.addItem('Name your folders…', None)
            if any(_key(a) in _ALBUMS for a in albums):
                self.dest_combo.insertSeparator(self.dest_combo.count())
                self.dest_combo.addItem(_dot_icon(''), 'Same as every album', SAME)
            pick = MIXED if mixed else (at if at >= 0 else current)
            self.dest_combo.setCurrentIndex(max(0, self.dest_combo.findData(pick) if (mixed or current) else 0))
            self.dest_combo.setToolTip(
                (f'Where the selected albums go: {current or "(none)"}\nDeselect them to choose for every album'
                 if albums else f"Where every album goes (Picard's destination directory): {current or '(none)'}"
                 '\nSelect albums in the right pane to choose for them alone'))
            self.colour = colours[at] if at >= 0 else ''
            self._paint()
            self.move_box.setChecked(bool(s['move_files']))
            self.rename_box.setChecked(bool(s['rename_files']))
            for w in (self.move_box, self.rename_box):
                w.setVisible(bool(_own('show_switches')))
            self.script_combo.clear()
            if len(scripts) > 1:
                self.script_combo.addItem('(several scripts)', MIXED)
            for sid, title in dst.scripts(s['file_renaming_scripts']):
                self.script_combo.addItem(title, sid)
                if sid == active and len(scripts) == 1:
                    self.script_combo.setCurrentIndex(self.script_combo.count() - 1)
            self.script_combo.setToolTip('The naming script of the selected albums' if albums
                                         else "Picard's active file naming script: every album's")
            for w in (self.script_sep, self.script_label, self.script_combo, self.edit_button):
                w.setVisible(bool(_own('show_scripts')))
        finally:
            self._building = False

    def _paint(self) -> None:
        """The folder's colour: a tinted bar with a stripe and a dot of it (none: Picard's own)."""
        if getattr(self, '_painting', False):
            return
        self._painting = True
        try:
            # (light or dark: the window's palette - the bar's own is its style sheet's)
            dark = _dark(self.window_ if self.window_ is not None else self)
            wash, dot = dst.tint(self.colour, dark), dst.dot(self.colour)
            key = (self.colour, dark)
            if getattr(self, '_painted', None) != key:
                self._painted = key
                self.dot.setPixmap(_dot_icon(self.colour, 7).pixmap(14, 14))
                self.dot.setVisible(bool(dot))
                sheet = (f'QFrame#{BAR_NAME} {{ background-color: {wash}; border-left: 4px solid {dot}; }}'
                         if wash else '')
                if self.styleSheet() != sheet:
                    self.setStyleSheet(sheet)
        finally:
            self._painting = False

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if event.type() == QtCore.QEvent.Type.PaletteChange and getattr(self, 'colour', None) is not None:
            QtCore.QTimer.singleShot(0, self._paint)      # (light / dark theme switched)

    def setting_changed(self, name, _old, _new) -> None:
        if name in WATCHED and not self._building:
            QtCore.QTimer.singleShot(0, self.rebuild)
            _retint_later()

    def selection_changed(self) -> None:
        QtCore.QTimer.singleShot(0, self.rebuild)

    # ---- changing them ----------------------------------------------------------------------
    def _set(self, key, value) -> None:
        s = _setting()
        if s[key] != value:
            s[key] = value

    def _dest_chosen(self, index) -> None:
        if self._building:
            return
        data = self.dest_combo.itemData(index)
        if data is None or data == '':
            _open_options(self.window_)
            self.rebuild()
            return
        if data == MIXED:
            return
        if data == SAME:
            _forget(_selected_albums(self.window_))
            return
        items = dst.load(_own('destinations'))
        if isinstance(data, int) and 0 <= data < len(items):
            self._choose(items[data]['path'], data)
        else:
            self._choose(str(data))

    def _choose(self, path: str, at: int | None = None) -> None:
        """Folder PATH (your folder AT) for the selected albums - none selected: for every album."""
        items = dst.load(_own('destinations'))
        albums = _selected_albums(self.window_)
        if at is None:
            at = dst.index_of(items, path, str(_setting()['active_file_naming_script_id'] or ''))
        if albums:
            _assign(albums, path, at)
            return
        self._set('move_files_to', path)
        if _own('move_on_choose'):
            self._set('move_files', True)
        # the naming script linked to that folder, when you gave it one
        sid = dst.linked_script(items[at], _setting()['file_renaming_scripts']) if at >= 0 else ''
        if sid:
            self._set('active_file_naming_script_id', sid)
        log = _log()
        if log:
            log.info('Destination Switcher: every album saves to %s%s', path,
                     f' with naming script {sid}' if sid else '')
        _changed()

    def _browse(self) -> None:
        albums = _selected_albums(self.window_)
        start = (dst.effective(_ALBUMS.get(_key(albums[0])), _default())['path'] if albums
                 else str(_setting()['move_files_to'] or '')) or os.path.expanduser('~')
        path = QtWidgets.QFileDialog.getExistingDirectory(self.window_, 'Save to', start)
        if path:
            self._choose(path)

    def _switch(self, key, on) -> None:
        if not self._building:
            self._set(key, bool(on))

    def _script_chosen(self, index) -> None:
        if self._building:
            return
        sid = self.script_combo.itemData(index)
        if not sid or sid == MIXED:
            return
        albums = _selected_albums(self.window_)
        if albums:
            default = _default()
            for album in albums:
                k = _key(album)
                _ALBUMS[k] = {'path': dst.effective(_ALBUMS.get(k), default)['path'], 'script': str(sid)}
            _changed()
        else:
            self._set('active_file_naming_script_id', str(sid))

    def _edit_scripts(self) -> None:
        opener = getattr(self.window_, 'open_file_naming_script_editor', None)
        if opener:
            opener()


def _open_options(window) -> None:
    show = getattr(window, 'show_options', None)
    if show:
        try:
            show('destination_switcher')
        except Exception:
            show()


# ---- placing the bar -------------------------------------------------------------------------
def _pane_container(window, which: str):
    """The container Picard puts each of its two panes in (its filter box above the view):
    the left (files) or right (albums) one; None when this Picard is built otherwise."""
    panel = getattr(window, 'panel', None)
    views = getattr(panel, '_views', None)
    if not views or len(views) < 2:
        return None
    view = views[0] if which == 'left' else views[1]
    container = view.parentWidget()
    layout = container.layout() if container is not None else None
    return container if isinstance(layout, QtWidgets.QVBoxLayout) else None


def _place() -> None:
    """Put the bar where the settings say (a pane Picard's build lacks: a toolbar instead)."""
    global _BAR, _HOST
    window = getattr(_API.tagger, 'window', None)
    if window is None:
        return
    _remove()
    bar = SwitcherBar(window)
    where = str(_own('placement') or 'right')
    container = _pane_container(window, where) if where in ('left', 'right') else None
    if container is not None:
        bar.setParent(container)
        container.layout().insertWidget(0, bar)
    else:
        host = QtWidgets.QToolBar('Destination and naming script', window)
        host.setObjectName(TOOLBAR_NAME)
        host.addWidget(bar)
        window.addToolBar(QtCore.Qt.ToolBarArea.TopToolBarArea, host)
        _HOST = host
    _BAR = bar
    hooks = [(_API.global_config.setting.setting_changed, bar.setting_changed)]
    view = _album_view(window)
    if view is not None:
        hooks += [(view.itemSelectionChanged, bar.selection_changed),
                  (view.model().rowsInserted, _retint_later)]
    for signal, slot in hooks:
        signal.connect(slot)
    _HOOKS[:] = hooks
    _retint_later()


def _remove() -> None:
    global _BAR, _HOST
    bar, host = _BAR, _HOST
    _BAR = _HOST = None
    for signal, slot in _HOOKS:
        try:
            signal.disconnect(slot)
        except Exception:
            pass
    _HOOKS.clear()
    if bar is not None:
        bar.hide()
        bar.setParent(None)
        bar.deleteLater()
    if host is not None:
        try:
            host.parentWidget().removeToolBar(host)
        except Exception:
            pass
        host.deleteLater()


# ---- options -------------------------------------------------------------------------------
COLOUR_CHOICES = [('', 'Automatic'), ('none', 'None')] + [(k, v[0]) for k, v in dst.TINTS.items()]


class DestinationOptionsPage(OptionsPage):
    NAME = 'destination_switcher'
    TITLE = 'Destination Switcher'
    PARENT = 'plugins'

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        layout = QtWidgets.QVBoxLayout(self)
        intro = QtWidgets.QLabel(
            'The folders the "Save to" dropdown offers, in this order. With albums selected in the '
            'right pane, choosing one is for those albums alone (right-click: Save to folder… too); '
            'with none selected, it sets Picard\'s destination directory (Options > File Naming) - '
            'every other album\'s - and the naming script you give it.', self)
        intro.setWordWrap(True)
        layout.addWidget(intro)
        self.table = QtWidgets.QTableWidget(0, 4, self)
        self.table.setHorizontalHeaderLabels(['Name', 'Folder', 'Naming script', 'Colour'])
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        layout.addWidget(self.table, 1)
        row = QtWidgets.QHBoxLayout()
        for text, slot in (('Add folder…', self._add), ('Change folder…', self._change),
                           ('Remove', self._remove), ('Up', partial(self._move, -1)),
                           ('Down', partial(self._move, 1))):
            b = QtWidgets.QPushButton(text, self)
            b.clicked.connect(slot)
            row.addWidget(b)
        row.addStretch(1)
        layout.addLayout(row)
        hint = QtWidgets.QLabel(
            'For example: Lossless → /music/lossless, Lossy → /music/lossy. Double-click a '
            'name to rename it. "Keep current" leaves the naming script as it is. Colour "Automatic" '
            'colours a folder as TagMender colours its profiles.', self)
        hint.setWordWrap(True)
        layout.addWidget(hint)
        place = QtWidgets.QHBoxLayout()
        place.addWidget(QtWidgets.QLabel('Show the switcher:', self))
        self.placement_combo = QtWidgets.QComboBox(self)
        for key, text in PLACEMENTS:
            self.placement_combo.addItem(text, key)
        place.addWidget(self.placement_combo, 1)
        layout.addLayout(place)
        self.tagmender_box = QtWidgets.QCheckBox(
            "Automatic colours: a folder a TagMender profile saves to takes that profile's colour", self)
        self.move_on_choose_box = QtWidgets.QCheckBox('Choosing a folder turns Move files on', self)
        self.show_switches_box = QtWidgets.QCheckBox('Show Move files and Rename files', self)
        self.show_scripts_box = QtWidgets.QCheckBox('Show the naming script dropdown', self)
        self.tint_box = QtWidgets.QCheckBox(
            "Colour each album in the right pane with the colour of the folder it saves to", self)
        self.sweep_box = QtWidgets.QCheckBox(
            "Move everything left in an album's folder with it (covers/, logs, booklets)", self)
        self.sweep_box.setToolTip(
            "Picard's \"Move additional files\" looks only beside each audio file: in a set of\n"
            "discs the covers folder, rip log and booklet beside CD1/ and CD2/ stay behind.\n"
            "With this on, once an album's old folder holds no audio any more, whatever is\n"
            "left in it - files and folders - is moved into the album's new folder.")
        for w in (self.sweep_box, self.tint_box, self.tagmender_box, self.move_on_choose_box, self.show_switches_box, self.show_scripts_box):
            layout.addWidget(w)

    def _combo(self, choices, value):
        combo = QtWidgets.QComboBox(self.table)
        for key, text in choices:
            combo.addItem(text, key)
        at = combo.findData(value or '')
        if at < 0 and value:
            combo.addItem(f'(missing {value[:8]})', value)
            at = combo.count() - 1
        combo.setCurrentIndex(max(0, at))
        return combo

    def _row(self, name, path, script='', colour='') -> None:
        r = self.table.rowCount()
        self.table.insertRow(r)
        self.table.setItem(r, 0, QtWidgets.QTableWidgetItem(name))
        item = QtWidgets.QTableWidgetItem(path)
        item.setFlags(item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
        self.table.setItem(r, 1, item)
        scripts = [('', 'Keep current')] + dst.scripts(_setting()['file_renaming_scripts'])
        self.table.setCellWidget(r, 2, self._combo(scripts, script))
        combo = self._combo(COLOUR_CHOICES, colour)
        for i in range(combo.count()):
            combo.setItemIcon(i, _dot_icon(combo.itemData(i) or ''))
        self.table.setCellWidget(r, 3, combo)

    def _cell(self, r, c) -> str:
        combo = self.table.cellWidget(r, c)
        return str(combo.currentData() or '') if combo is not None else ''

    def _script_at(self, r) -> str:
        return self._cell(r, 2)

    def _pick(self, start='') -> str:
        return QtWidgets.QFileDialog.getExistingDirectory(self, 'Folder', start or os.path.expanduser('~'))

    def _add(self) -> None:
        path = self._pick(str(_setting()['move_files_to'] or ''))
        if path:
            self._row(dst.default_name(path), path)

    def _change(self) -> None:
        r = self.table.currentRow()
        if r < 0:
            return
        path = self._pick(self.table.item(r, 1).text())
        if path:
            self.table.item(r, 1).setText(path)

    def _remove(self) -> None:
        r = self.table.currentRow()
        if r >= 0:
            self.table.removeRow(r)

    def _values(self, r) -> list:
        return [self.table.item(r, 0).text(), self.table.item(r, 1).text(), self._cell(r, 2), self._cell(r, 3)]

    def _move(self, step) -> None:
        r = self.table.currentRow()
        to = r + step
        if r < 0 or not 0 <= to < self.table.rowCount():
            return
        a, b = self._values(r), self._values(to)
        for row, v in ((r, b), (to, a)):
            self.table.item(row, 0).setText(v[0])
            self.table.item(row, 1).setText(v[1])
            for c in (2, 3):
                combo = self.table.cellWidget(row, c)
                combo.setCurrentIndex(max(0, combo.findData(v[c])))
        self.table.setCurrentCell(to, 0)

    def load(self):
        self.table.setRowCount(0)
        for d in dst.load(_own('destinations')):
            self._row(d['name'], d['path'], d.get('script', ''), d.get('colour', ''))
        i = self.placement_combo.findData(str(_own('placement') or 'right'))
        self.placement_combo.setCurrentIndex(max(0, i))
        self.tagmender_box.setChecked(bool(_own('tagmender_colours')))
        self.move_on_choose_box.setChecked(bool(_own('move_on_choose')))
        self.show_switches_box.setChecked(bool(_own('show_switches')))
        self.show_scripts_box.setChecked(bool(_own('show_scripts')))
        self.tint_box.setChecked(bool(_own('tint_albums')))
        self.sweep_box.setChecked(bool(_own('sweep_album_folder')))

    def save(self):
        items = [dict(zip(('name', 'path', 'script', 'colour'), self._values(r)))
                 for r in range(self.table.rowCount())]
        moved = str(self.placement_combo.currentData() or 'right') != str(_own('placement') or 'right')
        _set_own('destinations', dst.dump(items))
        _set_own('placement', self.placement_combo.currentData() or 'right')
        _set_own('tagmender_colours', self.tagmender_box.isChecked())
        _set_own('move_on_choose', self.move_on_choose_box.isChecked())
        _set_own('show_switches', self.show_switches_box.isChecked())
        _set_own('show_scripts', self.show_scripts_box.isChecked())
        _set_own('tint_albums', self.tint_box.isChecked())
        _set_own('sweep_album_folder', self.sweep_box.isChecked())
        _retint_later()
        if moved or _BAR is None:
            QtCore.QTimer.singleShot(0, _place)
        else:
            _BAR.rebuild()


def enable(api) -> None:
    """Picard 3 entry point."""
    global _API
    _API = api
    for key, default in DEFAULTS.items():
        try:
            api.plugin_config.register_option(key, default)
        except Exception:
            pass
    api.register_options_page(DestinationOptionsPage)
    try:
        api.register_album_action(SaveToAction)
    except Exception:
        pass
    _patch_saving()
    _patch_sweep()
    _add_column()
    try:
        _place()
    except Exception:
        log = _log()
        if log:
            log.error('Destination Switcher: the bar could not be added', exc_info=True)


def disable() -> None:
    _unpatch_saving()
    _unpatch_sweep()
    _ALBUMS.clear()
    _remove_column()
    try:
        _remove()
        _untint()
    except Exception:
        pass
