#!/usr/bin/env python3
"""Shared logic layer for the "Top group tracks → MP3" tool.

The module is UI-independent (neither CLI nor GUI). Progress and events are
reported through an optional ``on_event`` callback; cancellation is requested
through an optional ``cancel`` callable (returns True to stop).
Use only for content you have the rights to.
"""
from __future__ import annotations

import csv
import re
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable
from urllib.parse import quote_plus

import requests
from yt_dlp import YoutubeDL

import i18n

DEEZER = "https://api.deezer.com"
INVALID_FILENAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

# YouTube sometimes answers a single request with HTTP 403 (rate limiting),
# especially with several concurrent downloads. Retrying almost always works,
# so we retry with an increasing pause.
RETRY_ATTEMPTS = 3
RETRY_DELAY = 1.5  # seconds; then 1.5, 3.0, ...


def setup_console() -> None:
    """Switches console output to UTF-8 so non-ASCII text is not garbled.

    On Windows the console may default to the cp866/cp1251 code page, which
    turns Cyrillic in stdout into mojibake.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8")
            except Exception:
                pass


# The event callback receives a dict. Fields: type, then per type.
#   {"type": "status", "track": Track, "status": <str>, "progress": <float 0..1 | None>, "message": <str>}
#   {"type": "log",    "message": <str>, "level": "info"|"warning"|"error"}
# Statuses: "pending" | "search" | "download" | "convert" | "done"
#           | "preview" | "skipped_exists" | "skipped_rank" | "error"
EventCallback = Callable[[dict], None]
CancelCallback = Callable[[], bool]


class Cancelled(Exception):
    """Raised when the user asked to stop a download."""


@dataclass(frozen=True)
class Track:
    group: str
    title: str
    duration: int
    rank: int
    catalog_id: str


@dataclass
class DownloadOutcome:
    track: Track
    status: str          # "done" | "preview" | "skipped_exists" | "error"
    message: str = ""
    downloaded: bool = False


def _emit(on_event: EventCallback | None, event: dict) -> None:
    if on_event is not None:
        try:
            on_event(event)
        except Exception:
            # The UI must not break a download because of a callback error.
            pass


def _status(on_event: EventCallback | None, track: Track, status: str,
            progress: float | None = None, message: str = "") -> None:
    _emit(on_event, {"type": "status", "track": track, "status": status,
                     "progress": progress, "message": message})


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def clean_filename(value: str) -> str:
    value = INVALID_FILENAME.sub("_", value)
    return re.sub(r"\s+", " ", value).strip(" .")[:180]


def read_groups(path: Path) -> list[str]:
    groups = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        name = line.split("#", 1)[0].strip()
        if name:
            groups.append(name)
    return list(dict.fromkeys(groups))


def read_aliases(path: Path) -> dict[tuple[str, str], tuple[str, str]]:
    if not path.exists():
        return {}
    result = {}
    with path.open(encoding="utf-8-sig", newline="") as file:
        for row in csv.DictReader(line for line in file if not line.lstrip().startswith("#")):
            group = (row.get("group") or "").strip().casefold()
            track = (row.get("track") or "").strip().casefold()
            if group:
                result[group, track] = ((row.get("group_ru") or "").strip(), (row.get("track_ru") or "").strip())
    return result


def deezer_top_tracks(group: str, limit: int, min_rank: int) -> list[Track]:
    response = requests.get(f"{DEEZER}/search/artist", params={"q": group, "limit": 1}, timeout=30)
    response.raise_for_status()
    artists = response.json().get("data", [])
    if not artists:
        raise RuntimeError(i18n.t("artist not found in the Deezer catalog"))
    artist = artists[0]
    response = requests.get(f"{DEEZER}/artist/{artist['id']}/top", params={"limit": limit}, timeout=30)
    response.raise_for_status()
    tracks = response.json().get("data", [])
    if not tracks:
        raise RuntimeError(i18n.t("artist has no available top tracks"))
    popular = [
        Track(
            artist["name"], t["title"], int(t.get("duration") or 0),
            int(t.get("rank") or 0), str(t["id"]),
        )
        for t in tracks
        if int(t.get("rank") or 0) >= min_rank
    ]
    return popular


def russian_names(track: Track, aliases: dict[tuple[str, str], tuple[str, str]]) -> tuple[str, str]:
    # Exact translation of proper names and song titles cannot be guessed
    # reliably, so we apply the variants configured in aliases.csv and fall
    # back to the original otherwise.
    group_key = track.group.casefold()
    group_ru, track_ru = aliases.get((group_key, track.title.casefold()), ("", ""))
    fallback_group, _ = aliases.get((group_key, ""), ("", ""))
    return group_ru or fallback_group or track.group, track_ru or track.title


def destination(track: Track, folder: Path, aliases: dict[tuple[str, str], tuple[str, str]]) -> Path:
    group, title = russian_names(track, aliases)
    return folder / f"{clean_filename(f'{group} — {title}')}.mp3"


def track_from_url(url: str) -> Track:
    options = {"quiet": True, "no_warnings": True, "skip_download": True}
    with YoutubeDL(options) as ydl:
        info = ydl.extract_info(url, download=False)
    if info.get("_type") == "playlist":
        info = next(iter(info.get("entries") or []), None)
    if not info:
        raise RuntimeError(i18n.t("no single audio track found at the link"))
    artist = info.get("artist") or info.get("uploader") or i18n.t("Unknown artist")
    title = info.get("track") or info.get("title") or i18n.t("Untitled")
    return Track(str(artist), str(title), int(info.get("duration") or 0), 0, str(info["id"]))


def download(
    track: Track,
    folder: Path,
    aliases: dict[tuple[str, str], tuple[str, str]],
    dry_run: bool = False,
    source: str | None = None,
    on_event: EventCallback | None = None,
    cancel: CancelCallback | None = None,
) -> DownloadOutcome:
    """Downloads a single track to MP3. Returns a DownloadOutcome.

    on_event reports stages (search/download/convert/done) and progress.
    cancel() == True interrupts the download (cooperative cancellation).
    """
    target = destination(track, folder, aliases)
    stem = target.stem
    if target.exists():
        _status(on_event, track, "skipped_exists", message=target.name)
        return DownloadOutcome(track, "skipped_exists", target.name, downloaded=False)

    # The Songs section of YouTube Music contains releases rather than regular
    # music videos, which lowers the chance of a long intro, a live version or
    # a video edit.
    search_text = f"{track.group} {track.title}"
    query = source or f"https://music.youtube.com/search?q={quote_plus(search_text)}#songs"
    _status(on_event, track, "search", progress=0.0, message=stem)
    if dry_run:
        _status(on_event, track, "preview", progress=1.0, message=stem)
        return DownloadOutcome(track, "preview", stem, downloaded=True)

    def hook(status: dict) -> None:
        if cancel is not None and cancel():
            raise Cancelled()
        if status.get("status") == "downloading":
            total = status.get("total_bytes") or status.get("total_bytes_estimate") or 0
            done = status.get("downloaded_bytes") or 0
            fraction = (done / total) if total else None
            _status(on_event, track, "download", progress=fraction, message=stem)
        elif status.get("status") == "finished":
            _status(on_event, track, "convert", progress=None, message=stem)

    options = {
        "format": "bestaudio/best",
        # Each task gets its own temporary file. This matters when the catalog
        # returns duplicates or different releases sharing the same name.
        "outtmpl": str(folder / f".part-{track.catalog_id}-%(id)s.%(ext)s"),
        "playlistend": 1,
        "quiet": True,
        "no_warnings": True,
        "retries": 3,
        "fragment_retries": 3,
        "extractor_retries": 3,
        "socket_timeout": 30,
        "progress_hooks": [hook],
        "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}],
    }

    def cleanup_partials() -> None:
        # An interrupted download/conversion may leave this track's temporary
        # files (.part-<id>-*). Remove them so the folder stays clean.
        for leftover in folder.glob(f".part-{track.catalog_id}-*"):
            try:
                leftover.unlink()
            except OSError:
                pass

    cancelled_message = i18n.t("cancelled")
    last_error: Exception | None = None
    for attempt in range(1, RETRY_ATTEMPTS + 1):
        if cancel is not None and cancel():
            _status(on_event, track, "error", message=cancelled_message)
            return DownloadOutcome(track, "error", cancelled_message, downloaded=False)
        try:
            if attempt > 1:
                # Retry after a failure: clean temporary files and wait so
                # YouTube stops rejecting requests.
                cleanup_partials()
                time.sleep(RETRY_DELAY * (attempt - 1))
                _status(on_event, track, "search", progress=0.0,
                        message=i18n.t("retry {attempt}", attempt=attempt))
            with YoutubeDL(options) as ydl:
                info = ydl.extract_info(query, download=True)
                if info.get("_type") == "playlist":
                    info = next(iter(info.get("entries") or []), None)
                    if info is None:
                        raise RuntimeError(i18n.t("YouTube Music returned no audio track"))
                temporary_mp3 = Path(ydl.prepare_filename(info)).with_suffix(".mp3")
            temporary_mp3.replace(target)
            last_error = None
            break
        except Cancelled:
            cleanup_partials()
            _status(on_event, track, "error", message=cancelled_message)
            return DownloadOutcome(track, "error", cancelled_message, downloaded=False)
        except Exception as error:
            last_error = error
            cleanup_partials()

    if last_error is not None:
        message = str(last_error)
        if "403" in message:
            message = i18n.t("YouTube rejected the request (403). Try again or reduce the number of threads.")
        _status(on_event, track, "error", message=message)
        return DownloadOutcome(track, "error", message, downloaded=False)
    _status(on_event, track, "done", progress=1.0, message=stem)
    return DownloadOutcome(track, "done", stem, downloaded=True)


def unique_by_destination(
    tracks: Iterable[Track], folder: Path,
    aliases: dict[tuple[str, str], tuple[str, str]],
) -> dict[Path, Track]:
    """Removes duplicates by final file name (the first one wins)."""
    result: dict[Path, Track] = {}
    for track in tracks:
        result.setdefault(destination(track, folder, aliases), track)
    return result


def download_many(
    tracks: Iterable[Track],
    folder: Path,
    aliases: dict[tuple[str, str], tuple[str, str]],
    workers: int,
    dry_run: bool = False,
    sources: dict[str, str] | None = None,
    on_event: EventCallback | None = None,
    cancel: CancelCallback | None = None,
) -> list[DownloadOutcome]:
    """Downloads a set of tracks in a thread pool. sources: catalog_id -> source URL."""
    unique = unique_by_destination(tracks, folder, aliases)
    sources = sources or {}
    outcomes: list[DownloadOutcome] = []
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="mp3") as pool:
        futures = {
            pool.submit(
                download, track, folder, aliases, dry_run,
                sources.get(track.catalog_id), on_event, cancel,
            ): track
            for track in unique.values()
        }
        for future in as_completed(futures):
            track = futures[future]
            try:
                outcomes.append(future.result())
            except Exception as error:
                _status(on_event, track, "error", message=str(error))
                outcomes.append(DownloadOutcome(track, "error", str(error), downloaded=False))
    return outcomes


# --- MP3 integrity check -----------------------------------------------------

@dataclass
class CheckResult:
    path: Path
    ok: bool
    message: str = ""
    size: int = 0


def check_file(path: Path) -> CheckResult:
    size = path.stat().st_size
    if size == 0:
        return CheckResult(path, False, i18n.t("file is empty (0 bytes)"), size)
    command = ["ffmpeg", "-v", "error", "-i", str(path), "-f", "null", "-"]
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode == 0:
        return CheckResult(path, True, "", size)
    message = (result.stderr or i18n.t("FFmpeg could not decode the file")).strip().replace("\n", " | ")
    return CheckResult(path, False, message[:500], size)


def check_folder(
    folder: Path, workers: int,
    on_result: Callable[[CheckResult], None] | None = None,
) -> list[CheckResult]:
    files = sorted(folder.rglob("*.mp3"))
    results: list[CheckResult] = []
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="verify") as pool:
        futures = {pool.submit(check_file, file): file for file in files}
        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            if on_result is not None:
                try:
                    on_result(result)
                except Exception:
                    pass
    return results


def format_duration(seconds: int) -> str:
    minutes, seconds = divmod(seconds, 60)
    return i18n.t("{minutes} min {seconds:02d} sec", minutes=minutes, seconds=seconds)
