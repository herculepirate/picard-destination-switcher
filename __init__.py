"""Destination Switcher: where Picard saves, and with which file naming script, from a bar above
one of Picard's panes (or a toolbar), coloured as TagMender colours its profiles.

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

from picard.plugin3.api import OptionsPage

try:
    from . import destinations as dst
except ImportError:  # run outside Picard (tests)
    import destinations as dst

# the plugin's own settings, with their defaults
DEFAULTS = {
    'destinations': '[]',          # JSON: [{"name", "path", "script", "colour"}, ...]
    'placement': 'right',          # right (above the album pane) | left (above the files pane) | toolbar
    'tagmender_colours': True,     # automatic colours: TagMender's profile for that folder first
    'move_on_choose': True,        # choosing a folder turns Move files on
    'show_switches': True,         # Move files / Rename files on the bar
    'show_scripts': True,          # the naming script dropdown
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
            current = str(s['move_files_to'] or '')
            items, colours = _items_and_colours()
            titles = dict(dst.scripts(s['file_renaming_scripts']))
            self.dest_combo.clear()
            for d, colour in zip(items, colours):
                self.dest_combo.addItem(_dot_icon(colour), dst.label(d), d['path'])
                sid = dst.linked_script(d, s['file_renaming_scripts'])
                tip = d['path'] + (f'\nnaming script: {titles.get(sid, sid)}' if sid else '')
                self.dest_combo.setItemData(self.dest_combo.count() - 1, tip, QtCore.Qt.ItemDataRole.ToolTipRole)
            at = dst.index_of(items, current)
            if at < 0 and current:
                # (Picard's folder is none of yours: shown as it is, first, uncoloured)
                self.dest_combo.insertItem(0, _dot_icon(''), f'Other: {dst.default_name(current)}', current)
                self.dest_combo.setItemData(0, current, QtCore.Qt.ItemDataRole.ToolTipRole)
            if not items:
                self.dest_combo.addItem('Name your folders…', None)
            self.dest_combo.setCurrentIndex(max(0, self.dest_combo.findData(current) if current else 0))
            self.dest_combo.setToolTip(f"Picard's destination directory: {current or '(none)'}")
            self.colour = colours[at] if at >= 0 else ''
            self._paint()
            self.move_box.setChecked(bool(s['move_files']))
            self.rename_box.setChecked(bool(s['rename_files']))
            for w in (self.move_box, self.rename_box):
                w.setVisible(bool(_own('show_switches')))
            self.script_combo.clear()
            active = str(s['active_file_naming_script_id'] or '')
            for sid, title in dst.scripts(s['file_renaming_scripts']):
                self.script_combo.addItem(title, sid)
                if sid == active:
                    self.script_combo.setCurrentIndex(self.script_combo.count() - 1)
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

    # ---- changing them ----------------------------------------------------------------------
    def _set(self, key, value) -> None:
        s = _setting()
        if s[key] != value:
            s[key] = value

    def _dest_chosen(self, index) -> None:
        if self._building:
            return
        path = self.dest_combo.itemData(index)
        if not path:
            _open_options(self.window_)
            self.rebuild()
            return
        self._choose(str(path))

    def _choose(self, path: str) -> None:
        self._set('move_files_to', path)
        if _own('move_on_choose'):
            self._set('move_files', True)
        # the naming script linked to that folder, when you gave it one
        items = dst.load(_own('destinations'))
        at = dst.index_of(items, path)
        sid = dst.linked_script(items[at], _setting()['file_renaming_scripts']) if at >= 0 else ''
        if sid:
            self._set('active_file_naming_script_id', sid)
        log = _log()
        if log:
            log.info('Destination Switcher: saving to %s%s', path, f' with naming script {sid}' if sid else '')
        self.rebuild()

    def _browse(self) -> None:
        start = str(_setting()['move_files_to'] or os.path.expanduser('~'))
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
        if sid:
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
    _API.global_config.setting.setting_changed.connect(bar.setting_changed)


def _remove() -> None:
    global _BAR, _HOST
    bar, host = _BAR, _HOST
    _BAR = _HOST = None
    if bar is not None:
        try:
            _API.global_config.setting.setting_changed.disconnect(bar.setting_changed)
        except Exception:
            pass
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
            'The folders the "Save to" dropdown offers, in this order. Choosing one sets Picard\'s '
            'destination directory (Options > File Naming), and the naming script you give it.', self)
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
        for w in (self.tagmender_box, self.move_on_choose_box, self.show_switches_box, self.show_scripts_box):
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
        _place()
    except Exception:
        log = _log()
        if log:
            log.error('Destination Switcher: the bar could not be added', exc_info=True)


def disable() -> None:
    try:
        _remove()
    except Exception:
        pass
