#!/usr/bin/env python3
"""Minimal runtime localization for the tools.

English source strings are used as keys; ``_RU`` holds the Russian
translation of each key. English needs no table (the key is returned as-is),
which keeps the codebase readable for an international audience and makes a
missing translation fall back to English instead of failing.

Usage:
    import i18n
    i18n.set_language("ru")           # or detect_language() at startup
    label = i18n.t("Download")         # -> "Загрузить" (ru) / "Download" (en)
    text  = i18n.t("retry {n}", n=2)   # -> "повтор 2"
"""
from __future__ import annotations

import os

LANGUAGE_NAMES = {"en": "English", "ru": "Русский"}
DEFAULT_LANGUAGE = "en"

_current = DEFAULT_LANGUAGE

# English key -> Russian translation.
_RU = {
    # --- core.py ---
    "artist not found in the Deezer catalog": "исполнитель не найден в каталоге Deezer",
    "artist has no available top tracks": "у исполнителя нет доступных топ-треков",
    "no single audio track found at the link": "по ссылке не найдена отдельная аудиодорожка",
    "Unknown artist": "Неизвестный исполнитель",
    "Untitled": "Без названия",
    "cancelled": "отменено",
    "retry {attempt}": "повтор {attempt}",
    "YouTube Music returned no audio track": "YouTube Music не вернул аудиодорожку",
    "YouTube rejected the request (403). Try again or reduce the number of threads.":
        "YouTube отклонил запрос (403). Попробуйте ещё раз или уменьшите число потоков.",
    "file is empty (0 bytes)": "файл пустой (0 байт)",
    "FFmpeg could not decode the file": "FFmpeg не смог декодировать файл",
    "{minutes} min {seconds:02d} sec": "{minutes} мин {seconds:02d} сек",

    # --- window / common ---
    "Top group tracks → MP3": "Топ-треки групп → MP3",
    "Language:": "Язык:",
    "Output folder:": "Папка вывода:",
    "Ready": "Готово",
    "Working…": "Работаю…",
    "Stopping…": "Останавливаю…",
    "Stop requested.": "Запрошена остановка.",
    "■ Stop": "■ Стоп",
    "Open folder": "Открыть папку",
    "Preview ready": "Предпросмотр готов",
    "Error": "Ошибка",
    "Operation error: {message}": "Ошибка операции: {message}",
    "Summary: {verb} {done} · skipped {skipped} · errors {errors} · duration {duration}.":
        "Сводка: {verb} {done} · пропущено {skipped} · ошибок {errors} · длительность {duration}.",
    "will be downloaded": "будет загружено",
    "downloaded": "скачано",

    # --- tabs ---
    "🎵 Top tracks": "🎵 Топ-треки",
    "🔗 Links": "🔗 Ссылки",
    "✔ MP3 check": "✔ Проверка MP3",
    "🏷 Names": "🏷 Имена",

    # --- status labels ---
    "In queue": "В очереди",
    "Searching…": "Поиск…",
    "Downloading": "Загрузка",
    "Converting…": "Конвертация…",
    "✔ Done": "✔ Готово",
    "👁 Will be downloaded": "👁 Будет загружено",
    "⟳ Already have": "⟳ Уже есть",
    "⤼ Below threshold": "⤼ Ниже порога",
    "⤼ Duplicate name": "⤼ Дубликат имени",
    "✖ Error": "✖ Ошибка",

    # --- Top tracks tab ---
    "Groups": "Группы",
    "Add a group and press Enter…": "Добавить группу и Enter…",
    "Delete": "Удалить",
    "Import": "Импорт",
    "Save": "Сохранить",
    "Parameters": "Параметры",
    "Higher number = more popular track. Tracks below the threshold are skipped.":
        "Чем выше число, тем популярнее трек. Позиции ниже порога пропускаются.",
    "Tracks per group:": "Треков на группу:",
    "Popularity threshold:": "Порог популярности:",
    "Download threads:": "Потоков загрузки:",
    "👁 Preview": "👁 Предпросмотр",
    "⬇ Download": "⬇ Загрузить",
    "Group": "Группа",
    "Track": "Трек",
    "Deezer rank": "Deezer-ранг",
    "Status": "Статус",
    "Progress": "Прогресс",
    "Legend: ✔ done · ⟳ already have · ⤼ skipped · ✖ error":
        "Легенда: ✔ готово · ⟳ уже есть · ⤼ пропуск · ✖ ошибка",
    "Import groups": "Импорт групп",
    "Text (*.txt)": "Текст (*.txt)",
    "Saved groups: {count}": "Сохранено групп: {count}",
    "No groups selected.": "Не отмечено ни одной группы.",
    "{group}: fetching top tracks…": "{group}: получаю топ-треки…",
    "{group}: selected {count}": "{group}: отобрано {count}",
    "{group}: error — {error}": "{group}: ошибка — {error}",

    # --- Links tab ---
    "YouTube Music links (one per line)": "Ссылки YouTube Music (по одной на строку)",
    "Save to music_links.txt": "Сохранить в music_links.txt",
    "Link": "Ссылка",
    "Recognized as": "Распознано как",
    "Links saved.": "Ссылки сохранены.",
    "Skipping invalid link: {url}": "Пропуск некорректной ссылки: {url}",
    "No valid links.": "Нет корректных ссылок.",
    "found: {group} — {title}": "найдено: {group} — {title}",
    "link error {url}: {error}": "ошибка ссылки {url}: {error}",

    # --- Check tab ---
    "▶ Check integrity": "▶ Проверить целостность",
    "Folder:": "Папка:",
    "Threads:": "Потоков:",
    "File": "Файл",
    "Size": "Размер",
    "Save report": "Сохранить отчёт",
    "MP3 folder": "Папка с MP3",
    "Folder not found: {path}": "Не найдена папка: {path}",
    "{size} MB": "{size} МБ",
    "✔ OK": "✔ OK",
    "Checked: {total} · OK: {ok} · broken: {bad}":
        "Проверено: {total} · OK: {ok} · повреждено: {bad}",
    "Check completed: {total} files, {bad} broken.":
        "Проверка завершена: {total} файлов, повреждено {bad}.",
    "Broken MP3 (files kept in place):": "Проблемные MP3 (файлы не удалены):",
    "Report saved: {path}": "Отчёт сохранён: {path}",

    # --- Names (aliases) tab ---
    "Set Russian name variants — they are used for the MP3 file name. Empty track = a variant for the whole group.":
        "Задайте русские варианты имён — ими будет назван MP3-файл. Пустой track = вариант для всей группы.",
    "＋ row": "＋ строка",
    "Delete row": "Удалить строку",
    "Save aliases.csv": "Сохранить aliases.csv",
    "aliases.csv saved.": "aliases.csv сохранён.",

    # --- environment / dialogs ---
    "● FFmpeg found": "● FFmpeg найден",
    "● FFmpeg not found — downloading unavailable": "● FFmpeg не найден — загрузка недоступна",
    "FFmpeg required": "Нужен FFmpeg",
    "FFmpeg was not found in PATH. It is required to convert to MP3.\n\n"
    "Install FFmpeg (for example: winget install Gyan.FFmpeg) and restart the application.":
        "FFmpeg не найден в PATH. Он нужен для конвертации в MP3.\n\n"
        "Установите FFmpeg (например: winget install Gyan.FFmpeg) и перезапустите приложение.",
    "FFmpeg not found": "FFmpeg не найден",
    "FFmpeg was not found in PATH. Downloading and MP3 checking will be unavailable "
    "until you install FFmpeg and restart the application.\n\n"
    "List editing and preview work without it.":
        "FFmpeg не обнаружен в PATH. Загрузка и проверка MP3 будут недоступны, "
        "пока вы не установите FFmpeg и не перезапустите приложение.\n\n"
        "Проверка списков и предпросмотр работают без него.",
    "Output folder": "Папка вывода",

    # --- CLI: download_top_tracks.py ---
    "Top group tracks to MP3 (licensed content only).":
        "Топ-треки групп в MP3 (только для разрешённого контента).",
    "file with groups": "файл с группами",
    "Russian names": "русские названия",
    "output folder": "папка результата",
    "minimum Deezer popularity rating (default: 100000)":
        "минимальный рейтинг популярности Deezer (по умолчанию: 100000)",
    "number of parallel downloads (default: 4)":
        "число параллельных загрузок (по умолчанию: 4)",
    "only show the found tracks": "только показать найденные треки",
    "File not found: {path}": "Не найден файл: {path}",
    "ffmpeg not found. Install FFmpeg and add it to PATH.":
        "Не найден ffmpeg. Установите FFmpeg и добавьте его в PATH.",
    "no tracks with rating not lower than {rank}": "нет треков с рейтингом не ниже {rank}",
    "selected: {count}": "отобрано: {count}",
    "error: {error}": "ошибка: {error}",
    "Parallel processing: {count} tracks, tasks at once: {workers}.":
        "Параллельная обработка: {count} треков, задач одновременно: {workers}.",
    "Skipped identical names: {count}.": "Пропущено одинаковых имён: {count}.",
    "skip: {message}": "пропуск: {message}",
    "checking": "проверка",
    "downloading": "загрузка",
    "download error: {message}": "ошибка загрузки: {message}",
    "Summary: {label} {count} songs; total duration: {duration}.":
        "Сводка: {label} {count} песен; общая длительность: {duration}.",

    # --- CLI: download_music_links.py ---
    "YouTube Music links → MP3 (licensed content only).":
        "Ссылки YouTube Music → MP3 (только для разрешённого контента).",
    "text file with links": "текстовый файл со ссылками",
    "only show the found songs": "только показать найденные песни",
    "skipping invalid link: {url}": "пропуск некорректной ссылки: {url}",

    # --- CLI: check_mp3.py ---
    "Check the integrity of all MP3 in a folder.": "Проверить целостность всех MP3 в папке.",
    "folder with MP3": "папка с MP3",
    "report file": "файл отчёта",
    "PROBLEM: {name}": "ПРОБЛЕМА: {name}",
    "No MP3 files found.": "MP3-файлы не найдены.",
    "Done: checked {total}, broken: {bad}.": "Готово: проверено {total}, проблемных: {bad}.",
    "Details: {path}": "Подробности: {path}",
    "Done: checked {total}, no broken files found.":
        "Готово: проверено {total}, проблемных файлов не найдено.",

    # --- CLI common ---
    "interface language: en or ru (default: system)":
        "язык интерфейса: en или ru (по умолчанию: системный)",
}

_TABLES = {"ru": _RU}


def _normalize(code: str | None) -> str | None:
    """Maps a locale code (``ru_RU.UTF-8``, ``en-US``, ``C``) to en/ru."""
    if not code:
        return None
    code = code.strip().lower().replace("-", "_")
    if code.startswith("ru"):
        return "ru"
    if code.startswith("en"):
        return "en"
    return None


def detect_language() -> str:
    """Best-effort detection of the user's language; falls back to English."""
    for var in ("SONG_LANG", "LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"):
        code = _normalize(os.environ.get(var))
        if code:
            return code
    try:
        import locale as _locale

        loc = _locale.getlocale()[0]
    except Exception:
        loc = None
    return _normalize(loc) or DEFAULT_LANGUAGE


def set_language(code: str | None) -> str:
    """Sets the active language. Unknown/None values fall back to English."""
    global _current
    _current = _normalize(code) or DEFAULT_LANGUAGE
    return _current


def get_language() -> str:
    return _current


def t(key: str, **fmt) -> str:
    """Translates ``key`` into the active language, then formats it.

    Unknown keys are returned unchanged, so English strings work without a
    table entry.
    """
    table = _TABLES.get(_current)
    text = table.get(key, key) if table else key
    if fmt:
        try:
            return text.format(**fmt)
        except (KeyError, IndexError, ValueError):
            return text
    return text


def add_language_argument(parser) -> None:
    """Adds a shared ``--lang`` option to a CLI argument parser."""
    parser.add_argument(
        "--lang", choices=("en", "ru"), default=None,
        help=t("interface language: en or ru (default: system)"),
    )
