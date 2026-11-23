"""Destination Switcher: where Picard saves, and with which file naming script, from a toolbar.

The toolbar shows and changes Picard's own settings - its destination directory
(move_files_to), Move files (move_files), Rename files (rename_files) and the active file
naming script (active_file_naming_script_id) - and follows them when they change anywhere else
(Options, the Options menu, a profile). The folders the "Save to" dropdown offers are yours,
named under Options > Plugins > Destination Switcher ("Lossless", "Lossy" ...).

Picard 3 has no API for main-window widgets: the toolbar is added to the window the plugin api
gives (api.tagger.window) when the plugin is enabled, and removed when it is disabled.
"""
from __future__ import annotations

import os
from functools import partial

from PyQt6 import QtCore, QtWidgets

from picard.plugin3.api import OptionsPage

try:
    from . import destinations as dst
except ImportError:  # run outside Picard (tests)
    import destinations as dst

# the plugin's own settings, with their defaults
DEFAULTS = {
    'destinations': '[]',          # JSON: [{"name": "Lossless", "path": "/music/lossless"}, ...]
    'move_on_choose': True,        # choosing a folder turns Move files on
    'show_switches': True,         # Move files / Rename files on the toolbar
    'show_scripts': True,          # the naming script dropdown
}
# Picard's settings the toolbar shows (a change to any of them redraws it)
WATCHED = {'move_files_to', 'move_files', 'rename_files', 'file_renaming_scripts',
           'active_file_naming_script_id'}
TOOLBAR_NAME = 'destination_switcher_toolbar'

_API = None
_TOOLBAR: 'DestinationToolbar | None' = None


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


class DestinationToolbar(QtWidgets.QToolBar):
    """Save to [folder ▾] [Browse…] [✓ Move files] [✓ Rename files] | Naming script [script ▾] [Edit…]"""

    def __init__(self, window):
        super().__init__('Destination and naming script', window)
        self.setObjectName(TOOLBAR_NAME)
        self.window_ = window
        self._building = False
        self._other = ''               # a folder picked with Browse… (not one of yours)

        self.addWidget(QtWidgets.QLabel(' Save to: ', self))
        self.dest_combo = QtWidgets.QComboBox(self)
        self.dest_combo.setSizeAdjustPolicy(QtWidgets.QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.dest_combo.setMinimumContentsLength(14)
        self.dest_combo.activated.connect(self._dest_chosen)
        self.addWidget(self.dest_combo)
        self.browse_button = QtWidgets.QToolButton(self)
        self.browse_button.setText('Browse…')
        self.browse_button.setToolTip('Save to another folder (not added to your list)')
        self.browse_button.clicked.connect(self._browse)
        self.addWidget(self.browse_button)
        self.move_box = QtWidgets.QCheckBox('Move files', self)
        self.move_box.setToolTip("Picard's Move files (Options > File Naming)")
        self.move_box.toggled.connect(partial(self._switch, 'move_files'))
        self.rename_box = QtWidgets.QCheckBox('Rename files', self)
        self.rename_box.setToolTip("Picard's Rename files (Options > File Naming)")
        self.rename_box.toggled.connect(partial(self._switch, 'rename_files'))
        self.switch_actions = [self.addWidget(self.move_box), self.addWidget(self.rename_box)]

        self.script_sep = self.addSeparator()
        self.script_label = QtWidgets.QLabel(' Naming script: ', self)
        self.script_combo = QtWidgets.QComboBox(self)
        self.script_combo.setSizeAdjustPolicy(QtWidgets.QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.script_combo.setMinimumContentsLength(14)
        self.script_combo.activated.connect(self._script_chosen)
        self.edit_button = QtWidgets.QToolButton(self)
        self.edit_button.setText('Edit…')
        self.edit_button.setToolTip("Picard's file naming script editor")
        self.edit_button.clicked.connect(self._edit_scripts)
        self.script_actions = [self.script_sep, self.addWidget(self.script_label),
                               self.addWidget(self.script_combo), self.addWidget(self.edit_button)]
        self.rebuild()

    # ---- showing Picard's settings ----------------------------------------------------------
    def rebuild(self) -> None:
        self._building = True
        try:
            s = _setting()
            current = str(s['move_files_to'] or '')
            items = dst.load(_own('destinations'))
            self.dest_combo.clear()
            titles = dict(dst.scripts(s['file_renaming_scripts']))
            for d in items:
                self.dest_combo.addItem(dst.label(d), d['path'])
                sid = dst.linked_script(d, s['file_renaming_scripts'])
                tip = d['path'] + (f'\nnaming script: {titles.get(sid, sid)}' if sid else '')
                self.dest_combo.setItemData(self.dest_combo.count() - 1, tip, QtCore.Qt.ItemDataRole.ToolTipRole)
            at = dst.index_of(items, current)
            if at < 0 and current:
                # (Picard's folder is none of yours: shown as it is, first)
                self.dest_combo.insertItem(0, f'Other: {dst.default_name(current)}', current)
                self.dest_combo.setItemData(0, current, QtCore.Qt.ItemDataRole.ToolTipRole)
                at = 0
            if not items:
                self.dest_combo.addItem('Name your folders…', None)
            self.dest_combo.setCurrentIndex(max(0, at))
            self.dest_combo.setToolTip(f"Picard's destination directory: {current or '(none)'}")
            self.move_box.setChecked(bool(s['move_files']))
            self.rename_box.setChecked(bool(s['rename_files']))
            for a in self.switch_actions:
                a.setVisible(bool(_own('show_switches')))
            self.script_combo.clear()
            active = str(s['active_file_naming_script_id'] or '')
            for sid, title in dst.scripts(s['file_renaming_scripts']):
                self.script_combo.addItem(title, sid)
                if sid == active:
                    self.script_combo.setCurrentIndex(self.script_combo.count() - 1)
            for a in self.script_actions:
                a.setVisible(bool(_own('show_scripts')))
        finally:
            self._building = False

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


class DestinationOptionsPage(OptionsPage):
    NAME = 'destination_switcher'
    TITLE = 'Destination Switcher'
    PARENT = 'plugins'

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        layout = QtWidgets.QVBoxLayout(self)
        intro = QtWidgets.QLabel(
            'The folders the toolbar\'s "Save to" dropdown offers, in this order. Choosing one sets '
            'Picard\'s destination directory (Options > File Naming).', self)
        intro.setWordWrap(True)
        layout.addWidget(intro)
        self.table = QtWidgets.QTableWidget(0, 3, self)
        self.table.setHorizontalHeaderLabels(['Name', 'Folder', 'Naming script'])
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
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
        hint = QtWidgets.QLabel('For example: Lossless → /music/lossless, Lossy → /music/lossy. '
                                'Double-click a name to rename it. A naming script given to a folder is '
                                'chosen with it; "Keep current" leaves the script as it is.', self)
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.move_on_choose_box = QtWidgets.QCheckBox('Choosing a folder turns Move files on', self)
        self.show_switches_box = QtWidgets.QCheckBox('Show Move files and Rename files on the toolbar', self)
        self.show_scripts_box = QtWidgets.QCheckBox('Show the naming script dropdown', self)
        for w in (self.move_on_choose_box, self.show_switches_box, self.show_scripts_box):
            layout.addWidget(w)

    def _row(self, name, path, script='') -> None:
        r = self.table.rowCount()
        self.table.insertRow(r)
        self.table.setItem(r, 0, QtWidgets.QTableWidgetItem(name))
        item = QtWidgets.QTableWidgetItem(path)
        item.setFlags(item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
        self.table.setItem(r, 1, item)
        combo = QtWidgets.QComboBox(self.table)
        combo.addItem('Keep current', '')
        for sid, title in dst.scripts(_setting()['file_renaming_scripts']):
            combo.addItem(title, sid)
        at = combo.findData(script or '')
        if at < 0 and script:
            combo.addItem(f'(missing script {script[:8]})', script)
            at = combo.count() - 1
        combo.setCurrentIndex(max(0, at))
        self.table.setCellWidget(r, 2, combo)

    def _script_at(self, r) -> str:
        combo = self.table.cellWidget(r, 2)
        return str(combo.currentData() or '') if combo is not None else ''

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

    def _move(self, step) -> None:
        r = self.table.currentRow()
        to = r + step
        if r < 0 or not 0 <= to < self.table.rowCount():
            return
        a = [self.table.item(r, c).text() for c in (0, 1)] + [self._script_at(r)]
        b = [self.table.item(to, c).text() for c in (0, 1)] + [self._script_at(to)]
        for c in (0, 1):
            self.table.item(r, c).setText(b[c])
            self.table.item(to, c).setText(a[c])
        for row, sid in ((r, b[2]), (to, a[2])):
            combo = self.table.cellWidget(row, 2)
            combo.setCurrentIndex(max(0, combo.findData(sid)))
        self.table.setCurrentCell(to, 0)

    def load(self):
        self.table.setRowCount(0)
        for d in dst.load(_own('destinations')):
            self._row(d['name'], d['path'], d.get('script', ''))
        self.move_on_choose_box.setChecked(bool(_own('move_on_choose')))
        self.show_switches_box.setChecked(bool(_own('show_switches')))
        self.show_scripts_box.setChecked(bool(_own('show_scripts')))

    def save(self):
        items = [{'name': self.table.item(r, 0).text(), 'path': self.table.item(r, 1).text(),
                  'script': self._script_at(r)}
                 for r in range(self.table.rowCount())]
        _set_own('destinations', dst.dump(items))
        _set_own('move_on_choose', self.move_on_choose_box.isChecked())
        _set_own('show_switches', self.show_switches_box.isChecked())
        _set_own('show_scripts', self.show_scripts_box.isChecked())
        if _TOOLBAR is not None:
            _TOOLBAR.rebuild()


def _add_toolbar() -> None:
    global _TOOLBAR
    window = getattr(_API.tagger, 'window', None)
    if window is None or _TOOLBAR is not None:
        return
    _TOOLBAR = DestinationToolbar(window)
    window.addToolBar(QtCore.Qt.ToolBarArea.TopToolBarArea, _TOOLBAR)
    _API.global_config.setting.setting_changed.connect(_TOOLBAR.setting_changed)


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
        _add_toolbar()
    except Exception:
        log = _log()
        if log:
            log.error('Destination Switcher: the toolbar could not be added', exc_info=True)


def disable() -> None:
    global _TOOLBAR
    tb = _TOOLBAR
    _TOOLBAR = None
    if tb is None:
        return
    try:
        _API.global_config.setting.setting_changed.disconnect(tb.setting_changed)
    except Exception:
        pass
    try:
        tb.window_.removeToolBar(tb)
        tb.deleteLater()
    except Exception:
        pass
