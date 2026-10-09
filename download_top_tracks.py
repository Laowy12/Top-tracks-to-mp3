#!/usr/bin/env python3
"""Downloads the top tracks of groups (that you are allowed to use) to MP3.

List source: the public Deezer catalog. Audio source: a YouTube URL/search via
yt-dlp. Run only for content you have the rights to.

The logic lives in core.py; this file is the console interface to it.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import requests

import core
import i18n
# Backwards compatibility: these names were historically imported from here.
from core import Track, destination, download, read_aliases  # noqa: F401


def main() -> int:
    core.setup_console()
    i18n.set_language(i18n.detect_language())
    parser = argparse.ArgumentParser(description=i18n.t("Top group tracks to MP3 (licensed content only)."))
    parser.add_argument("--groups", default="groups.txt", type=Path, help=i18n.t("file with groups"))
    parser.add_argument("--aliases", default="aliases.csv", type=Path, help=i18n.t("Russian names"))
    parser.add_argument("--output", default="mp3", type=Path, help=i18n.t("output folder"))
    parser.add_argument("--limit", default=30, type=int, choices=range(1, 31), metavar="1..30")
    parser.add_argument(
        "--min-rank", default=100_000, type=int, metavar="N",
        help=i18n.t("minimum Deezer popularity rating (default: 100000)"),
    )
    parser.add_argument(
        "--workers", default=4, type=int, choices=range(1, 17), metavar="1..16",
        help=i18n.t("number of parallel downloads (default: 4)"),
    )
    parser.add_argument("--dry-run", action="store_true", help=i18n.t("only show the found tracks"))
    i18n.add_language_argument(parser)
    args = parser.parse_args()
    if args.lang:
        i18n.set_language(args.lang)
    if not args.groups.exists():
        print(i18n.t("File not found: {path}", path=args.groups), file=sys.stderr)
        return 2
    if not args.dry_run and not core.ffmpeg_available():
        print(i18n.t("ffmpeg not found. Install FFmpeg and add it to PATH."), file=sys.stderr)
        return 2
    if not args.dry_run:
        args.output.mkdir(parents=True, exist_ok=True)
    aliases = read_aliases(args.aliases)

    tracks_to_download: list[Track] = []
    for requested_group in core.read_groups(args.groups):
        print(f"{requested_group}:")
        try:
            tracks = core.deezer_top_tracks(requested_group, args.limit, args.min_rank)
            if not tracks:
                print("  " + i18n.t("no tracks with rating not lower than {rank}", rank=args.min_rank))
                continue
            print("  " + i18n.t("selected: {count}", count=len(tracks)))
            tracks_to_download.extend(tracks)
        except (requests.RequestException, RuntimeError) as error:
            print("  " + i18n.t("error: {error}", error=error), file=sys.stderr)

    unique = core.unique_by_destination(tracks_to_download, args.output, aliases)
    if unique:
        skipped_duplicates = len(tracks_to_download) - len(unique)
        print("\n" + i18n.t("Parallel processing: {count} tracks, tasks at once: {workers}.",
                            count=len(unique), workers=args.workers))
        if skipped_duplicates:
            print(i18n.t("Skipped identical names: {count}.", count=skipped_duplicates))

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
        tracks_to_download, args.output, aliases, args.workers,
        dry_run=args.dry_run, on_event=on_event,
    )
    downloaded_count = sum(1 for o in outcomes if o.downloaded)
    downloaded_seconds = sum(o.track.duration for o in outcomes if o.downloaded)

    label = i18n.t("will be downloaded" if args.dry_run else "downloaded")
    print("\n" + i18n.t("Summary: {label} {count} songs; total duration: {duration}.",
                        label=label, count=downloaded_count,
                        duration=core.format_duration(downloaded_seconds)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
