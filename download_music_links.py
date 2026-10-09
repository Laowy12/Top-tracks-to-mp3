#!/usr/bin/env python3
"""Downloads individual songs (that you are allowed to use) from YouTube Music links.

The logic lives in core.py; this file is the console interface to it.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import core
import i18n
from core import Track, read_aliases  # noqa: F401


def read_urls(path: Path) -> list[str]:
    result = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        url = line.split("#", 1)[0].strip()
        if url:
            if not url.startswith(("https://music.youtube.com/", "https://www.youtube.com/", "https://youtu.be/")):
                print("  " + i18n.t("skipping invalid link: {url}", url=url), file=sys.stderr)
                continue
            result.append(url)
    return list(dict.fromkeys(result))


def main() -> int:
    core.setup_console()
    i18n.set_language(i18n.detect_language())
    parser = argparse.ArgumentParser(description=i18n.t("YouTube Music links → MP3 (licensed content only)."))
    parser.add_argument("--links", default="music_links.txt", type=Path, help=i18n.t("text file with links"))
    parser.add_argument("--aliases", default="aliases.csv", type=Path, help=i18n.t("Russian names"))
    parser.add_argument("--output", default="mp3", type=Path, help=i18n.t("output folder"))
    parser.add_argument("--workers", default=3, type=int, choices=range(1, 9), metavar="1..8")
    parser.add_argument("--dry-run", action="store_true", help=i18n.t("only show the found songs"))
    i18n.add_language_argument(parser)
    args = parser.parse_args()
    if args.lang:
        i18n.set_language(args.lang)
    if not args.links.exists():
        print(i18n.t("File not found: {path}", path=args.links), file=sys.stderr)
        return 2
    if not args.dry_run and not core.ffmpeg_available():
        print(i18n.t("ffmpeg not found. Install FFmpeg and add it to PATH."), file=sys.stderr)
        return 2

    aliases = read_aliases(args.aliases)
    tracks: list[Track] = []
    sources: dict[str, str] = {}
    for url in read_urls(args.links):
        try:
            track = core.track_from_url(url)
            print(i18n.t("found: {group} — {title}", group=track.group, title=track.title))
            tracks.append(track)
            sources[track.catalog_id] = url
        except Exception as error:
            print("  " + i18n.t("link error {url}: {error}", url=url, error=error), file=sys.stderr)

    if not args.dry_run:
        args.output.mkdir(parents=True, exist_ok=True)

    def on_event(event: dict) -> None:
        if event.get("type") != "status":
            return
        status, message = event["status"], event.get("message", "")
        if status == "skipped_exists":
            print("  " + i18n.t("skip: {message}", message=message))
        elif status == "search":
            print("  " + i18n.t("checking" if args.dry_run else "downloading") + f": {message}")
        elif status == "error":
            print("  " + i18n.t("download error: {message}", message=message), file=sys.stderr)

    outcomes = core.download_many(
        tracks, args.output, aliases, args.workers,
        dry_run=args.dry_run, sources=sources, on_event=on_event,
    )
    success_count = sum(1 for o in outcomes if o.downloaded)
    success_seconds = sum(o.track.duration for o in outcomes if o.downloaded)

    label = i18n.t("will be downloaded" if args.dry_run else "downloaded")
    print("\n" + i18n.t("Summary: {label} {count} songs; total duration: {duration}.",
                        label=label, count=success_count,
                        duration=core.format_duration(success_seconds)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
