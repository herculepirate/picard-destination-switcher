# Destination Switcher

A [MusicBrainz Picard](https://picard.musicbrainz.org/) 3 plugin: a toolbar on
the main window to pick **where Picard saves** and **which file naming script**
it uses, without opening Options.

```
Save to: [Lossless ▾] [Browse…] [✓ Move files] [✓ Rename files] │ Naming script: [My script ▾] [Edit…]
```

- **Save to** offers the folders you name in the plugin's settings — for
  example *Lossless* → `/music/lossless` and *Lossy* → `/music/lossy`.
  Choosing one sets Picard's destination directory (Options → File Naming →
  *Move files to this directory*) and turns *Move files* on. A folder that is
  none of yours shows as *Other: …*; **Browse…** picks any folder.
- **Naming script** lists every file naming script Picard knows, as Options →
  File naming scripts does; **Edit…** opens Picard's script editor.
- **Move files** and **Rename files** are Picard's own switches.

Everything the toolbar changes is Picard's own setting, so it follows Picard
(and Picard follows it): change the folder or script in Options, a profile or
the Options menu, and the toolbar shows it.

## Settings

**Options → Plugins → Destination Switcher**

| Setting | Default |
| --- | --- |
| Your folders: name and path, in the order the dropdown shows them (Add, Change, Remove, Up, Down; double-click a name to rename) | none |
| Choosing a folder turns Move files on | on |
| Show Move files and Rename files on the toolbar | on |
| Show the naming script dropdown | on |

The toolbar can be moved like Picard's own, and hidden from the right-click
menu of any toolbar.

## Installing

From inside Picard: **Options → Plugins → Install Plugin…** and paste
`https://github.com/herculepirate/picard-destination-switcher`.

Or with the install script (Linux, deb or Flatpak Picard):

```bash
git clone https://github.com/herculepirate/picard-destination-switcher
cd picard-destination-switcher
./install.sh            # from GitHub
./install.sh --update   # later
```

Restart Picard, enable **Destination Switcher** under Options → Plugins, and
name your folders.

## How it works

Picard 3's plugin API has no extension point for main-window widgets, so the
toolbar is added to the window the plugin API gives (`api.tagger.window`)
when the plugin is enabled and removed when it is disabled. Picard's settings
are read and written through `api.global_config.setting` (`move_files_to`,
`move_files`, `rename_files`, `active_file_naming_script_id`), and its
`setting_changed` signal keeps the toolbar current.

## Development

```bash
python3 tests/test_destinations.py
```

`destinations.py` holds the pure logic (your folders as JSON, matching
Picard's current folder, the scripts' order); `__init__.py` the toolbar and
the options page.

## Licence

GPL-2.0-or-later, as Picard.
