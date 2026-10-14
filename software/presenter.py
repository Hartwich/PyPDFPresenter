"""Small offline PDF presenter. Rendering is confined to one worker thread."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import queue
import re
import sys
import tempfile
import time

SOFTWARE = Path(__file__).resolve().parent
ROOT = SOFTWARE if getattr(sys, 'frozen', False) else SOFTWARE.parent
sys.path.insert(0, str(ROOT / '.deps'))
import pymupdf
from PySide6.QtCore import Qt, QThread, Signal, QTimer, QUrl, QRectF, QStandardPaths, QTranslator, QLibraryInfo
from i18n import tr as _t, select_language
from PySide6.QtGui import QPixmap, QPainter, QColor, QShortcut, QKeySequence, QFontDatabase, QFont, QImage
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput, QVideoSink
from PySide6.QtWidgets import (QApplication, QWidget, QMainWindow, QVBoxLayout,
    QHBoxLayout, QLabel, QPushButton, QComboBox, QSpinBox, QFileDialog, QMessageBox,
    QSplitter, QCheckBox, QPlainTextEdit, QStackedWidget)


def clips(rect, mode):
    if mode == 'right':
        mid = (rect.x0 + rect.x1) / 2
        return pymupdf.Rect(rect.x0, rect.y0, mid, rect.y1), pymupdf.Rect(mid, rect.y0, rect.x1, rect.y1)
    if mode == 'left':
        notes, slide = clips(rect, 'right')
        return slide, notes
    return rect, None


def render_page(doc, index, mode, folder):
    slide, notes = clips(doc[index].rect, mode)
    result = []
    for name, clip, width in [('slide', slide, 1920), ('notes', notes, 1440)]:
        target = folder / f'{index:04d}-{name}.png'
        if clip is not None and not target.exists():
            pix = doc[index].get_pixmap(matrix=pymupdf.Matrix(width / clip.width, width / clip.width), clip=clip, alpha=False)
            temporary = target.with_suffix('.part.png')
            pix.save(str(temporary))
            os.replace(temporary, target)
        result.append(str(target) if clip is not None else '')
    return result


def reference(doc, xref, key):
    kind, value = doc.xref_get_key(xref, key)
    return int(value.split()[0]) if kind == 'xref' else None


def extract_videos(doc, mode, folder, pdf):
    """Read PDF Screen/Rendition and Movie annotations without executing PDF actions."""
    videos = {}
    for index, page in enumerate(doc):
        slide, _ = clips(page.rect, mode)
        for xref, kind, _ in page.annot_xrefs():
            if kind not in (19, 22):
                continue
            if kind == 22:
                file_ref = xref
                for key in ('A', 'R', 'C', 'D'):
                    file_ref = reference(doc, file_ref, key) if file_ref else None
            else:
                file_ref = reference(doc, xref, 'Movie/F')
            if not file_ref:
                continue
            filename = doc.xref_get_key(file_ref, 'UF')[1]
            if filename == 'null':
                filename = doc.xref_get_key(file_ref, 'F')[1]
            embedded = reference(doc, file_ref, 'EF/F') or reference(doc, file_ref, 'EF/UF')
            if embedded:
                suffix = Path(filename).suffix.lower()
                if suffix not in ('.mp4', '.mov', '.m4v', '.webm', '.avi', '.mkv'):
                    suffix = '.mp4'
                target = folder / f'video-{index}-{xref}{suffix}'
                if not target.exists():
                    target.write_bytes(doc.xref_stream(embedded))
            else:
                target = (pdf.parent / filename).resolve()
                if not target.is_file():
                    continue
            value = doc.xref_get_key(xref, 'Rect')[1]
            numbers = re.findall(r'-?\d+(?:\.\d+)?', value)
            if len(numbers) != 4:
                continue
            rect = pymupdf.Rect(*map(float, numbers)) * page.transformation_matrix
            rect &= slide
            if rect.is_empty:
                continue
            normalized = ((rect.x0 - slide.x0) / slide.width, (rect.y0 - slide.y0) / slide.height,
                          rect.width / slide.width, rect.height / slide.height)
            videos.setdefault(index, []).append({'path': str(target), 'rect': normalized, 'name': filename})
    return videos


class Renderer(QThread):
    ready = Signal(int, str, str)
    media_ready = Signal(object)
    failed = Signal(str)
    def __init__(self, pdf, mode, count):
        super().__init__()
        self.pdf, self.mode = pdf, mode
        identity = f'v1:{pdf.resolve()}:{pdf.stat().st_size}:{pdf.stat().st_mtime_ns}:{mode}'
        base = Path(os.environ.get('PYPDFPRESENTER_CACHE_DIR') or QStandardPaths.writableLocation(QStandardPaths.StandardLocation.CacheLocation)) / 'cache'
        self.folder = base / hashlib.sha256(identity.encode()).hexdigest()[:24]
        self.jobs = queue.PriorityQueue()
        self.serial = 0
        for index in range(count):
            self.request(index, 10)

    def request(self, index, priority=0):
        self.serial += 1
        self.jobs.put((priority, self.serial, index))

    def run(self):
        try:
            self.folder.mkdir(parents=True, exist_ok=True)
            with pymupdf.open(self.pdf) as doc:
                self.media_ready.emit(extract_videos(doc, self.mode, self.folder, self.pdf))
                done = set()
                while not self.isInterruptionRequested():
                    try:
                        _, _, index = self.jobs.get(timeout=0.1)
                    except queue.Empty:
                        continue
                    if index in done:
                        continue
                    paths = render_page(doc, index, self.mode, self.folder)
                    done.add(index)
                    self.ready.emit(index, *paths)
        except Exception as error:
            self.failed.emit(str(error))


class ImageView(QWidget):
    video_clicked = Signal()
    pointer_moved = Signal(object)
    def __init__(self):
        super().__init__()
        self.pixmap = QPixmap()
        self.black = False
        self.video_frame = QImage()
        self.video_rect = None
        self.laser_enabled = False
        self.pointer = None
        self.empty_text = ''
        self.setMouseTracking(True)
        self.setMinimumSize(120, 80)

    def set_image(self, path=''):
        self.pixmap = QPixmap(path) if path else QPixmap()
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor('#000000'))
        if self.black:
            return
        if self.pixmap.isNull():
            painter.setPen(QColor('#98abc4'))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self.empty_text)
            return
        scaled = self.pixmap.size().scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio)
        x, y = (self.width() - scaled.width()) // 2, (self.height() - scaled.height()) // 2
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.drawPixmap(x, y, scaled.width(), scaled.height(), self.pixmap)
        if self.video_rect is not None and not self.video_frame.isNull():
            a, b, w, h = self.video_rect
            box = QRectF(x + a * scaled.width(), y + b * scaled.height(), w * scaled.width(), h * scaled.height())
            painter.fillRect(box, QColor('black'))
            size = self.video_frame.size().scaled(box.size().toSize(), Qt.AspectRatioMode.KeepAspectRatio)
            destination = QRectF(box.center().x() - size.width() / 2, box.center().y() - size.height() / 2, size.width(), size.height())
            painter.drawImage(destination, self.video_frame)
        if self.laser_enabled and self.pointer is not None:
            px = x + self.pointer[0] * scaled.width()
            py = y + self.pointer[1] * scaled.height()
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setPen(Qt.PenStyle.NoPen)
            for radius, alpha in [(15, 35), (10, 65), (6, 230)]:
                painter.setBrush(QColor(255, 35, 50, alpha))
                painter.drawEllipse(QRectF(px - radius, py - radius, radius * 2, radius * 2))
            painter.setBrush(QColor(255, 235, 235))
            painter.drawEllipse(QRectF(px - 2, py - 2, 4, 4))

    def slide_position(self, position):
        if self.pixmap.isNull():
            return None
        size = self.pixmap.size().scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio)
        x, y = (self.width() - size.width()) / 2, (self.height() - size.height()) / 2
        a, b = (position.x() - x) / size.width(), (position.y() - y) / size.height()
        return (a, b) if 0 <= a <= 1 and 0 <= b <= 1 else None

    def mouseMoveEvent(self, event):
        if self.laser_enabled:
            self.pointer_moved.emit(self.slide_position(event.position()))

    def leaveEvent(self, event):
        if self.laser_enabled:
            self.pointer_moved.emit(None)

    def set_laser(self, enabled):
        self.laser_enabled = enabled
        self.pointer = None
        self.setCursor(Qt.CursorShape.BlankCursor if enabled else Qt.CursorShape.ArrowCursor)
        self.update()

    def mousePressEvent(self, event):
        if self.laser_enabled:
            self.pointer_moved.emit(self.slide_position(event.position()))
            return
        if self.video_rect is not None and not self.pixmap.isNull() and not self.black:
            size = self.pixmap.size().scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio)
            x, y = (self.width() - size.width()) / 2, (self.height() - size.height()) / 2
            a, b, w, h = self.video_rect
            if QRectF(x + a * size.width(), y + b * size.height(), w * size.width(), h * size.height()).contains(event.position()):
                self.video_clicked.emit()


class Output(ImageView):
    visibility_changed = Signal(bool)
    def showEvent(self, event):
        super().showEvent(event)
        self.visibility_changed.emit(True)

    def hideEvent(self, event):
        super().hideEvent(event)
        self.visibility_changed.emit(False)

    def closeEvent(self, event):
        event.ignore()
        self.hide()


class NoteEditor(QPlainTextEdit):
    editing_focus = Signal(bool)
    def focusInEvent(self, event):
        super().focusInEvent(event)
        self.editing_focus.emit(True)

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        self.editing_focus.emit(False)


class Presenter(QMainWindow):
    def __init__(self, pdf=None, mode='auto'):
        super().__init__()
        self.worker = None
        self.paths = {}
        self.videos = {}
        self.index = 0
        self.pdf = None
        self.count = 0
        self.autoplay_page = None
        self.speaker_notes = {}
        self.notes_path = None
        self.notes_document = {}
        self.notes_dirty = False
        self.editing_notes = False
        self.notes_autosave = QTimer(self)
        self.notes_autosave.setSingleShot(True)
        self.notes_autosave.setInterval(500)
        self.notes_autosave.timeout.connect(self.save_notes)
        self.elapsed = 0
        self.started = None
        self.output = Output()
        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.player.setAudioOutput(self.audio)
        self.sink = QVideoSink(self)
        self.player.setVideoSink(self.sink)
        self.sink.videoFrameChanged.connect(self.video_frame)
        self.player.errorOccurred.connect(lambda error, text: QMessageBox.warning(self, _t('Videofehler'), text))
        self.output.setWindowTitle(_t('PyPDFPresenter - Publikum'))
        self.output.resize(960, 540)
        self.setWindowTitle(_t('PyPDFPresenter - Referentenansicht'))
        self.resize(1280, 850)
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        self.header_bar = QWidget()
        bar = QHBoxLayout(self.header_bar)
        bar.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.header_bar)
        self.button(bar, _t('PDF öffnen'), self.open_pdf)
        self.mode = QComboBox()
        self.mode.addItems([_t('Automatisch'), _t('Notizen rechts'), _t('Notizen links'), _t('Keine Notizen')])
        self.mode.setCurrentIndex(['auto', 'right', 'left', 'none'].index(mode))
        bar.addWidget(self.mode)
        self.mode.currentIndexChanged.connect(lambda: self.load(self.pdf) if self.pdf else None)
        self.screen = QComboBox()
        bar.addWidget(self.screen)
        self.refresh_screens()
        QApplication.instance().screenAdded.connect(self.refresh_screens)
        QApplication.instance().screenRemoved.connect(self.refresh_screens)
        self.start_button = self.button(bar, _t('Präsentation starten · F5'), self.toggle_presentation)
        self.output.visibility_changed.connect(self.output_visibility_changed)
        self.black_button = self.button(bar, _t('Schwarz · B'), self.toggle_black)
        self.notes_load_button = self.button(bar, _t('JSON laden'), self.open_notes)
        self.note_source = QComboBox()
        self.note_source.addItems([_t('PDF-Notizen'), _t('Text / JSON')])
        self.note_source.currentIndexChanged.connect(self.update_note_source)
        bar.addWidget(self.note_source)
        self.arrangement = QComboBox()
        self.arrangement.addItems([_t('Unter den Notizen'), _t('Unter der aktuellen Folie'), _t('Unten: nächste Folie und ihre Notizen')])
        self.arrangement.setCurrentIndex(2)
        self.arrangement.setMinimumContentsLength(12)
        self.arrangement.setMinimumWidth(120)
        self.arrangement.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.arrangement.setToolTip(self.arrangement.currentText())
        self.arrangement.currentTextChanged.connect(self.arrangement.setToolTip)
        self.counter = QLabel(_t('Keine PDF geladen'))
        bar.addStretch()
        bar.addWidget(self.counter)
        self.laser = QCheckBox(_t('Laserpointer · L'))
        self.laser.toggled.connect(self.set_laser)
        self.autoplay = QCheckBox(_t('Automatisch Abspielen'))
        self.autoplay.toggled.connect(lambda checked: self.maybe_autoplay() if checked else None)
        self.current, self.notes, self.next, self.next_notes = ImageView(), ImageView(), ImageView(), ImageView()
        self.current.empty_text = _t('Präsentation über „PDF öffnen“ laden')
        notes_area = self.build_notes_area()
        self.panels = [self.panel(_t('AKTUELLE FOLIE'), self.current), self.panel(_t('NOTIZEN'), notes_area),
                       self.panel(_t('NÄCHSTE PDF-SEITE / EINBLENDUNG'), self.next),
                       self.panel(_t('NOTIZEN DER NÄCHSTEN PDF-SEITE'), self.next_notes_stack)]
        content = QWidget()
        self.content_layout = QVBoxLayout(content)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.layout_root = None
        layout.addWidget(content, 1)
        self.arrangement.currentIndexChanged.connect(self.rebuild_layout)
        self.rebuild_layout()
        self.current.pointer_moved.connect(self.move_pointer)
        self.output.pointer_moved.connect(self.move_pointer)
        laser_row = QHBoxLayout()
        self.back_button = self.button(laser_row, _t('← Zurück'), lambda: self.go(self.index - 1))
        self.forward_button = self.button(laser_row, _t('Weiter →'), lambda: self.go(self.index + 1))
        laser_row.addWidget(self.laser)
        laser_row.addStretch()
        self.clock = QLabel('00:00')
        self.clock.setStyleSheet('font-size: 28px; font-weight: 600')
        laser_row.addWidget(self.clock)
        self.timer_button = self.button(laser_row, _t('Timer starten'), self.toggle_timer)
        self.timer_reset_button = self.button(laser_row, _t('Zurücksetzen'), self.reset_timer)
        self.clean_view_button = self.button(laser_row, 'Clean View', self.toggle_clean_view)
        self.clean_view_button.setCheckable(True)
        layout.addLayout(laser_row)
        self.lower_bar = QWidget()
        controls = QHBoxLayout(self.lower_bar)
        controls.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.lower_bar)
        controls.addWidget(QLabel(_t('PDF-Seite:')))
        self.jump = QSpinBox()
        self.jump.setMinimumWidth(92)
        self.jump.valueChanged.connect(lambda value: self.go(value - 1))
        controls.addWidget(self.jump)
        self.video_button = self.button(controls, _t('Video abspielen · V'), self.toggle_video)
        self.video_reset_button = self.button(controls, _t('Video zurücksetzen'), self.stop_video)
        controls.addWidget(self.autoplay)
        controls.addWidget(QLabel(_t('Vorschau:')))
        controls.addWidget(self.arrangement)
        controls.addStretch()
        self.video_button.setEnabled(False)
        self.current.video_clicked.connect(self.toggle_video)
        self.output.video_clicked.connect(self.toggle_video)
        self.player.playbackStateChanged.connect(lambda state: self.video_button.setText(
            _t('Video pausieren · V') if state == QMediaPlayer.PlaybackState.PlayingState else _t('Video abspielen · V')))
        self.shortcuts = []
        for key, action in [('Right', lambda: self.go(self.index + 1)), ('Space', lambda: self.go(self.index + 1)),
                            ('PgDown', lambda: self.go(self.index + 1)), ('Left', lambda: self.go(self.index - 1)),
                            ('PgUp', lambda: self.go(self.index - 1)), ('Home', lambda: self.go(0)),
                            ('End', lambda: self.go(self.count - 1)), ('F5', self.toggle_presentation),
                            ('B', self.toggle_black), ('V', self.toggle_video), ('L', lambda: self.laser.toggle()),
                            ('Escape', self.output.hide)]:
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
            shortcut.activated.connect(action)
            self.shortcuts.append(shortcut)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(250)
        self.set_document_controls(False)
        if pdf:
            self.load(Path(pdf))

    def button(self, layout, title, action):
        button = QPushButton(title)
        button.clicked.connect(action)
        layout.addWidget(button)
        return button

    def toggle_clean_view(self):
        clean = self.clean_view_button.isChecked()
        self.header_bar.setVisible(not clean)
        self.lower_bar.setVisible(not clean)

    def set_document_controls(self, enabled):
        for widget in (self.start_button, self.back_button, self.forward_button,
                       self.jump, self.video_reset_button, self.black_button):
            widget.setEnabled(enabled)
        for widget in (self.notes_load_button, self.note_source):
            widget.setEnabled(enabled)
        self.notes_editor.setReadOnly(True)
        self.notes_edit_button.setEnabled(enabled and self.note_source.currentIndex() == 1)

    def build_notes_area(self):
        area = QWidget()
        layout = QVBoxLayout(area)
        layout.setContentsMargins(0, 0, 0, 0)
        self.font_controls = QWidget()
        font_layout = QHBoxLayout(self.font_controls)
        font_layout.setContentsMargins(0, 0, 0, 0)
        font_layout.addWidget(QLabel(_t('Schrift:')))
        self.note_font = QSpinBox()
        self.note_font.setMinimumWidth(120)
        self.note_font.setRange(10, 64)
        self.note_font.setValue(22)
        self.note_font.setSuffix(' pt')
        self.note_font.valueChanged.connect(self.change_note_font)
        font_layout.addWidget(self.note_font)
        font_layout.addStretch()
        self.notes_status = QLabel(_t('Keine JSON geladen'))
        self.notes_status.setWordWrap(True)
        self.notes_status.hide()
        layout.addWidget(self.notes_status)
        self.notes_editor = NoteEditor()
        self.notes_editor.setPlaceholderText(_t('Eine JSON über „JSON laden“ öffnen.\nZum Ändern „Notizen bearbeiten“ wählen.'))
        self.notes_editor.setReadOnly(True)
        self.notes_editor.textChanged.connect(self.edit_notes)
        self.notes_editor.editing_focus.connect(self.set_editing_focus)
        self.notes_stack = QStackedWidget()
        self.notes_stack.addWidget(self.notes)
        self.notes_stack.addWidget(self.notes_editor)
        layout.addWidget(self.notes_stack, 1)
        footer = QHBoxLayout()
        self.notes_edit_button = self.button(footer, _t('Notizen bearbeiten'), self.toggle_note_editing)
        self.notes_edit_button.hide()
        footer.addWidget(self.font_controls)
        layout.addLayout(footer)
        self.font_controls.hide()
        self.next_notes_text = QPlainTextEdit()
        self.next_notes_text.setReadOnly(True)
        self.next_notes_text.setPlaceholderText(_t('Keine Textnotizen für die nächste PDF-Seite.'))
        self.next_notes_stack = QStackedWidget()
        self.next_notes_stack.addWidget(self.next_notes)
        self.next_notes_stack.addWidget(self.next_notes_text)
        self.apply_note_font()
        return area

    def set_editing_focus(self, editing):
        # Plain presentation shortcuts must not consume letters, spaces or cursor keys.
        for shortcut in getattr(self, 'shortcuts', []):
            if shortcut.key().toString() not in ('F5', 'Esc'):
                shortcut.setEnabled(not self.editing_notes)

    def update_note_source(self, *args):
        text = self.note_source.currentIndex() == 1
        if not text and self.editing_notes and not self.finish_note_editing():
            self.note_source.blockSignals(True)
            self.note_source.setCurrentIndex(1)
            self.note_source.blockSignals(False)
            return
        self.notes_stack.setCurrentIndex(int(text))
        self.next_notes_stack.setCurrentIndex(int(text))
        self.font_controls.setVisible(text)
        self.notes_edit_button.setVisible(text)
        self.notes_edit_button.setEnabled(text and self.pdf is not None)
        self.update_note_button()
        self.update_notes_status()
        if not text:
            self.set_editing_focus(False)
        self.update_note_text()

    def apply_note_font(self):
        style = f'QPlainTextEdit {{ background: #202b3b; color: #edf2fa; font-size: {self.note_font.value()}pt; padding: 10px; border: 1px solid #40516b; }}'
        self.notes_editor.setStyleSheet(style)
        self.next_notes_text.setStyleSheet(style)

    def change_note_font(self, *args):
        self.apply_note_font()
        if self.pdf and self.notes_path and self.note_source.currentIndex() == 1:
            self.notes_dirty = True
            self.update_notes_status()
            self.notes_autosave.start()

    def toggle_note_editing(self):
        if not self.pdf or self.note_source.currentIndex() != 1:
            return
        if self.editing_notes:
            self.finish_note_editing()
        elif self.notes_path or self.create_notes_file():
            self.editing_notes = True
            self.notes_editor.setReadOnly(False)
            self.update_note_button()
            self.set_editing_focus(True)
            self.notes_editor.setFocus()

    def finish_note_editing(self):
        if not self.confirm_notes_saved():
            return False
        self.editing_notes = False
        self.notes_editor.setReadOnly(True)
        self.update_note_button()
        self.set_editing_focus(False)
        return True

    def update_note_button(self):
        title = _t('Bearbeitung beenden') if self.editing_notes else (_t('Notizen bearbeiten') if self.notes_path else _t('Notizen anlegen'))
        self.notes_edit_button.setText(title)
        self.notes_editor.setPlaceholderText(_t('Zum Ändern „Notizen bearbeiten“ wählen.') if self.notes_path else
            _t('Über „Notizen anlegen“ eine JSON erstellen oder oben „JSON laden“ wählen.'))

    def create_notes_file(self):
        filename, _ = QFileDialog.getSaveFileName(self, _t('Notizdatei anlegen'), str(self.pdf.with_suffix('.notes.json')), 'JSON (*.json)',
                                                options=QFileDialog.Option.DontConfirmOverwrite)
        if not filename:
            return False
        path = Path(filename)
        if path.suffix.lower() != '.json':
            path = Path(str(path) + '.json')
        # Selecting an existing JSON opens its content rather than clearing it.
        if path.exists():
            return self.load_notes(path)
        self.notes_path = path
        if not self.save_notes():
            self.notes_path = None
            self.update_notes_status()
            self.update_note_button()
            return False
        self.update_note_button()
        return True

    def update_note_text(self):
        text = self.speaker_notes.get(str(self.index + 1), '')
        # Background render signals should not reset the editor's cursor or undo history.
        if self.notes_editor.toPlainText() != text:
            self.notes_editor.blockSignals(True)
            self.notes_editor.setPlainText(text)
            self.notes_editor.blockSignals(False)
        upcoming = self.speaker_notes.get(str(self.index + 2), '') if self.index + 1 < self.count else ''
        if self.next_notes_text.toPlainText() != upcoming:
            self.next_notes_text.setPlainText(upcoming)

    def edit_notes(self):
        if not self.pdf or not self.editing_notes:
            return
        text = self.notes_editor.toPlainText()
        key = str(self.index + 1)
        if text:
            self.speaker_notes[key] = text
        else:
            self.speaker_notes.pop(key, None)
        self.notes_dirty = True
        self.update_notes_status()
        self.notes_autosave.start()

    def update_notes_status(self):
        self.notes_status.setVisible(self.note_source.currentIndex() == 1)
        name = self.notes_path.name if self.notes_path else _t('Keine JSON geladen')
        suffix = _t(' · Speichern ausstehend') if self.notes_dirty else ''
        outside = sum(int(page) > self.count for page in self.speaker_notes)
        extra = _t(' · {count} Einträge außerhalb dieser PDF').format(count=outside) if outside else ''
        self.notes_status.setText(f'{name}{suffix}{extra}')
        self.notes_status.setToolTip(str(self.notes_path) if self.notes_path else '')

    def confirm_notes_saved(self):
        if not self.notes_dirty:
            return True
        return self.save_notes()

    def open_notes(self):
        if not self.pdf:
            return
        filename, _ = QFileDialog.getOpenFileName(self, _t('Sprechtexte laden'), str(self.pdf.parent), 'JSON (*.json)')
        if filename:
            self.load_notes(Path(filename))

    def load_notes(self, path):
        # Flush before reading, including when reloading the currently edited file.
        if not self.confirm_notes_saved():
            return False
        try:
            document = json.loads(Path(path).read_text(encoding='utf-8-sig'))
            if not isinstance(document, dict) or document.get('version', 1) != 1:
                raise ValueError(_t('Erwartet wird ein JSON-Objekt mit version: 1.'))
            notes = document.get('notes')
            if not isinstance(notes, dict):
                raise ValueError(_t('Das Feld notes muss PDF-Seitennummern auf Sprechtexte abbilden, z. B. {"1": "Einleitung"}.'))
            normalized = {}
            for key, text in notes.items():
                if not str(key).isdigit() or int(key) < 1 or not isinstance(text, str):
                    raise ValueError(_t('Jeder Notizeintrag braucht eine positive Seitennummer und einen Text.'))
                page = str(int(key))
                if page in normalized:
                    raise ValueError(_t('Doppelte Seitennummern, z. B. 1 und 01, sind nicht zulässig.'))
                normalized[page] = text
            size = document.get('font_size', self.note_font.value())
            if type(size) is not int or not 10 <= size <= 64:
                raise ValueError(_t('font_size muss eine ganze Zahl zwischen 10 und 64 sein.'))
        except (OSError, ValueError, TypeError) as error:
            QMessageBox.critical(self, _t('JSON kann nicht geladen werden'), str(error))
            return False
        self.finish_note_editing()
        self.speaker_notes, self.notes_document, self.notes_path = normalized, document, Path(path)
        self.note_font.blockSignals(True)
        self.note_font.setValue(size)
        self.note_font.blockSignals(False)
        self.apply_note_font()
        self.notes_dirty = False
        self.note_source.setCurrentIndex(1)
        self.update_note_text()
        self.update_notes_status()
        self.update_note_source()
        return True

    def save_notes(self):
        self.notes_autosave.stop()
        if not self.pdf or not self.notes_path:
            return False
        path = self.notes_path
        document = dict(self.notes_document)
        document.update({'version': 1, 'pdf': self.pdf.name, 'font_size': self.note_font.value(),
                         'notes': dict(sorted(self.speaker_notes.items(), key=lambda entry: int(entry[0])))})
        temporary = None
        try:
            # Replace only after a complete write, so an interrupted save keeps the old JSON.
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, delete=False, suffix='.tmp') as file:
                temporary = Path(file.name)
                json.dump(document, file, ensure_ascii=False, indent=2)
                file.write('\n')
            os.replace(temporary, path)
        except OSError as error:
            if temporary:
                temporary.unlink(missing_ok=True)
            QMessageBox.critical(self, _t('Notizen können nicht gespeichert werden'), str(error))
            return False
        self.notes_path, self.notes_document, self.notes_dirty = path, document, False
        self.update_notes_status()
        self.update_note_button()
        return True

    def panel(self, title, image):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        label = QLabel(title)
        label.setStyleSheet('color: #98abc4; font-weight: 600; padding-top: 6px')
        layout.addWidget(label)
        layout.addWidget(image, 1)
        return widget

    def rebuild_layout(self, *args):
        for panel in self.panels:
            panel.hide()
            panel.setParent(None)
        if self.layout_root:
            self.content_layout.removeWidget(self.layout_root)
            self.layout_root.deleteLater()
        current, notes, upcoming, next_notes = self.panels
        def split(orientation, widgets, sizes):
            result = QSplitter(orientation)
            result.setChildrenCollapsible(False)
            for widget in widgets:
                result.addWidget(widget)
            result.setSizes(sizes)
            return result
        mode = self.arrangement.currentIndex()
        if mode == 0:
            column = split(Qt.Orientation.Vertical, [notes, upcoming], [570, 250])
            root = split(Qt.Orientation.Horizontal, [current, column], [750, 500])
        elif mode == 1:
            column = split(Qt.Orientation.Vertical, [current, upcoming], [570, 250])
            root = split(Qt.Orientation.Horizontal, [column, notes], [750, 500])
        else:
            top = split(Qt.Orientation.Horizontal, [current, notes], [750, 500])
            bottom = split(Qt.Orientation.Horizontal, [upcoming, next_notes], [750, 500])
            root = split(Qt.Orientation.Vertical, [top, bottom], [570, 250])
        self.layout_root = root
        self.content_layout.addWidget(root)
        for panel in self.panels[:3]:
            panel.show()
        if mode == 2:
            next_notes.show()

    def set_laser(self, enabled):
        for view in (self.current, self.output):
            view.set_laser(enabled)

    def move_pointer(self, position):
        for view in (self.current, self.output):
            view.pointer = position
            view.update()

    def refresh_screens(self, *args):
        self.screen.clear()
        for index, screen in enumerate(QApplication.screens()):
            self.screen.addItem(_t('Bildschirm {number}: {name}').format(number=index + 1, name=screen.name()))
        self.screen.setCurrentIndex(min(1, self.screen.count() - 1))

    def stop_worker(self):
        if self.worker:
            self.worker.ready.disconnect()
            self.worker.failed.disconnect()
            self.worker.media_ready.disconnect()
            self.worker.requestInterruption()
            self.worker.wait()
            self.worker = None

    def load(self, pdf):
        try:
            with pymupdf.open(pdf) as doc:
                if doc.needs_pass:
                    raise ValueError(_t('Passwortgeschützte PDFs werden noch nicht unterstützt.'))
                count = len(doc)
                if not count:
                    raise ValueError(_t('Die PDF enthält keine Seiten.'))
                mode = ['auto', 'right', 'left', 'none'][self.mode.currentIndex()]
                if mode == 'auto':
                    mode = 'right' if doc[0].rect.width / doc[0].rect.height > 2.5 else 'none'
        except Exception as error:
            QMessageBox.critical(self, _t('PDF kann nicht geöffnet werden'), str(error))
            return
        changed_pdf = self.pdf is None or Path(pdf).resolve() != self.pdf.resolve()
        if changed_pdf and not self.confirm_notes_saved():
            return
        if changed_pdf:
            self.speaker_notes, self.notes_document, self.notes_path = {}, {}, None
            self.notes_dirty = False
        if not self.finish_note_editing():
            return
        self.stop_worker()
        self.stop_video()
        self.pdf, self.count = Path(pdf), count
        self.current.empty_text = ''
        self.set_document_controls(True)
        self.index, self.paths, self.videos = 0, {}, {}
        self.autoplay_page = None
        self.output.black = False
        self.black_button.setText(_t('Schwarz · B'))
        self.jump.blockSignals(True)
        self.jump.setRange(1, count)
        self.jump.setValue(1)
        self.jump.blockSignals(False)
        self.reset_timer()
        self.setWindowTitle(f'PyPDFPresenter - {self.pdf.name}')
        self.note_source.setCurrentIndex(1 if mode == 'none' or self.notes_path or self.speaker_notes else 0)
        self.update_notes_status()
        self.resolved_mode = mode
        self.worker = Renderer(self.pdf, mode, count)
        self.worker.ready.connect(self.page_ready)
        self.worker.media_ready.connect(self.media_ready)
        self.worker.failed.connect(lambda error: QMessageBox.critical(self, _t('Rendering fehlgeschlagen'), error))
        self.worker.start()
        self.go(0)

    def open_pdf(self):
        folder = str(self.pdf.parent) if self.pdf else str(Path.home())
        filename, _ = QFileDialog.getOpenFileName(self, _t('Präsentation öffnen'), folder, 'PDF (*.pdf)')
        if filename:
            self.load(Path(filename))

    def page_ready(self, index, slide, notes):
        self.paths[index] = (slide, notes)
        if index in (self.index, self.index + 1):
            self.update_images()
        if index == self.index:
            self.maybe_autoplay()

    def update_images(self):
        current = self.paths.get(self.index, ('', ''))
        self.current.set_image(current[0])
        self.notes.set_image(current[1])
        self.output.set_image(current[0])
        self.next.set_image(self.paths.get(self.index + 1, ('', ''))[0])
        self.next_notes.set_image(self.paths.get(self.index + 1, ('', ''))[1])
        self.update_note_text()

    def go(self, index):
        if not self.count:
            return
        new_index = max(0, min(index, self.count - 1))
        if new_index != self.index:
            self.stop_video()
            self.autoplay_page = None
            self.move_pointer(None)
        self.index = new_index
        self.select_video()
        self.counter.setText(_t('Seite {page} / {total}').format(page=self.index + 1, total=self.count))
        self.jump.blockSignals(True)
        self.jump.setValue(self.index + 1)
        self.jump.blockSignals(False)
        self.update_images()
        for offset in (0, 1, 2, -1):
            page = self.index + offset
            if 0 <= page < self.count and page not in self.paths:
                self.worker.request(page)
        self.maybe_autoplay()

    def show_output(self):
        if not self.count:
            return
        screens = QApplication.screens()
        screen = screens[max(0, min(self.screen.currentIndex(), len(screens) - 1))]
        self.output.showNormal()
        self.output.setGeometry(screen.geometry())
        self.output.windowHandle().setScreen(screen)
        self.output.showFullScreen()
        self.maybe_autoplay()

    def toggle_presentation(self):
        if self.output.isVisible():
            self.output.hide()
        else:
            self.show_output()

    def output_visibility_changed(self, visible):
        self.start_button.setText(_t('Präsentation stoppen · F5') if visible else _t('Präsentation starten · F5'))
        if not visible:
            self.player.pause()
            self.autoplay_page = None
            self.move_pointer(None)

    def toggle_black(self):
        self.output.black = not self.output.black
        self.black_button.setText(_t('Folie zeigen · B') if self.output.black else _t('Schwarz · B'))
        self.output.update()
        if self.output.black:
            self.player.pause()

    def media_ready(self, videos):
        self.videos = videos
        self.select_video()
        self.maybe_autoplay()

    def maybe_autoplay(self):
        # Wait for both slide and media; don't restart after a pause or reset.
        if (self.autoplay.isChecked() and self.index in self.paths and self.videos.get(self.index)
                and not self.output.black and self.autoplay_page != self.index):
            self.autoplay_page = self.index
            if self.player.playbackState() != QMediaPlayer.PlaybackState.PlayingState:
                self.toggle_video()

    def select_video(self):
        media = self.videos.get(self.index, [])
        self.video_button.setEnabled(bool(media))
        rect = media[0]['rect'] if media else None
        for view in (self.current, self.output):
            view.video_rect = rect
            view.update()
        self.video_button.setToolTip(media[0]['name'] if media else _t('Diese Seite enthält kein unterstütztes Video.'))

    def toggle_video(self):
        media = self.videos.get(self.index, [])
        if not media:
            return
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
            return
        source = QUrl.fromLocalFile(media[0]['path'])
        if self.player.source() != source:
            self.player.setSource(source)
        if self.output.black:
            self.toggle_black()
        self.player.play()

    def video_frame(self, frame):
        if self.player.source().isEmpty() or self.player.playbackState() == QMediaPlayer.PlaybackState.StoppedState:
            return
        image = frame.toImage()
        if not image.isNull():
            for view in (self.current, self.output):
                view.video_frame = image
                view.update()

    def stop_video(self):
        self.player.stop()
        self.player.setSource(QUrl())
        for view in (self.current, self.output):
            view.video_frame = QImage()
            view.update()

    def toggle_timer(self):
        if self.started is None:
            self.started = time.monotonic()
            self.timer_button.setText(_t('Timer pausieren'))
        else:
            self.elapsed += time.monotonic() - self.started
            self.started = None
            self.timer_button.setText(_t('Timer fortsetzen'))
        self.tick()

    def reset_timer(self):
        self.elapsed, self.started = 0, None
        self.timer_button.setText(_t('Timer starten'))
        self.tick()

    def tick(self):
        seconds = int(self.elapsed + (time.monotonic() - self.started if self.started is not None else 0))
        self.clock.setText(f'{seconds // 60:02d}:{seconds % 60:02d}')

    def closeEvent(self, event):
        if not self.confirm_notes_saved():
            event.ignore()
            return
        self.stop_video()
        self.stop_worker()
        self.output.hide()
        for panel in self.panels:
            if panel.parent() is None:
                panel.deleteLater()
        event.accept()


def configure_app(app, language='auto'):
    selected = select_language(language)
    app.setApplicationName('PyPDFPresenter')
    app.setApplicationVersion('0.1.0')
    app.setOrganizationName('PyPDFPresenter')
    if hasattr(app, '_qt_translator'):
        app.removeTranslator(app._qt_translator)
    if selected == 'de':
        translator = QTranslator(app)
        for directory in (SOFTWARE / 'ui-assets', Path(QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath))):
            if translator.load(str(directory / 'qtbase_de.qm')):
                app.installTranslator(translator)
                app._qt_translator = translator
                break
    # Offscreen Qt can lack access to the Windows font registry.
    font = Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts' / 'segoeui.ttf'
    if font.exists():
        font_id = QFontDatabase.addApplicationFont(str(font))
        families = QFontDatabase.applicationFontFamilies(font_id)
        if families:
            app.setFont(QFont(families[0], 10))
    app.setStyle('Fusion')
    assets = (SOFTWARE / 'ui-assets').as_posix()
    app.setStyleSheet('QWidget { background: #182130; color: #edf2fa; font-size: 14px; } '
                     'QPushButton, QComboBox, QSpinBox { background: #29364b; border: 1px solid #40516b; padding: 7px; border-radius: 4px; } '
                     'QPushButton:hover { background: #365479; } QSplitter::handle { background: #40516b; }'
                     'QPushButton:checked { background: #1778bc; border-color: #69c5ff; } '
                     'QCheckBox { spacing: 8px; } '
                     'QCheckBox::indicator { width: 20px; height: 20px; border: 2px solid #9cb4d2; border-radius: 4px; background: #26364d; } '
                     'QCheckBox::indicator:hover { border-color: #ffffff; } '
                     f'QCheckBox::indicator:checked {{ background: #1778bc; border-color: #69c5ff; image: url("{assets}/check.svg"); }} '
                     'QCheckBox::indicator:disabled { border-color: #637792; background: #263246; } '
                     'QSpinBox { padding-right: 34px; } '
                     'QSpinBox::up-button { subcontrol-origin: border; subcontrol-position: top right; width: 28px; background: #3c5474; border-left: 1px solid #9cb4d2; border-bottom: 1px solid #9cb4d2; border-top-right-radius: 4px; } '
                     'QSpinBox::down-button { subcontrol-origin: border; subcontrol-position: bottom right; width: 28px; background: #3c5474; border-left: 1px solid #9cb4d2; border-bottom-right-radius: 4px; } '
                     'QSpinBox::up-button:hover, QSpinBox::down-button:hover { background: #5277a4; } '
                     f'QSpinBox::up-arrow {{ image: url("{assets}/up.svg"); width: 12px; height: 8px; }} '
                     f'QSpinBox::down-arrow {{ image: url("{assets}/down.svg"); width: 12px; height: 8px; }} '
                     'QComboBox { padding-right: 28px; } '
                     'QComboBox::drop-down { subcontrol-origin: border; subcontrol-position: top right; width: 24px; border-left: 1px solid #7893b5; background: #344966; } '
                     f'QComboBox::down-arrow {{ image: url("{assets}/down.svg"); width: 12px; height: 8px; }} '
                     'QPushButton:disabled { color: #8193aa; background: #202c3e; border-color: #40516b; }')


def main():
    parser = argparse.ArgumentParser(description='PyPDFPresenter: offline PDF presentations with speaker notes.')
    parser.add_argument('pdf', nargs='?')
    parser.add_argument('--demo', action='store_true', help='Open the included English demo with JSON speaker notes')
    parser.add_argument('--notes', choices=['auto', 'right', 'left', 'none'], default='auto')
    parser.add_argument('--speaker-notes', metavar='JSON', help=_t('Externe Sprechtexte laden'))
    parser.add_argument('--language', choices=['auto', 'de', 'en'], default='auto', help='UI language; default follows the system locale')
    parser.add_argument('--verify', metavar='RESULT_JSON', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.demo:
        args.pdf = str(ROOT / 'examples' / 'demo.pdf')
        if not args.speaker_notes:
            args.speaker_notes = str(ROOT / 'examples' / 'demo.notes.json')
    if args.speaker_notes and not args.pdf:
        parser.error(_t('--speaker-notes benötigt eine PDF-Datei.'))
    app = QApplication(sys.argv[:1])
    configure_app(app, args.language)
    window = Presenter(Path(args.pdf) if args.pdf else None, args.notes)
    if args.pdf and not window.worker:
        return 1
    if args.speaker_notes and not window.load_notes(Path(args.speaker_notes)):
        window.close()
        return 1
    window.show()
    if args.verify:
        deadline = time.monotonic() + 60
        check = QTimer(window)
        verified_videos = set()
        active_video = [None]
        def verify():
            if not args.pdf:
                passed = window.isVisible() and window.worker is None and window.pdf is None and window.count == 0
                Path(args.verify).write_text(json.dumps({'passed': passed, 'empty_start': True}), encoding='utf-8')
                check.stop()
                window.close()
                app.exit(0 if passed else 1)
                return
            prepared = len(window.paths) == window.count
            if prepared and time.monotonic() <= deadline:
                pending = [page for page in window.videos if page not in verified_videos]
                if pending:
                    page = pending[0]
                    if active_video[0] != page:
                        window.go(page)
                        window.toggle_video()
                        active_video[0] = page
                    elif not window.output.video_frame.isNull() and window.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
                        verified_videos.add(page)
                        window.stop_video()
                    return
            if prepared or time.monotonic() > deadline:
                passed = len(window.paths) == window.count
                passed = passed and len(verified_videos) == len(window.videos)
                window.go(min(2, window.count - 1))
                passed = passed and not window.output.pixmap.isNull()
                Path(args.verify).write_text(json.dumps({'passed': passed, 'pages': window.count,
                    'prepared': len(window.paths), 'output_width': window.output.pixmap.width(),
                    'videos_decoded': len(verified_videos), 'notes_mode': window.resolved_mode,
                    'text_notes': len(window.speaker_notes), 'font_size': window.note_font.value()}), encoding='utf-8')
                check.stop()
                window.close()
                app.exit(0 if passed else 1)
        check.timeout.connect(verify)
        check.start(100)
    return app.exec()


if __name__ == '__main__':
    sys.exit(main())
