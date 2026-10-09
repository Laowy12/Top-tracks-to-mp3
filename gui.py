#!/usr/bin/env python3
"""Graphical interface for the "Top group tracks → MP3" tool (PySide6).

Run:  python gui.py
Download/check logic lives in core.py; this file is only the interface.
Use only for content you have the rights to.
"""
from __future__ import annotations

import sys
import threading
import traceback
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Qt, Signal, Slot, QSettings, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QPalette
from PySide6.QtWidgets import (
    QApplication, QComboBox, QFileDialog, QFormLayout, QGroupBox, QHBoxLayout,
    QHeaderView, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow,
    QMessageBox, QPlainTextEdit, QProgressBar, QPushButton, QSpinBox,
    QTableWidget, QTableWidgetItem, QTabWidget, QToolButton,
    QVBoxLayout, QWidget,
)

import core
import i18n

APP_NAME = "MusicTopTracks"        # stable QSettings application name
ACCENT_LIGHT = "#4F46E5"
ACCENT_DARK = "#7C83FF"

# core status -> (English label, colour). Translated at display time.
STATUS_STYLE = {
    "pending": ("In queue", "#64748B"),
    "search": ("Searching…", None),
    "download": ("Downloading", None),
    "convert": ("Converting…", None),
    "done": ("✔ Done", "#16A34A"),
    "preview": ("👁 Will be downloaded", "#4F46E5"),
    "skipped_exists": ("⟳ Already have", "#64748B"),
    "skipped_rank": ("⤼ Below threshold", "#64748B"),
    "skipped_dup": ("⤼ Duplicate name", "#64748B"),
    "error": ("✖ Error", "#DC2626"),
}


def status_text(status: str, message: str = "") -> str:
    label = i18n.t(STATUS_STYLE.get(status, (status, None))[0])
    if status == "error" and message:
        label = f"✖ {message}"
    return label


# --------------------------------------------------------------------------- #
#  Background tasks
# --------------------------------------------------------------------------- #
class WorkerSignals(QObject):
    event = Signal(object)      # core event: dict
    finished = Signal(object)   # function result
    failed = Signal(str)        # error text
    log = Signal(str)           # log line


class Worker(QRunnable):
    """Runs an arbitrary function in the background. The function receives a
    helper object ``emit`` with event()/log() for thread-safe UI updates."""

    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self.signals = WorkerSignals()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs

    @Slot()
    def run(self):
        try:
            result = self.fn(self.signals, *self.args, **self.kwargs)
        except Exception as error:  # noqa: BLE001 - show it to the user
            self.signals.failed.emit(str(error))
        else:
            self.signals.finished.emit(result)


# --------------------------------------------------------------------------- #
#  Theme
# --------------------------------------------------------------------------- #
def apply_theme(app: QApplication, dark: bool) -> None:
    app.setStyle("Fusion")
    palette = QPalette()
    if dark:
        bg, base, text, mid = "#14171C", "#1C2026", "#E8EAED", "#2A2F37"
        accent = ACCENT_DARK
    else:
        bg, base, text, mid = "#F7F8FA", "#FFFFFF", "#1B1F24", "#E3E6EB"
        accent = ACCENT_LIGHT
    palette.setColor(QPalette.Window, QColor(bg))
    palette.setColor(QPalette.Base, QColor(base))
    palette.setColor(QPalette.AlternateBase, QColor(mid))
    palette.setColor(QPalette.Text, QColor(text))
    palette.setColor(QPalette.WindowText, QColor(text))
    palette.setColor(QPalette.ButtonText, QColor(text))
    palette.setColor(QPalette.Button, QColor(base))
    palette.setColor(QPalette.ToolTipBase, QColor(base))
    palette.setColor(QPalette.ToolTipText, QColor(text))
    palette.setColor(QPalette.Highlight, QColor(accent))
    palette.setColor(QPalette.HighlightedText, QColor("#FFFFFF"))
    app.setPalette(palette)
    app.setStyleSheet(
        f"QPushButton#accent {{ background: {accent}; color: white; border: none;"
        f" padding: 7px 14px; border-radius: 6px; font-weight: 600; }}"
        f"QPushButton#accent:disabled {{ background: {mid}; color: {text}; }}"
        f"QProgressBar {{ border: 1px solid {mid}; border-radius: 4px; text-align: center; }}"
        f"QProgressBar::chunk {{ background: {accent}; border-radius: 3px; }}"
        f"QTabBar::tab {{ padding: 8px 14px; }}"
    )


# --------------------------------------------------------------------------- #
#  Helpers
# --------------------------------------------------------------------------- #
def make_table(headers: list[str]) -> QTableWidget:
    table = QTableWidget(0, len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.verticalHeader().setVisible(False)
    table.setEditTriggers(QTableWidget.NoEditTriggers)
    table.setSelectionBehavior(QTableWidget.SelectRows)
    table.horizontalHeader().setStretchLastSection(True)
    return table


def set_status_cell(table: QTableWidget, row: int, column: int, status: str, message: str = "") -> None:
    color = STATUS_STYLE.get(status, (status, None))[1]
    item = QTableWidgetItem(status_text(status, message))
    if color:
        item.setForeground(QColor(color))
    item.setToolTip(message or status_text(status, message))
    table.setItem(row, column, item)


# --------------------------------------------------------------------------- #
#  Tab: Top tracks
# --------------------------------------------------------------------------- #
class TopTracksTab(QWidget):
    COL_GROUP, COL_TRACK, COL_RANK, COL_STATUS, COL_PROGRESS = range(5)
    HEADERS = ["Group", "Track", "Deezer rank", "Status", "Progress"]

    def __init__(self, win: "MainWindow"):
        super().__init__()
        self.win = win
        self.rows: dict[str, int] = {}          # catalog_id -> row
        self.bars: dict[str, QProgressBar] = {}
        self._status: dict[str, tuple[int, str, str]] = {}   # catalog_id -> (row, status, message)
        self._build()
        self.load_groups()

    def _build(self):
        root = QVBoxLayout(self)
        top = QHBoxLayout()

        # --- groups ---
        self.groups_box = QGroupBox()
        gl = QVBoxLayout(self.groups_box)
        self.group_list = QListWidget()
        add_row = QHBoxLayout()
        self.group_input = QLineEdit()
        self.group_input.returnPressed.connect(self.add_group)
        self.add_btn = QPushButton("＋")
        self.add_btn.setFixedWidth(36)
        self.add_btn.clicked.connect(self.add_group)
        self.del_btn = QPushButton()
        self.del_btn.clicked.connect(self.remove_selected)
        self.imp_btn = QPushButton()
        self.imp_btn.clicked.connect(self.import_groups)
        self.save_btn = QPushButton()
        self.save_btn.clicked.connect(self.save_groups)
        add_row.addWidget(self.group_input)
        add_row.addWidget(self.add_btn)
        btn_row = QHBoxLayout()
        for b in (self.del_btn, self.imp_btn, self.save_btn):
            btn_row.addWidget(b)
        gl.addLayout(add_row)
        gl.addWidget(self.group_list)
        gl.addLayout(btn_row)

        # --- parameters ---
        self.params_box = QGroupBox()
        pf = QFormLayout(self.params_box)
        self.limit = QSpinBox()
        self.limit.setRange(1, 30)
        self.limit.setValue(30)
        self.min_rank = QSpinBox()
        self.min_rank.setRange(0, 100_000_000)
        self.min_rank.setSingleStep(10_000)
        self.min_rank.setValue(100_000)
        self.workers = QSpinBox()
        self.workers.setRange(1, 16)
        self.workers.setValue(4)
        self.lbl_limit = QLabel()
        self.lbl_min_rank = QLabel()
        self.lbl_workers = QLabel()
        pf.addRow(self.lbl_limit, self.limit)
        pf.addRow(self.lbl_min_rank, self.min_rank)
        pf.addRow(self.lbl_workers, self.workers)

        actions = QVBoxLayout()
        self.preview_btn = QPushButton()
        self.preview_btn.clicked.connect(lambda: self.start(dry_run=True))
        self.download_btn = QPushButton()
        self.download_btn.setObjectName("accent")
        self.download_btn.clicked.connect(lambda: self.start(dry_run=False))
        actions.addWidget(self.preview_btn)
        actions.addWidget(self.download_btn)
        actions.addStretch(1)

        right = QVBoxLayout()
        right.addWidget(self.params_box)
        right.addLayout(actions)

        top.addWidget(self.groups_box, 2)
        top.addLayout(right, 1)
        root.addLayout(top)

        self.table = make_table(self.HEADERS)
        root.addWidget(self.table, 1)
        self.legend = QLabel()
        self.legend.setStyleSheet("color: #64748B;")
        root.addWidget(self.legend)
        self.refresh_texts()

    # ---- translation ----
    def refresh_texts(self):
        self.groups_box.setTitle(i18n.t("Groups"))
        self.group_input.setPlaceholderText(i18n.t("Add a group and press Enter…"))
        self.del_btn.setText(i18n.t("Delete"))
        self.imp_btn.setText(i18n.t("Import"))
        self.save_btn.setText(i18n.t("Save"))
        self.params_box.setTitle(i18n.t("Parameters"))
        self.min_rank.setToolTip(i18n.t("Higher number = more popular track. Tracks below the threshold are skipped."))
        self.lbl_limit.setText(i18n.t("Tracks per group:"))
        self.lbl_min_rank.setText(i18n.t("Popularity threshold:"))
        self.lbl_workers.setText(i18n.t("Download threads:"))
        self.preview_btn.setText(i18n.t("👁 Preview"))
        self.download_btn.setText(i18n.t("⬇ Download"))
        self.table.setHorizontalHeaderLabels([i18n.t(h) for h in self.HEADERS])
        self.legend.setText(i18n.t("Legend: ✔ done · ⟳ already have · ⤼ skipped · ✖ error"))
        for cid, (row, status, message) in self._status.items():
            set_status_cell(self.table, row, self.COL_STATUS, status, message)

    # ---- groups ----
    def load_groups(self):
        self.group_list.clear()
        path = self.win.base_dir / "groups.txt"
        if path.exists():
            for name in core.read_groups(path):
                self._add_item(name)

    def _add_item(self, name: str):
        item = QListWidgetItem(name)
        item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
        item.setCheckState(Qt.Checked)
        self.group_list.addItem(item)

    def add_group(self):
        name = self.group_input.text().strip()
        if name:
            self._add_item(name)
            self.group_input.clear()

    def remove_selected(self):
        for item in self.group_list.selectedItems():
            self.group_list.takeItem(self.group_list.row(item))

    def import_groups(self):
        path, _ = QFileDialog.getOpenFileName(
            self, i18n.t("Import groups"), str(self.win.base_dir), i18n.t("Text (*.txt)"))
        if path:
            for name in core.read_groups(Path(path)):
                self._add_item(name)

    def save_groups(self):
        names = [self.group_list.item(i).text() for i in range(self.group_list.count())]
        (self.win.base_dir / "groups.txt").write_text(
            "# One group per line. Everything after # is a comment.\n" + "\n".join(names) + "\n",
            encoding="utf-8",
        )
        self.win.log(i18n.t("Saved groups: {count}", count=len(names)))

    def checked_groups(self) -> list[str]:
        return [
            self.group_list.item(i).text()
            for i in range(self.group_list.count())
            if self.group_list.item(i).checkState() == Qt.Checked
        ]

    # ---- run ----
    def start(self, dry_run: bool):
        if not dry_run and not self.win.require_ffmpeg():
            return
        groups = self.checked_groups()
        if not groups:
            self.win.log(i18n.t("No groups selected."))
            return
        self.table.setRowCount(0)
        self.rows.clear()
        self.bars.clear()
        self._status.clear()
        self.win.set_running(True)
        aliases = core.read_aliases(self.win.base_dir / "aliases.csv")
        folder = self.win.output_dir()
        limit, min_rank, workers = self.limit.value(), self.min_rank.value(), self.workers.value()

        def job(signals: WorkerSignals):
            tracks = []
            for group in groups:
                if self.win.cancel_event.is_set():
                    break
                signals.log.emit(i18n.t("{group}: fetching top tracks…", group=group))
                try:
                    found = core.deezer_top_tracks(group, limit, min_rank)
                    signals.log.emit(i18n.t("{group}: selected {count}", group=group, count=len(found)))
                    tracks.extend(found)
                except Exception as error:  # noqa: BLE001
                    signals.log.emit(i18n.t("{group}: error — {error}", group=group, error=error))
            # Show the rows before the download starts.
            for track in tracks:
                signals.event.emit({"type": "row", "track": track})
            outcomes = core.download_many(
                tracks, folder, aliases, workers, dry_run=dry_run,
                on_event=signals.event.emit,
                cancel=self.win.cancel_event.is_set,
            )
            return outcomes

        worker = Worker(job)
        worker.signals.log.connect(self.win.log)
        worker.signals.event.connect(self.handle_event)
        worker.signals.event.connect(self.win.note_event)
        worker.signals.finished.connect(lambda outcomes: self.win.finish_download(outcomes, dry_run))
        worker.signals.failed.connect(self.win.fail_operation)
        self.win.run_worker(worker)

    @Slot(object)
    def handle_event(self, event: dict):
        etype = event.get("type")
        if etype == "row":
            self._ensure_row(event["track"])
            return
        if etype != "status":
            return
        track = event["track"]
        row = self._ensure_row(track)
        status = event["status"]
        message = event.get("message", "")
        set_status_cell(self.table, row, self.COL_STATUS, status, message)
        self._status[track.catalog_id] = (row, status, message)
        bar = self.bars.get(track.catalog_id)
        if bar is not None:
            progress = event.get("progress")
            if status == "convert":
                bar.setRange(0, 0)
            elif progress is None:
                pass
            else:
                bar.setRange(0, 100)
                bar.setValue(int(progress * 100))
            if status in ("done", "preview"):
                bar.setRange(0, 100)
                bar.setValue(100)

    def _ensure_row(self, track) -> int:
        if track.catalog_id in self.rows:
            return self.rows[track.catalog_id]
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setItem(row, self.COL_GROUP, QTableWidgetItem(track.group))
        self.table.setItem(row, self.COL_TRACK, QTableWidgetItem(track.title))
        self.table.setItem(row, self.COL_RANK, QTableWidgetItem(f"{track.rank:,}".replace(",", " ") if track.rank else "—"))
        set_status_cell(self.table, row, self.COL_STATUS, "pending")
        bar = QProgressBar()
        bar.setRange(0, 100)
        bar.setValue(0)
        self.table.setCellWidget(row, self.COL_PROGRESS, bar)
        self.rows[track.catalog_id] = row
        self.bars[track.catalog_id] = bar
        return row


# --------------------------------------------------------------------------- #
#  Tab: Links
# --------------------------------------------------------------------------- #
class LinksTab(QWidget):
    COL_LINK, COL_NAME, COL_STATUS, COL_PROGRESS = range(4)
    HEADERS = ["Link", "Recognized as", "Status", "Progress"]

    def __init__(self, win: "MainWindow"):
        super().__init__()
        self.win = win
        self.rows: dict[str, int] = {}
        self.bars: dict[str, QProgressBar] = {}
        self._status: dict[str, tuple[int, str, str]] = {}
        self._build()
        self.load_links()

    def _build(self):
        root = QVBoxLayout(self)
        top = QHBoxLayout()
        self.links_box = QGroupBox()
        ll = QVBoxLayout(self.links_box)
        self.links_edit = QPlainTextEdit()
        ll.addWidget(self.links_edit)
        self.save = QPushButton()
        self.save.clicked.connect(self.save_links)
        ll.addWidget(self.save)

        self.params_box = QGroupBox()
        pf = QFormLayout(self.params_box)
        self.workers = QSpinBox()
        self.workers.setRange(1, 8)
        self.workers.setValue(3)
        self.lbl_workers = QLabel()
        pf.addRow(self.lbl_workers, self.workers)
        self.preview_btn = QPushButton()
        self.preview_btn.clicked.connect(lambda: self.start(dry_run=True))
        self.download_btn = QPushButton()
        self.download_btn.setObjectName("accent")
        self.download_btn.clicked.connect(lambda: self.start(dry_run=False))
        right = QVBoxLayout()
        right.addWidget(self.params_box)
        right.addWidget(self.preview_btn)
        right.addWidget(self.download_btn)
        right.addStretch(1)

        top.addWidget(self.links_box, 2)
        top.addLayout(right, 1)
        root.addLayout(top)
        self.table = make_table(self.HEADERS)
        root.addWidget(self.table, 1)
        self.refresh_texts()

    def refresh_texts(self):
        self.links_box.setTitle(i18n.t("YouTube Music links (one per line)"))
        self.links_edit.setPlaceholderText("https://music.youtube.com/watch?v=…")
        self.save.setText(i18n.t("Save to music_links.txt"))
        self.params_box.setTitle(i18n.t("Parameters"))
        self.lbl_workers.setText(i18n.t("Download threads:"))
        self.preview_btn.setText(i18n.t("👁 Preview"))
        self.download_btn.setText(i18n.t("⬇ Download"))
        self.table.setHorizontalHeaderLabels([i18n.t(h) for h in self.HEADERS])
        for cid, (row, status, message) in self._status.items():
            set_status_cell(self.table, row, self.COL_STATUS, status, message)

    def load_links(self):
        path = self.win.base_dir / "music_links.txt"
        if path.exists():
            lines = [l for l in path.read_text(encoding="utf-8-sig").splitlines()
                     if l.strip() and not l.lstrip().startswith("#")]
            self.links_edit.setPlainText("\n".join(lines))

    def save_links(self):
        text = self.links_edit.toPlainText().strip()
        (self.win.base_dir / "music_links.txt").write_text(
            "# One YouTube Music link per line.\n" + text + "\n", encoding="utf-8")
        self.win.log(i18n.t("Links saved."))

    def urls(self) -> list[str]:
        result = []
        for line in self.links_edit.toPlainText().splitlines():
            url = line.split("#", 1)[0].strip()
            if url.startswith(("https://music.youtube.com/", "https://www.youtube.com/", "https://youtu.be/")):
                result.append(url)
            elif url:
                self.win.log(i18n.t("Skipping invalid link: {url}", url=url))
        return list(dict.fromkeys(result))

    def start(self, dry_run: bool):
        if not dry_run and not self.win.require_ffmpeg():
            return
        urls = self.urls()
        if not urls:
            self.win.log(i18n.t("No valid links."))
            return
        self.table.setRowCount(0)
        self.rows.clear()
        self.bars.clear()
        self._status.clear()
        self.win.set_running(True)
        aliases = core.read_aliases(self.win.base_dir / "aliases.csv")
        folder = self.win.output_dir()
        workers = self.workers.value()

        def job(signals: WorkerSignals):
            tracks, sources = [], {}
            for url in urls:
                if self.win.cancel_event.is_set():
                    break
                try:
                    track = core.track_from_url(url)
                    sources[track.catalog_id] = url
                    tracks.append(track)
                    signals.event.emit({"type": "row", "track": track, "url": url})
                    signals.log.emit(i18n.t("found: {group} — {title}", group=track.group, title=track.title))
                except Exception as error:  # noqa: BLE001
                    signals.log.emit(i18n.t("link error {url}: {error}", url=url, error=error))
            outcomes = core.download_many(
                tracks, folder, aliases, workers, dry_run=dry_run, sources=sources,
                on_event=signals.event.emit, cancel=self.win.cancel_event.is_set)
            return outcomes

        worker = Worker(job)
        worker.signals.log.connect(self.win.log)
        worker.signals.event.connect(self.handle_event)
        worker.signals.event.connect(self.win.note_event)
        worker.signals.finished.connect(lambda outcomes: self.win.finish_download(outcomes, dry_run))
        worker.signals.failed.connect(self.win.fail_operation)
        self.win.run_worker(worker)

    @Slot(object)
    def handle_event(self, event: dict):
        etype = event.get("type")
        if etype == "row":
            self._ensure_row(event["track"], event.get("url", ""))
            return
        if etype != "status":
            return
        track = event["track"]
        row = self._ensure_row(track, "")
        status = event["status"]
        message = event.get("message", "")
        set_status_cell(self.table, row, self.COL_STATUS, status, message)
        self._status[track.catalog_id] = (row, status, message)
        bar = self.bars.get(track.catalog_id)
        if bar is not None:
            progress = event.get("progress")
            if status == "convert":
                bar.setRange(0, 0)
            elif progress is not None:
                bar.setRange(0, 100)
                bar.setValue(int(progress * 100))
            if status in ("done", "preview"):
                bar.setRange(0, 100)
                bar.setValue(100)

    def _ensure_row(self, track, url: str) -> int:
        if track.catalog_id in self.rows:
            row = self.rows[track.catalog_id]
            if url:
                self.table.setItem(row, self.COL_NAME, QTableWidgetItem(f"{track.group} — {track.title}"))
            return row
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setItem(row, self.COL_LINK, QTableWidgetItem((url[:40] + "…") if len(url) > 41 else url))
        self.table.setItem(row, self.COL_NAME, QTableWidgetItem(f"{track.group} — {track.title}"))
        set_status_cell(self.table, row, self.COL_STATUS, "pending")
        bar = QProgressBar()
        bar.setRange(0, 100)
        self.table.setCellWidget(row, self.COL_PROGRESS, bar)
        self.rows[track.catalog_id] = row
        self.bars[track.catalog_id] = bar
        return row


# --------------------------------------------------------------------------- #
#  Tab: MP3 check
# --------------------------------------------------------------------------- #
class CheckTab(QWidget):
    HEADERS = ["File", "Size", "Status"]

    def __init__(self, win: "MainWindow"):
        super().__init__()
        self.win = win
        self._build()
        self._broken: list = []

    def _build(self):
        root = QVBoxLayout(self)
        row = QHBoxLayout()
        self.folder_edit = QLineEdit(str(self.win.output_dir()))
        self.browse = QPushButton("📂")
        self.browse.clicked.connect(self.pick_folder)
        self.workers = QSpinBox()
        self.workers.setRange(1, 16)
        self.workers.setValue(4)
        self.check_btn = QPushButton()
        self.check_btn.setObjectName("accent")
        self.check_btn.clicked.connect(self.start)
        self.lbl_folder = QLabel()
        self.lbl_threads = QLabel()
        row.addWidget(self.lbl_folder)
        row.addWidget(self.folder_edit, 1)
        row.addWidget(self.browse)
        row.addWidget(self.lbl_threads)
        row.addWidget(self.workers)
        row.addWidget(self.check_btn)
        root.addLayout(row)
        self.table = make_table(self.HEADERS)
        root.addWidget(self.table, 1)
        bottom = QHBoxLayout()
        self.summary = QLabel("")
        self.save_report = QPushButton()
        self.save_report.clicked.connect(self.write_report)
        self.save_report.setEnabled(False)
        bottom.addWidget(self.summary, 1)
        bottom.addWidget(self.save_report)
        root.addLayout(bottom)
        self.refresh_texts()

    def refresh_texts(self):
        self.lbl_folder.setText(i18n.t("Folder:"))
        self.lbl_threads.setText(i18n.t("Threads:"))
        self.check_btn.setText(i18n.t("▶ Check integrity"))
        self.table.setHorizontalHeaderLabels([i18n.t(h) for h in self.HEADERS])
        self.save_report.setText(i18n.t("Save report"))

    def pick_folder(self):
        path = QFileDialog.getExistingDirectory(self, i18n.t("MP3 folder"), self.folder_edit.text())
        if path:
            self.folder_edit.setText(path)

    def start(self):
        if not self.win.require_ffmpeg():
            return
        folder = Path(self.folder_edit.text())
        if not folder.is_dir():
            self.win.log(i18n.t("Folder not found: {path}", path=folder))
            return
        self.table.setRowCount(0)
        self._broken = []
        self.save_report.setEnabled(False)
        self.win.set_running(True)
        workers = self.workers.value()

        def job(signals: WorkerSignals):
            return core.check_folder(folder, workers, on_result=lambda r: signals.event.emit({"type": "check", "result": r}))

        worker = Worker(job)
        worker.signals.event.connect(self.handle_event)
        worker.signals.finished.connect(self.finished)
        worker.signals.failed.connect(self.win.fail_operation)
        self.win.run_worker(worker)

    @Slot(object)
    def handle_event(self, event: dict):
        if event.get("type") != "check":
            return
        result = event["result"]
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setItem(row, 0, QTableWidgetItem(result.path.name))
        self.table.setItem(row, 1, QTableWidgetItem(i18n.t("{size} MB", size=f"{result.size / 1_048_576:.1f}")))
        status = QTableWidgetItem(i18n.t("✔ OK") if result.ok else f"✖ {result.message}")
        status.setForeground(QColor("#16A34A" if result.ok else "#DC2626"))
        status.setToolTip(result.message or i18n.t("✔ OK"))
        self.table.setItem(row, 2, status)
        if not result.ok:
            self._broken.append(result)

    def finished(self, results):
        self.win.set_running(False)
        total = len(results)
        bad = len(self._broken)
        self.summary.setText(i18n.t("Checked: {total} · OK: {ok} · broken: {bad}",
                                    total=total, ok=total - bad, bad=bad))
        self.save_report.setEnabled(bad > 0)
        self.win.log(i18n.t("Check completed: {total} files, {bad} broken.", total=total, bad=bad))

    def write_report(self):
        path = self.win.base_dir / "broken_mp3_report.txt"
        lines = [i18n.t("Broken MP3 (files kept in place):"), ""]
        for r in sorted(self._broken, key=lambda r: r.path):
            lines.extend((str(r.path), r.message, ""))
        path.write_text("\n".join(lines), encoding="utf-8")
        self.win.log(i18n.t("Report saved: {path}", path=path))


# --------------------------------------------------------------------------- #
#  Tab: Names (aliases)
# --------------------------------------------------------------------------- #
class AliasesTab(QWidget):
    HEADERS = ["group", "track", "group_ru", "track_ru"]   # CSV schema keys (not translated)

    def __init__(self, win: "MainWindow"):
        super().__init__()
        self.win = win
        self._build()
        self.load()

    def _build(self):
        root = QVBoxLayout(self)
        self.info = QLabel()
        self.info.setWordWrap(True)
        root.addWidget(self.info)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(self.HEADERS)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        root.addWidget(self.table, 1)
        row = QHBoxLayout()
        self.add = QPushButton()
        self.add.clicked.connect(lambda: self.table.insertRow(self.table.rowCount()))
        self.rem = QPushButton()
        self.rem.clicked.connect(self.remove_row)
        self.save_btn = QPushButton()
        self.save_btn.setObjectName("accent")
        self.save_btn.clicked.connect(self.save)
        for b in (self.add, self.rem):
            row.addWidget(b)
        row.addStretch(1)
        row.addWidget(self.save_btn)
        root.addLayout(row)
        self.refresh_texts()

    def refresh_texts(self):
        self.info.setText(i18n.t(
            "Set Russian name variants — they are used for the MP3 file name. "
            "Empty track = a variant for the whole group."))
        self.add.setText(i18n.t("＋ row"))
        self.rem.setText(i18n.t("Delete row"))
        self.save_btn.setText(i18n.t("Save aliases.csv"))

    def load(self):
        path = self.win.base_dir / "aliases.csv"
        self.table.setRowCount(0)
        aliases = core.read_aliases(path)
        for (group_key, track_key), (group_ru, track_ru) in aliases.items():
            r = self.table.rowCount()
            self.table.insertRow(r)
            for c, value in enumerate((group_key, track_key, group_ru, track_ru)):
                self.table.setItem(r, c, QTableWidgetItem(value))

    def remove_row(self):
        rows = {i.row() for i in self.table.selectedItems()}
        for r in sorted(rows, reverse=True):
            self.table.removeRow(r)

    def save(self):
        import csv
        path = self.win.base_dir / "aliases.csv"
        with path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(self.HEADERS)
            for r in range(self.table.rowCount()):
                values = [(self.table.item(r, c).text() if self.table.item(r, c) else "") for c in range(4)]
                if any(values):
                    writer.writerow(values)
        self.win.log(i18n.t("aliases.csv saved."))


# --------------------------------------------------------------------------- #
#  Main window
# --------------------------------------------------------------------------- #
class MainWindow(QMainWindow):
    def __init__(self, base_dir: Path):
        super().__init__()
        self.base_dir = base_dir
        self.pool = QThreadPool.globalInstance()
        # A Worker without an external reference is garbage-collected before it
        # can emit finished, which leaves the buttons disabled forever. So we
        # keep running workers alive here.
        self._workers: list[Worker] = []
        self.cancel_event = threading.Event()
        self.settings = QSettings("song-tools", APP_NAME)
        self._total = 0
        self._done = 0
        self._phase: tuple[str | None, str | None, dict] = ("Ready", None, {})
        self.resize(1000, 720)
        self._build()
        self.refresh_ffmpeg()

    def _build(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)

        # top status line
        status = QHBoxLayout()
        self.env_label = QLabel()
        self.output_edit = QLineEdit(str(self.base_dir / "mp3"))
        self.out_btn = QPushButton("📂")
        self.out_btn.setFixedWidth(36)
        self.out_btn.clicked.connect(self.pick_output)
        self.lbl_output = QLabel()
        self.lbl_language = QLabel()
        self.lang_combo = QComboBox()
        for code, name in i18n.LANGUAGE_NAMES.items():
            self.lang_combo.addItem(name, code)
        self.lang_combo.setCurrentIndex(max(0, self.lang_combo.findData(i18n.get_language())))
        self.lang_combo.currentIndexChanged.connect(self._on_language_changed)
        self.theme_btn = QToolButton()
        self.theme_btn.setText("🌙/☀")
        self.theme_btn.clicked.connect(self.toggle_theme)
        status.addWidget(self.env_label, 1)
        status.addWidget(self.lbl_output)
        status.addWidget(self.output_edit, 1)
        status.addWidget(self.out_btn)
        status.addWidget(self.lbl_language)
        status.addWidget(self.lang_combo)
        status.addWidget(self.theme_btn)
        root.addLayout(status)

        # tabs
        self.tabs = QTabWidget()
        self.top_tab = TopTracksTab(self)
        self.links_tab = LinksTab(self)
        self.check_tab = CheckTab(self)
        self.aliases_tab = AliasesTab(self)
        self.tabs.addTab(self.top_tab, "")
        self.tabs.addTab(self.links_tab, "")
        self.tabs.addTab(self.check_tab, "")
        self.tabs.addTab(self.aliases_tab, "")
        root.addWidget(self.tabs, 1)

        # bottom panel: progress + log
        bottom = QVBoxLayout()
        prow = QHBoxLayout()
        self.overall = QProgressBar()
        self.overall.setRange(0, 100)
        self.phase_label = QLabel()
        self.stop_btn = QPushButton()
        self.stop_btn.clicked.connect(self.stop)
        self.stop_btn.setEnabled(False)
        self.open_btn = QPushButton()
        self.open_btn.clicked.connect(self.open_output)
        prow.addWidget(self.phase_label)
        prow.addWidget(self.overall, 1)
        prow.addWidget(self.stop_btn)
        prow.addWidget(self.open_btn)
        bottom.addLayout(prow)
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumHeight(150)
        bottom.addWidget(self.log_view)
        root.addLayout(bottom)
        self.retranslate()

    # ---- localization ----
    def _on_language_changed(self, index: int):
        code = self.lang_combo.itemData(index)
        if not code:
            return
        i18n.set_language(code)
        self.settings.setValue("lang", code)
        self.retranslate()

    def retranslate(self):
        self.setWindowTitle(i18n.t("Top group tracks → MP3"))
        self.lbl_output.setText(i18n.t("Output folder:"))
        self.lbl_language.setText(i18n.t("Language:"))
        self.tabs.setTabText(0, i18n.t("🎵 Top tracks"))
        self.tabs.setTabText(1, i18n.t("🔗 Links"))
        self.tabs.setTabText(2, i18n.t("✔ MP3 check"))
        self.tabs.setTabText(3, i18n.t("🏷 Names"))
        self.stop_btn.setText(i18n.t("■ Stop"))
        self.open_btn.setText(i18n.t("Open folder"))
        for tab in (self.top_tab, self.links_tab, self.check_tab, self.aliases_tab):
            tab.refresh_texts()
        self._apply_phase()
        self.refresh_ffmpeg()

    # ---- environment ----
    def refresh_ffmpeg(self):
        self.ffmpeg_ok = core.ffmpeg_available()
        if self.ffmpeg_ok:
            self.env_label.setText(i18n.t("● FFmpeg found"))
            self.env_label.setStyleSheet("color: #16A34A;")
        else:
            self.env_label.setText(i18n.t("● FFmpeg not found — downloading unavailable"))
            self.env_label.setStyleSheet("color: #DC2626;")

    def require_ffmpeg(self) -> bool:
        self.refresh_ffmpeg()
        if not self.ffmpeg_ok:
            QMessageBox.warning(
                self, i18n.t("FFmpeg required"),
                i18n.t("FFmpeg was not found in PATH. It is required to convert to MP3.\n\n"
                       "Install FFmpeg (for example: winget install Gyan.FFmpeg) and restart the application."))
            return False
        return True

    # ---- output folder ----
    def output_dir(self) -> Path:
        return Path(self.output_edit.text())

    def pick_output(self):
        path = QFileDialog.getExistingDirectory(self, i18n.t("Output folder"), self.output_edit.text())
        if path:
            self.output_edit.setText(path)

    def open_output(self):
        folder = self.output_dir()
        folder.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    # ---- theme ----
    def toggle_theme(self):
        dark = not self.settings.value("dark", False, type=bool)
        self.settings.setValue("dark", dark)
        apply_theme(QApplication.instance(), dark)

    # ---- workers / progress / log ----
    def run_worker(self, worker: Worker):
        """Starts a worker, keeping a reference to it until it finishes."""
        self._workers.append(worker)
        worker.signals.finished.connect(lambda *_: self._drop_worker(worker))
        worker.signals.failed.connect(lambda *_: self._drop_worker(worker))
        self.pool.start(worker)

    def _drop_worker(self, worker: Worker):
        if worker in self._workers:
            self._workers.remove(worker)

    def log(self, message: str):
        self.log_view.appendPlainText(message)

    def set_phase(self, key: str | None = None, text: str | None = None, **fmt):
        self._phase = (key, text, fmt)
        self._apply_phase()

    def _apply_phase(self):
        key, text, fmt = self._phase
        self.phase_label.setText(i18n.t(key, **fmt) if key else (text or ""))

    def set_running(self, running: bool):
        if running:
            self.cancel_event.clear()
            self._total = 0
            self._done = 0
            self.overall.setValue(0)
            self.set_phase("Working…")
        self.stop_btn.setEnabled(running)
        for tab in (self.top_tab, self.links_tab, self.check_tab):
            for name in ("preview_btn", "download_btn", "check_btn"):
                btn = getattr(tab, name, None)
                if btn is not None:
                    btn.setEnabled(not running)

    def stop(self):
        self.cancel_event.set()
        self.set_phase("Stopping…")
        self.log(i18n.t("Stop requested."))

    @Slot(object)
    def note_event(self, event: dict):
        if event.get("type") == "row":
            self._total += 1
            self.overall.setRange(0, max(self._total, 1))
            return
        if event.get("type") == "status" and event.get("status") in ("done", "preview", "skipped_exists", "error"):
            self._done += 1
            self.overall.setValue(self._done)
            if self.stop_btn.isEnabled():
                self.set_phase(None, text=f"{self._done}/{self._total}")

    def finish_download(self, outcomes, dry_run: bool):
        self.set_running(False)
        done = sum(1 for o in outcomes if o.downloaded)
        seconds = sum(o.track.duration for o in outcomes if o.downloaded)
        errors = sum(1 for o in outcomes if o.status == "error")
        skipped = sum(1 for o in outcomes if o.status == "skipped_exists")
        verb = i18n.t("will be downloaded" if dry_run else "downloaded")
        self.set_phase("Preview ready" if dry_run else "Ready")
        self.overall.setValue(self.overall.maximum())
        self.log(i18n.t("Summary: {verb} {done} · skipped {skipped} · errors {errors} · duration {duration}.",
                        verb=verb, done=done, skipped=skipped, errors=errors,
                        duration=core.format_duration(seconds)))

    def fail_operation(self, message: str):
        self.set_running(False)
        self.set_phase("Error")
        self.log(i18n.t("Operation error: {message}", message=message))
        QMessageBox.critical(self, i18n.t("Error"), message)


def resolve_base_dir() -> Path:
    """Folder holding data (groups.txt, aliases.csv, mp3…).

    In a PyInstaller onefile build ``__file__`` points into the temporary
    extraction folder, so we take data from next to the .exe itself.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def main() -> int:
    base_dir = resolve_base_dir()
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)

    def _log_crash(exc_type, exc, tb):
        """A windowed .exe has no console — write the traceback next to the app."""
        try:
            (base_dir / "error.log").write_text(
                "".join(traceback.format_exception(exc_type, exc, tb)), encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass
        sys.__excepthook__(exc_type, exc, tb)

    sys.excepthook = _log_crash
    settings = QSettings("song-tools", APP_NAME)
    i18n.set_language(settings.value("lang") or i18n.detect_language())
    apply_theme(app, settings.value("dark", False, type=bool))
    window = MainWindow(base_dir)
    window.show()
    if not window.ffmpeg_ok:
        QMessageBox.information(
            window, i18n.t("FFmpeg not found"),
            i18n.t("FFmpeg was not found in PATH. Downloading and MP3 checking will be unavailable "
                   "until you install FFmpeg and restart the application.\n\n"
                   "List editing and preview work without it."))
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
