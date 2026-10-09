#!/usr/bin/env python3
"""Checks MP3 files by fully decoding them with FFmpeg, without changing anything.

The logic lives in core.py; this file is the console interface to it.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import core
import i18n


def main() -> int:
    core.setup_console()
    i18n.set_language(i18n.detect_language())
    parser = argparse.ArgumentParser(description=i18n.t("Check the integrity of all MP3 in a folder."))
    parser.add_argument("--folder", default="mp3", type=Path, help=i18n.t("folder with MP3"))
    parser.add_argument("--workers", default=4, type=int, choices=range(1, 17), metavar="1..16")
    parser.add_argument("--report", default="broken_mp3_report.txt", type=Path, help=i18n.t("report file"))
    i18n.add_language_argument(parser)
    args = parser.parse_args()
    if args.lang:
        i18n.set_language(args.lang)
    if not core.ffmpeg_available():
        print(i18n.t("ffmpeg not found. Install FFmpeg and add it to PATH."), file=sys.stderr)
        return 2
    if not args.folder.is_dir():
        print(i18n.t("Folder not found: {path}", path=args.folder), file=sys.stderr)
        return 2

    def on_result(result: core.CheckResult) -> None:
        if not result.ok:
            print(i18n.t("PROBLEM: {name}", name=result.path.name))

    results = core.check_folder(args.folder, args.workers, on_result=on_result)
    if not results:
        print(i18n.t("No MP3 files found."))
        return 0

    broken = [r for r in results if not r.ok]
    if broken:
        report_lines = [i18n.t("Broken MP3 (files kept in place):"), ""]
        for result in sorted(broken, key=lambda r: r.path):
            report_lines.extend((str(result.path), result.message, ""))
        args.report.write_text("\n".join(report_lines), encoding="utf-8")
        print("\n" + i18n.t("Done: checked {total}, broken: {bad}.", total=len(results), bad=len(broken)))
        print(i18n.t("Details: {path}", path=args.report))
        return 1

    print("\n" + i18n.t("Done: checked {total}, no broken files found.", total=len(results)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
