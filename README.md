# Destination Switcher

A [MusicBrainz Picard](https://picard.musicbrainz.org/) 3 plugin: a bar above
Picard's right pane (where files go) — or the left pane, or a toolbar — to pick
**where Picard saves** and **which file naming script** it uses, without
opening Options — **for each album on its own** or for every album. The bar is tinted with the colour of the folder Picard saves
to, as [TagMender](https://github.com/herculepirate/tagmender) colours its
profiles.

```
● Save to: [● classical ▾] [Browse…] [✓ Move files] [✓ Rename files] │ Naming script: [classical_unraid ▾] [Edit…]
```

- **Each album its own folder.** Select one or more albums in the right pane
  and the bar is theirs (*Solaris saves to:*): a folder or naming script
  chosen then is for those albums alone, used when their files are saved —
  Picard's own settings stay as they are. Right-click albums → **Save to
  folder…** does the same. *Same as every album* gives an album back to
  Picard's folder. With no album selected, the bar is for every other album
  (*Every album saves to:*). Each album row is tinted with the colour of the
  folder it saves to, and a **Saves to** column in the right pane names it,
  with a dot of its colour: **bold** when the album has a folder of its own,
  *italic* when it follows every album. Hover it for the path and naming
  script; click its header to sort albums by folder. (Right-click the header
  to hide or show it, as with any of Picard's columns.)
- **Everything in the album's folder goes with it.** Picard's own *Move
  additional files* looks only beside each audio file, so in a set of discs
  the `covers/` folder, rip log, cue sheet and booklet sitting beside `CD1/`
  and `CD2/` stayed behind. Now, once an album's old folder holds no audio any
  more, whatever is left in it — files and whole folders — is moved into the
  album's new folder (a leftover `CD1/` cue goes into the new `CD1/`), and the
  emptied folder is removed when Picard's *Delete empty directories* is on. A
  folder that still holds music (an album saved in part, an artist's folder of
  several albums) is never touched; a file already at the destination is kept
  unless Picard's *Overwrite existing files* is on. Option: **"Move everything
  left in an album's folder with it"** (on).
- **Save to** offers the folders you name in the plugin's settings — for
  example *Lossless* → `/music/lossless` and *Lossy* → `/music/lossy`.
  Choosing one sets Picard's destination directory (Options → File Naming →
  *Move files to this directory*) and turns *Move files* on — and, when you
  linked a naming script to that folder, makes it the active script
  (*classical* → *classical_unraid*). One folder can be named twice with two
  scripts (*lossyless* → *allmusic_unraid*, *lossyless_va* →
  *variousartists_unraid*); the bar shows the one whose script is active. A folder that is
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
| Colour each album in the right pane with the colour of the folder it saves to | on |
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
and removed when it is disabled. An album's own folder and naming script are
kept while it is loaded (not in its tags) and given to Picard when it names
that album's files (`File.make_filename`, wrapped while the plugin is enabled).
TagMender's profiles are read (never
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
