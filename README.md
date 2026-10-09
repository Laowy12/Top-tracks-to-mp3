# Top group tracks → MP3

[Русская версия →](README.ru.md)

The tool fetches up to 30 popular tracks for each group in `groups.txt`, drops the less popular ones, looks up the rest in the **Songs** section of YouTube Music and extracts MP3 files with `yt-dlp` and FFmpeg. Use it only for audio you have the rights to or permission from the copyright holder to use.

There are two ways to use it:

- **Graphical interface** (`gui.py`) — a window with tabs, list editors, progress bars and a **Stop** button. The easiest path, including as a ready-made `.exe`.
- **Command line** — three scripts (`download_top_tracks.py`, `download_music_links.py`, `check_mp3.py`) for automation and advanced users.

The interface and the console messages are available in **English and Russian**. The language is picked automatically from your system on first launch and can be switched any time in the window (or with `--lang` on the command line).

## Installation

1. Install [FFmpeg](https://ffmpeg.org/download.html) and make sure the `ffmpeg -version` command works in PowerShell.
2. In this folder run:

```powershell
python -m pip install -r requirements.txt
```

3. Add groups to `groups.txt`, one per line.
4. Optionally provide Russian name variants in `aliases.csv`. Automatic translation of track titles is unreliable, so this file lets you set the exact variants that end up in the MP3 file name.

Example `aliases.csv`:

```csv
group,track,group_ru,track_ru
The Beatles,,Битлз,
The Beatles,Yesterday,Битлз,Вчера
```

## Graphical interface

Launch the window with:

```powershell
python .\gui.py
```

The window has four tabs:

- **🎵 Top tracks** — tick the groups (the list is edited right here and saved to `groups.txt`), set the number of positions, the rating threshold and the number of threads. The **Preview** button shows what will be downloaded without downloading anything; **Download** fetches the MP3 files. The table shows the status and per-track progress.
- **🔗 Links** — paste YouTube Music links (one per line, saved to `music_links.txt`) and download them.
- **✔ Check MP3** — pick a folder and verify file integrity; the report can be saved.
- **🏷 Names** — the `aliases.csv` table for Russian name variants of groups and tracks.

The bottom of the window holds the overall progress, the log and the **Stop** button (which cleanly interrupts the current operation). The FFmpeg status and the output folder are shown in the top bar, next to the language switcher and the light/dark theme toggle. Without FFmpeg, downloads are blocked with a hint on how to install it.

## Running from the command line

First look at the list without downloading:

```powershell
python .\download_top_tracks.py --dry-run
```

Then download:

```powershell
python .\download_top_tracks.py
```

Files appear in `mp3`. File name format: `Group name — Track name.mp3`.

By default the program takes at most 30 tracks and skips anything whose Deezer rating is below `100000`. That is why a group may end up with fewer than 30 files — this is how unpopular songs are filtered out. For a stricter selection, for example:

```powershell
python .\download_top_tracks.py --min-rank 250000
```

To take fewer positions from the rating, add e.g. `--limit 10`.

When finished, the program prints a summary: the number of songs successfully downloaded in this run and their total duration in minutes and seconds. Files already present in the `mp3` folder are skipped and are not counted in the repeat summary.

## Download speed

Downloads and conversion run in parallel: by default 4 tracks are processed at once. On a fast connection and an SSD you can raise the limit, e.g. to 6:

```powershell
python .\download_top_tracks.py --workers 6
```

Do not go straight to the maximum: YouTube may temporarily throttle too many simultaneous requests. If a track fails and you see a `403` error, it is not a problem: the program has already retried automatically (up to three times with a growing delay). Usually it is enough to run it again or reduce the number of threads to `--workers 3` or `--workers 2`. Successfully created MP3 files are skipped rather than downloaded again.

## Individual YouTube Music links

In [music_links.txt](music_links.txt) paste one link to an individual YouTube Music song per line, then run:

```powershell
python .\download_music_links.py
```

The script gets the artist and title from the link metadata, applies matching translations from `aliases.csv`, downloads the MP3 into the same `mp3` folder and prints the total duration. For such links a safe limit is 3 parallel tasks; change it with `--workers 4`.

## Checking for broken MP3 files

After downloading you can fully check all audio files without modifying them:

```powershell
python .\check_mp3.py
```

The check decodes every MP3 with FFmpeg. If damaged or truncated files are found, they stay in place and their names and the reason are written to `broken_mp3_report.txt`.

The search runs in the **Songs** section of YouTube Music, so an album audio track is usually chosen instead of the music-video version. Exceptions are possible (remix, radio edit, cover), so check `--dry-run` before a bulk download; for critical accuracy it is better to extend the tool with a list of URLs you have verified yourself.

## Command-line reference

Every script accepts `--lang {en,ru}` to force the interface language (otherwise it is detected from the system).

`download_top_tracks.py`:

| Option | Default | Description |
| --- | --- | --- |
| `--groups` | `groups.txt` | file with groups |
| `--aliases` | `aliases.csv` | Russian name variants |
| `--output` | `mp3` | output folder |
| `--limit` | `30` | maximum number of top positions per group |
| `--min-rank` | `100000` | minimum Deezer popularity rating |
| `--workers` | `4` | number of parallel downloads |
| `--dry-run` | off | only show the found tracks |
| `--lang` | auto | interface language (`en` or `ru`) |

`download_music_links.py`: `--links` (`music_links.txt`), `--aliases`, `--output`, `--workers` (`3`), `--dry-run`, `--lang`.

`check_mp3.py`: `--folder` (`mp3`), `--workers` (`4`), `--report` (`broken_mp3_report.txt`), `--lang`.

## Building the .exe for Windows

To get a single executable that needs no Python installed:

```powershell
python -m pip install -r requirements.txt -r requirements-dev.txt
pwsh -File build.ps1
```

The result appears as `dist\MusicTopTracks.exe` (about 55 MB). Put `groups.txt`, `music_links.txt` and `aliases.csv` next to it — the program reads and saves data in the folder where the `.exe` lives, and stores downloaded MP3 files in the `mp3` subfolder.

FFmpeg is not bundled: it must be installed on the system (the `ffmpeg -version` command must work).

## Legal notice

Use the tool only for audio you have the rights to or permission from the copyright holder to use, and for personal use. Respect the authors and the terms of the services you use.

## License

Released under the [MIT](LICENSE) license.
