# Destination Switcher

A [MusicBrainz Picard](https://picard.musicbrainz.org/) 3 plugin: a bar above
Picard's right pane (where files go) — or the left pane, or a toolbar — to pick
**where Picard saves** and **which file naming script** it uses, without
opening Options. The bar is tinted with the colour of the folder Picard saves
to, as [TagMender](https://github.com/herculepirate/tagmender) colours its
profiles.

```
● Save to: [● classical ▾] [Browse…] [✓ Move files] [✓ Rename files] │ Naming script: [classical_unraid ▾] [Edit…]
```

- **Save to** offers the folders you name in the plugin's settings — for
  example *Lossless* → `/music/lossless` and *Lossy* → `/music/lossy`.
  Choosing one sets Picard's destination directory (Options → File Naming →
  *Move files to this directory*) and turns *Move files* on — and, when you
  linked a naming script to that folder, makes it the active script
  (*classical* → *classical_unraid*). A folder that is
  none of yours shows as *Other: …*; **Browse…** picks any folder.
- **Naming script** lists every file naming script Picard knows, as Options →
  File naming scripts does; **Edit…** opens Picard's script editor.
- **Move files** and **Rename files** are Picard's own switches.
- **Colours.** Each folder has a colour: a dot beside it in the dropdown, and
  the bar is tinted with the colour of the folder Picard saves to (a stripe and
  a light wash; a darker wash in a dark theme), so you see at a glance where
  the next save goes. *Automatic* colours a folder as TagMender colours its
  profiles: the colour of the TagMender profile that saves to that folder, if
  you have one; else by its name (*lossyless* green, *extreme* orange); else
  blue, purple, teal, pink, amber, grey, red in turn.

Everything the toolbar changes is Picard's own setting, so it follows Picard
(and Picard follows it): change the folder or script in Options, a profile or
the Options menu, and the toolbar shows it.

## Settings

**Options → Plugins → Destination Switcher**

| Setting | Default |
| --- | --- |
| Your folders: name, path, the naming script chosen with it (*Keep current* leaves the script as it is) and its colour (*Automatic*, *None* or one of nine), in the order the dropdown shows them (Add, Change, Remove, Up, Down; double-click a name to rename) | none |
| Show the switcher: above the right pane, above the left pane, or on a toolbar | right pane |
| Automatic colours: a folder a TagMender profile saves to takes that profile's colour | on |
| Choosing a folder turns Move files on | on |
| Show Move files and Rename files on the toolbar | on |
| Show the naming script dropdown | on |

On a toolbar, it can be moved like Picard's own and hidden from the
right-click menu of any toolbar.

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
bar is put into the window the plugin API gives (`api.tagger.window`) when the
plugin is enabled — at the top of the container Picard keeps each pane and its
filter box in, or on a toolbar if a Picard build lays its panes out otherwise —
and removed when it is disabled. TagMender's profiles are read (never
written) from `~/.config/tagmender/profiles` for their colours. Picard's settings
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
