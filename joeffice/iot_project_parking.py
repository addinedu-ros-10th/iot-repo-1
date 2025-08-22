#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os, sys, time, re
import mysql.connector
import cv2
import pytesseract
from ultralytics import YOLO

import serial
import serial.tools.list_ports
import numpy as np

from PyQt6 import uic
from PyQt6.QtCore import QThread, pyqtSignal, Qt, QTimer
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QDialog,
    QListWidget, QListWidgetItem, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QHBoxLayout,
    QMessageBox, QPushButton, QLineEdit, QComboBox, QLabel
)

# ================== DB 설정 ==================
DB = dict(
    host="database-1.c1kkeqig4j9x.ap-northeast-2.rds.amazonaws.com",
    port=3306,
    user="joeffice_user",
    password="12345678",
    database="joeffice",
    autocommit=True,
)

def connect_db():
    return mysql.connector.connect(connection_timeout=5, **DB)

def ensure_parking_table():
    conn = connect_db(); cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS parking (
            id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(50) NOT NULL,
            company VARCHAR(100) NOT NULL,
            number VARCHAR(20) NOT NULL,
            class VARCHAR(50) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            INDEX(number)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    cur.close(); conn.close()

# ---- parking 스키마 보강: 컬럼/인덱스 없으면 추가 ----
def column_exists(cur, table, col):
    cur.execute("""
        SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
         WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s AND COLUMN_NAME=%s
         LIMIT 1
    """, (DB["database"], table, col))
    return cur.fetchone() is not None

def index_exists(cur, table, index_name):
    cur.execute("""
        SELECT 1 FROM INFORMATION_SCHEMA.STATISTICS
         WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s AND INDEX_NAME=%s
         LIMIT 1
    """, (DB["database"], table, index_name))
    return cur.fetchone() is not None

def ensure_parking_schema():
    conn = connect_db(); cur = conn.cursor()
    if not column_exists(cur, "parking", "last_in_time"):
        cur.execute("ALTER TABLE parking ADD COLUMN last_in_time DATETIME NULL")
    if not column_exists(cur, "parking", "last_out_time"):
        cur.execute("ALTER TABLE parking ADD COLUMN last_out_time DATETIME NULL")
    if not column_exists(cur, "parking", "is_parked"):
        cur.execute("ALTER TABLE parking ADD COLUMN is_parked TINYINT(1) NOT NULL DEFAULT 0")
    if not index_exists(cur, "parking", "idx_is_parked"):
        cur.execute("ALTER TABLE parking ADD INDEX idx_is_parked (is_parked)")
    if not index_exists(cur, "parking", "idx_last_in_time"):
        cur.execute("ALTER TABLE parking ADD INDEX idx_last_in_time (last_in_time)")
    if not index_exists(cur, "parking", "idx_last_out_time"):
        cur.execute("ALTER TABLE parking ADD INDEX idx_last_out_time (last_out_time)")
    cur.close(); conn.close()

def insert_parking_row(name: str, company: str, number: str, klass: str):
    conn = connect_db(); cur = conn.cursor()
    cur.execute(
        "INSERT INTO parking (name, company, number, class) VALUES (%s,%s,%s,%s)",
        (name, company, number, klass)
    )
    cur.close(); conn.close()

# ---- 상태 유틸 (visit 테이블 없이 운영) ----
def is_currently_parked(number: str) -> bool:
    conn = connect_db(); cur = conn.cursor()
    cur.execute("SELECT is_parked FROM parking WHERE number=%s LIMIT 1", (number,))
    row = cur.fetchone()
    cur.close(); conn.close()
    return bool(row and int(row[0]) == 1)

def mark_in(number: str):
    conn = connect_db(); cur = conn.cursor()
    cur.execute("""
        UPDATE parking
           SET last_in_time = NOW(),
               is_parked    = 1
         WHERE number=%s
         LIMIT 1
    """, (number,))
    cur.close(); conn.close()

def mark_out(number: str):
    conn = connect_db(); cur = conn.cursor()
    cur.execute("""
        UPDATE parking
           SET last_out_time = NOW(),
               is_parked     = 0
         WHERE number=%s
         LIMIT 1
    """, (number,))
    cur.close(); conn.close()

def get_current_count() -> int:
    conn = connect_db(); cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM parking WHERE is_parked=1")
    cnt = cur.fetchone()[0]
    cur.close(); conn.close()
    return int(cnt)

def fetch_current_parked_rows():
    """현재 주차 중인 차량 목록 (name, company, number, class, last_in_time, last_out_time)"""
    conn = connect_db(); cur = conn.cursor()
    cur.execute("""
        SELECT name, company, number, class,
               COALESCE(DATE_FORMAT(last_in_time,  '%Y-%m-%d %H:%i:%s'), ''),
               COALESCE(DATE_FORMAT(last_out_time, '%Y-%m-%d %H:%i:%s'), '')
          FROM parking
         WHERE is_parked=1
         ORDER BY last_in_time DESC
    """)
    rows = cur.fetchall()
    cur.close(); conn.close()
    return rows

def fetch_parking_manage_rows():
    conn = connect_db(); cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT
            name, company, number, class, is_parked,
            last_in_time, last_out_time,
            CASE
              WHEN is_parked=1 AND last_in_time IS NOT NULL
                THEN TIMESTAMPDIFF(MINUTE, last_in_time, NOW())
              WHEN is_parked=0 AND last_in_time IS NOT NULL AND last_out_time IS NOT NULL
                THEN TIMESTAMPDIFF(MINUTE, last_in_time, last_out_time)
              ELSE NULL
            END AS minutes_used
        FROM parking
        ORDER BY COALESCE(last_in_time, created_at) DESC, id DESC
    """)
    rows = cur.fetchall()
    cur.close(); conn.close()
    return rows

def format_minutes_hms(total_minutes: int | None) -> str:
    if total_minutes is None:
        return ""
    if total_minutes < 0:
        total_minutes = 0
    days = total_minutes // 1440
    rem  = total_minutes % 1440
    hours = rem // 60
    mins  = rem % 60
    if days > 0:
        return f"{days}일 {hours}시간 {mins}분"
    return f"{hours}시간 {mins}분"

# ================== 아두이노 직렬 설정 ==================
ARDUINO_BAUD = 9600
SERIAL_TIMEOUT = 1.0

class ArduinoController:
    def __init__(self, port_hint: str | None = None, baud: int = ARDUINO_BAUD):
        self.port_name = port_hint
        self.baud = baud
        self.ser = None
        self.connect()

    def _auto_detect_port(self) -> str | None:
        for p in serial.tools.list_ports.comports():
            if ('ACM' in p.device) or ('USB' in p.device) or ('COM' in p.device):
                return p.device
        return None

    def connect(self):
        self.close()
        port = self.port_name
        try:
            if not port or (not port.upper().startswith('COM') and not os.path.exists(port)):
                cand = self._auto_detect_port()
                if cand:
                    port = cand
            self.ser = serial.Serial(port, self.baud, timeout=SERIAL_TIMEOUT)
            self.port_name = port
            time.sleep(1.8)
            print(f"[SERIAL] Connected to {port} @ {self.baud}")
        except Exception as e:
            self.ser = None
            print(f"[SERIAL] Connect fail: {e}")

    def is_open(self) -> bool:
        return self.ser is not None and self.ser.is_open

    def send(self, line: str) -> bool:
        if not self.is_open():
            self.connect()
        if not self.is_open():
            print("[SERIAL] Not connected.")
            return False
        try:
            if not line.endswith("\n"):
                line += "\n"
            self.ser.write(line.encode("utf-8"))
            return True
        except Exception as e:
            print(f"[SERIAL] Send fail: {e}")
            try:
                self.ser.close()
            except: pass
            self.ser = None
            return False

    def close(self):
        try:
            if self.ser is not None:
                self.ser.close()
        except: pass
        self.ser = None

# ================== YOLO / OCR 설정 ==================
WEIGHTS_PATH = "/home/addinedu/dev_ws/qt_venv/weights/lp_detector.pt"
CAM_INDEX = 0
CONF_THRES = 0.25
IOU_THRES = 0.5
IMGSZ = 640

TESSERACT_BIN = "/usr/bin/tesseract"
if os.path.exists(TESSERACT_BIN):
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_BIN
else:
    print(f"[WARN] Tesseract not found at {TESSERACT_BIN}. Adjust path if needed.")

def resolve_tess_lang() -> str:
    try:
        langs = set(pytesseract.get_languages(config=""))
    except Exception as e:
        print(f"[WARN] get_languages failed: {e} -> fallback to 'eng'")
        return "eng"
    if "kor" in langs and "eng" in langs: return "kor+eng"
    if "kor" in langs: return "kor"
    return "eng"

TESS_LANG = resolve_tess_lang()
print(f"[INFO] OCR language set to: {TESS_LANG}")

WHITELIST = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ가나다라마바사아자차카타파하허호무부거너더러머버서어저고노도로모보소오조우배국합육공하허호음임"
PLATE_PATTERN = re.compile(r"\b\d{2,3}[가-힣]\d{4}\b")
DEDUP_SECONDS = 6  # 같은 번호 연속 중복 방지 시간(초)

# ================== OCR 유틸 ==================
def preprocess_for_ocr(crop_bgr):
    if crop_bgr is None or crop_bgr.size == 0: return None
    gray = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2GRAY)
    scale = 3.0 if max(crop_bgr.shape[:2]) < 200 else 2.0
    resized = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    _, th = cv2.threshold(resized, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    th = cv2.morphologyEx(th, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (2,2)), 1)
    return th

def normalize_text(s:str)->str:
    return re.sub(r"[^0-9A-Z가-힣]", "", s.strip().upper())

def validate_plate(text:str)->str|None:
    m = PLATE_PATTERN.search(text) if text else None
    return m.group(0) if m else None

def ocr_plate(crop_bgr)->str:
    img = preprocess_for_ocr(crop_bgr)
    if img is None: return ""
    config = (f'--oem 1 --psm 7 --dpi 300 '
              f'-c tessedit_char_whitelist={WHITELIST} '
              f'-c preserve_interword_spaces=1')
    try:
        raw = pytesseract.image_to_string(img, lang=TESS_LANG, config=config)
    except Exception as e:
        print(f"[OCR] {e}")
        return ""
    clean = normalize_text(raw)
    valid = validate_plate(clean)
    return valid or ""

# ================== Detector Thread (라벨 미리보기 + 무한 감지) ==================
class DetectorThread(QThread):
    plateDetected = pyqtSignal(str)
    frameReady    = pyqtSignal(QImage)
    done          = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._running = True
        self.last_seen = {}   # plate -> last timestamp
        self._last_emit_ts = 0.0

    def stop(self):
        # 안전 종료: 루프 플래그 + 인터럽트 + 조인
        self._running = False
        self.requestInterruption()
        try:
            self.wait(1500)
        except Exception:
            pass

    def run(self):
        if self.isInterruptionRequested():
            return
        if not os.path.exists(WEIGHTS_PATH):
            self.plateDetected.emit(f"[ERR] weights not found: {WEIGHTS_PATH}")
            self.done.emit(); return
        try:
            model = YOLO(WEIGHTS_PATH)
        except Exception as e:
            self.plateDetected.emit(f"[ERR] YOLO load fail: {e}")
            self.done.emit(); return

        cap = cv2.VideoCapture(CAM_INDEX)
        if not cap.isOpened():
            self.plateDetected.emit("[ERR] Cannot open webcam")
            self.done.emit(); return

        try:
            while self._running and not self.isInterruptionRequested():
                ok, frame = cap.read()
                if not ok:
                    break

                # ---- 미리보기 (≈15fps) ----
                now = time.time()
                if now - self._last_emit_ts >= (1/15):
                    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    h, w, ch = rgb.shape
                    qimg = QImage(rgb.data, w, h, ch*w, QImage.Format.Format_RGB888)
                    self.frameReady.emit(qimg.copy())
                    self._last_emit_ts = now

                # ---- 탐지 & OCR ----
                results = model.predict(source=frame, conf=CONF_THRES, iou=IOU_THRES, imgsz=IMGSZ, verbose=False)
                t2 = time.time()
                for r in results:
                    if r.boxes is None: continue
                    for b in r.boxes:
                        if not self._running or self.isInterruptionRequested(): break
                        x1, y1, x2, y2 = b.xyxy[0].cpu().numpy().astype(int).tolist()
                        pad = int(0.06 * max(1, x2 - x1))
                        xx1 = max(0, x1 - pad); yy1 = max(0, y1 - pad)
                        xx2 = min(frame.shape[1]-1, x2 + pad); yy2 = min(frame.shape[0]-1, y2 + pad)
                        crop = frame[yy1:yy2, xx1:xx2]

                        plate = ocr_plate(crop)
                        if not plate: continue
                        if t2 - self.last_seen.get(plate, 0) < DEDUP_SECONDS:
                            continue
                        self.last_seen[plate] = t2
                        self.plateDetected.emit(plate)
        finally:
            cap.release()
        self.done.emit()

# ================== 등록 다이얼로그 (인식된 번호용) ==================
class RegisterDialog(QDialog):
    def __init__(self, number: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("차량 등록")
        self.number = number

        v = QVBoxLayout(self)
        v.addWidget(QLabel(f"차량번호: {number}", self))
        self.nameEdit = QLineEdit(self); self.nameEdit.setPlaceholderText("이름")
        self.companyEdit = QLineEdit(self); self.companyEdit.setPlaceholderText("소속회사")
        v.addWidget(self.nameEdit); v.addWidget(self.companyEdit)

        row = QHBoxLayout()
        row.addWidget(QLabel("구분:", self))
        self.classCombo = QComboBox(self); self.classCombo.addItems(["내부인","외부인"])
        row.addWidget(self.classCombo); v.addLayout(row)

        btnRow = QHBoxLayout()
        btnSave = QPushButton("저장", self); btnCancel = QPushButton("취소", self)
        btnRow.addWidget(btnSave); btnRow.addWidget(btnCancel); v.addLayout(btnRow)
        btnSave.clicked.connect(self.on_save); btnCancel.clicked.connect(self.reject)

    def on_save(self):
        name = self.nameEdit.text().strip()
        company = self.companyEdit.text().strip()
        klass = self.classCombo.currentText().strip()
        if not name: QMessageBox.information(self,"안내","이름을 입력하세요."); return
        if not company: QMessageBox.information(self,"안내","소속회사를 입력하세요."); return
        try:
            insert_parking_row(name, company, self.number, klass)
        except Exception as e:
            QMessageBox.critical(self, "DB 오류", f"저장 실패: {e}"); return
        QMessageBox.information(self, "완료",
                                f"[저장]\n이름: {name}\n회사: {company}\n번호: {self.number}\n구분: {klass}")
        self.accept()

# ================== 등록 다이얼로그 (번호 직접 입력용) ==================
class ManualRegisterDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("수동 차량 등록")

        v = QVBoxLayout(self)
        self.numberEdit = QLineEdit(self); self.numberEdit.setPlaceholderText("차량번호 (예: 123가4567)")
        v.addWidget(self.numberEdit)

        self.nameEdit = QLineEdit(self); self.nameEdit.setPlaceholderText("이름")
        self.companyEdit = QLineEdit(self); self.companyEdit.setPlaceholderText("소속회사")
        v.addWidget(self.nameEdit); v.addWidget(self.companyEdit)

        row = QHBoxLayout()
        row.addWidget(QLabel("구분:", self))
        self.classCombo = QComboBox(self); self.classCombo.addItems(["내부인","외부인"])
        row.addWidget(self.classCombo); v.addLayout(row)

        btnRow = QHBoxLayout()
        btnSave = QPushButton("저장", self); btnCancel = QPushButton("취소", self)
        btnRow.addWidget(btnSave); btnRow.addWidget(btnCancel); v.addLayout(btnRow)
        btnSave.clicked.connect(self.on_save); btnCancel.clicked.connect(self.reject)

    def on_save(self):
        number_raw = self.numberEdit.text()
        number_norm = normalize_text(number_raw)
        valid = validate_plate(number_norm)
        if not valid:
            QMessageBox.information(self, "안내", "차량번호 형식이 올바르지 않습니다. 예) 123가4567")
            return

        name = self.nameEdit.text().strip()
        company = self.companyEdit.text().strip()
        klass = self.classCombo.currentText().strip()
        if not name: QMessageBox.information(self,"안내","이름을 입력하세요."); return
        if not company: QMessageBox.information(self,"안내","소속회사를 입력하세요."); return

        try:
            insert_parking_row(name, company, valid, klass)
        except Exception as e:
            QMessageBox.critical(self, "DB 오류", f"저장 실패: {e}"); return

        QMessageBox.information(self, "완료",
                                f"[저장]\n이름: {name}\n회사: {company}\n번호: {valid}\n구분: {klass}")
        self.accept()

# ================== UI (ui 베이스 자동 반영) ==================
UiClass, BaseClass = uic.loadUiType("iot_project_parking.ui")

class MainWindow(BaseClass, UiClass):
    def __init__(self):
        super().__init__()
        self.setupUi(self)

        # 상태
        self.preview_enabled = True
        self.min_auto_open_gap = 3.0
        self._last_auto_open_ts_by_plate = {}
        self.last_detected_plate = None

        # 영상 라벨
        self.videoLabel = self.findChild(QLabel, "videoLabel")
        if self.videoLabel is None:
            raise RuntimeError("ui에 QLabel 'videoLabel'이 없습니다.")
        self.videoLabel.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.videoLabel.setMinimumHeight(260)
        self.videoLabel.setStyleSheet("background:#111; color:#ccc;")

        # 실시간 주차대수 라벨(label_2)
        self.parkingCountLabel = self.findChild(QLabel, "label_2")
        if self.parkingCountLabel is None:
            raise RuntimeError("ui에 QLabel 'label_2'이 없습니다.")
        self.parkingCountLabel.setText("실시간 주차정보: 0대")

        # 현재 주차 목록 tableWidget
        self.tableWidget = self.findChild(QTableWidget, "tableWidget")
        if self.tableWidget is None:
            raise RuntimeError("ui에 QTableWidget 'tableWidget'이 없습니다.")
        headers = ["name", "company", "number", "class", "last_in_time", "last_out_time"]
        self.tableWidget.setColumnCount(len(headers))
        self.tableWidget.setHorizontalHeaderLabels(headers)
        self.tableWidget.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tableWidget.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tableWidget.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.tableWidget.horizontalHeader().setStretchLastSection(True)

        # 로그 리스트
        self.listPlates = self.findChild(QListWidget, "listPlates")
        if self.listPlates is None:
            container = self.centralWidget() if hasattr(self,"centralWidget") and self.centralWidget() else self
            layout = container.layout()
            if layout is None:
                layout = QVBoxLayout(container); container.setLayout(layout)
            self.listPlates = QListWidget(self); self.listPlates.setObjectName("listPlates")
            layout.addWidget(self.listPlates)

        # 버튼
        self.registerButton = self.findChild(QPushButton, "registerButton")
        if self.registerButton:
            self.registerButton.clicked.connect(self.on_register_clicked)

        self.offButton = self.findChild(QPushButton, "offButton")
        if self.offButton:
            self.offButton.clicked.connect(self.on_off_clicked)

        self.openButton = self.findChild(QPushButton, "openButton")
        if self.openButton:
            self.openButton.setEnabled(False)
            self.openButton.clicked.connect(self.on_open_clicked)
            self.listPlates.currentTextChanged.connect(self.on_plate_selection_changed)

        self.newregisterButton = self.findChild(QPushButton, "newregisterButton")
        if self.newregisterButton:
            self.newregisterButton.clicked.connect(self.on_newregister_clicked)

        # 관리(토글) 버튼과 관리 테이블
        self.manageButton = self.findChild(QPushButton, "manageButton")
        self.tableWidget2 = self.findChild(QTableWidget, "tableWidget_2")
        if self.manageButton is None or self.tableWidget2 is None:
            raise RuntimeError("ui에 manageButton 또는 tableWidget_2가 없습니다.")
        self.manageButton.clicked.connect(self.on_manage_clicked)
        headers2 = ["name", "company", "number", "class",
                    "상태", "마지막 입차", "마지막 출차",
                    "이번 주차시간", "이번 주차일수"]
        self.tableWidget2.setColumnCount(len(headers2))
        self.tableWidget2.setHorizontalHeaderLabels(headers2)
        self.tableWidget2.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tableWidget2.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tableWidget2.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.tableWidget2.horizontalHeader().setStretchLastSection(True)
        self.tableWidget2.setVisible(False)   # 기본 숨김

        # DB 준비
        try:
            ensure_parking_table()
            ensure_parking_schema()
        except Exception as e:
            QMessageBox.critical(self, "DB 오류", f"테이블 준비 실패: {e}")

        # 아두이노
        self.arduino = ArduinoController()

        # 감지 스레드: 지연 시작(탭 임베드 환경에서 안전)
        self.det = None
        QTimer.singleShot(0, self.start_detector)

        # 앱 종료/탭 닫기 대비 안전 종료
        QApplication.instance().aboutToQuit.connect(self.stop_detector)

        # 실시간 갱신 타이머
        self.refresh_timer = QTimer(self)
        self.refresh_timer.setInterval(1000)
        self.refresh_timer.timeout.connect(self.refresh_parking_summary)
        self.refresh_timer.start()
        self.refresh_parking_summary()

    # ===== 스레드 수명 관리 =====
    def start_detector(self):
        if self.det and self.det.isRunning():
            return
        self.det = DetectorThread(parent=self)
        self.det.plateDetected.connect(self.on_plate_detected)
        self.det.frameReady.connect(self.on_frame_ready)
        self.det.done.connect(self.on_detect_done)
        self.det.start()

    def stop_detector(self):
        try:
            if self.det:
                try:
                    self.det.plateDetected.disconnect()
                    self.det.frameReady.disconnect()
                    self.det.done.disconnect()
                except Exception:
                    pass
                self.det.stop()
                self.det.wait(1500)
        except Exception:
            pass
        finally:
            self.det = None

    # ===== 프리뷰 표시 =====
    def on_frame_ready(self, qimg: QImage):
        if not self.preview_enabled or self.videoLabel is None:
            return
        pix = QPixmap.fromImage(qimg)
        self.videoLabel.setPixmap(
            pix.scaled(
                self.videoLabel.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
        )

    # ===== 감지 이벤트 =====
    def on_plate_detected(self, plate: str):
        if plate.startswith("[ERR]") or plate.startswith("[WARN]"):
            QMessageBox.warning(self, "알림", plate); return

        self.last_detected_plate = plate

        self.listPlates.addItem(plate)
        self.listPlates.setCurrentRow(self.listPlates.count()-1)

        # 등록 차량이면 자동 OPEN + IN/OUT 토글
        if self.is_registered(plate):
            if self.openButton:
                self.openButton.setEnabled(True)
            self._auto_open_and_toggle(plate)
        else:
            if self.openButton:
                self.openButton.setEnabled(False)

    def _auto_open_and_toggle(self, number: str):
        self.on_plate_selection_changed(number)

        now = time.time()
        last = self._last_auto_open_ts_by_plate.get(number, 0.0)
        if now - last < self.min_auto_open_gap:
            return
        ok = self.arduino.send("OPEN\n")
        self._last_auto_open_ts_by_plate[number] = now
        if not ok:
            QMessageBox.warning(self, "아두이노", f"OPEN 명령 전송 실패 ({number})")

        try:
            if is_currently_parked(number):
                mark_out(number)
                self.listPlates.addItem(f"[OUT] {number}")
            else:
                mark_in(number)
                self.listPlates.addItem(f"[IN ] {number}")
        except Exception as e:
            QMessageBox.critical(self, "DB 오류", f"상태 갱신 실패: {e}")

        self.refresh_parking_summary()

    def on_detect_done(self):
        pass

    # ===== 등록/수동 등록 =====
    def on_register_clicked(self):
        items = self.listPlates.selectedItems()
        if not items:
            QMessageBox.information(self, "안내", "먼저 리스트에서 차량번호를 선택하세요."); return
        number = items[0].text().strip()
        dlg = RegisterDialog(number=number, parent=self)
        if dlg.exec():
            self.on_plate_selection_changed(number)

    def on_newregister_clicked(self):
        dlg = ManualRegisterDialog(parent=self)
        if dlg.exec():
            cur = self.listPlates.currentItem()
            if cur:
                self.on_plate_selection_changed(cur.text())

    # ===== 수동 OPEN =====
    def on_open_clicked(self):
        number = None
        items = self.listPlates.selectedItems()
        if items:
            number = (items[0].text() or "").strip()
        if not number and self.last_detected_plate:
            number = self.last_detected_plate

        if not number:
            QMessageBox.information(self, "안내", "선택된 차량이 없고 최근 감지 기록도 없습니다.")
            return
        if not self.is_registered(number):
            QMessageBox.information(self, "안내", f"{number} : 등록된 차량이 아닙니다.")
            return

        if self.arduino.send("OPEN\n"):
            try:
                if is_currently_parked(number):
                    mark_out(number)
                    self.listPlates.addItem(f"[OUT] {number} (manual)")
                else:
                    mark_in(number)
                    self.listPlates.addItem(f"[IN ] {number} (manual)")
            except Exception as e:
                QMessageBox.critical(self, "DB 오류", f"상태 갱신 실패: {e}")
            self.refresh_parking_summary()
        else:
            QMessageBox.warning(self, "아두이노", "OPEN 명령 전송 실패")

    # ===== 관리 화면 (토글) =====
    def on_manage_clicked(self):
        if self.tableWidget2.isVisible():
            self.tableWidget2.setVisible(False)
            return

        try:
            rows = fetch_parking_manage_rows()
        except Exception as e:
            QMessageBox.critical(self, "DB 오류", f"관리 데이터 조회 실패: {e}")
            return

        self.tableWidget2.setRowCount(len(rows))
        for i, r in enumerate(rows):
            name = r.get("name","")
            company = r.get("company","")
            number = r.get("number","")
            klass = r.get("class","")
            is_parked = int(r.get("is_parked") or 0)
            status_txt = "주차중" if is_parked == 1 else "미주차"

            last_in  = r.get("last_in_time")
            last_out = r.get("last_out_time")
            last_in_str  = last_in.strftime("%Y-%m-%d %H:%M:%S") if last_in else ""
            last_out_str = last_out.strftime("%Y-%m-%d %H:%M:%S") if last_out else ""

            minutes = r.get("minutes_used")
            dur_str = format_minutes_hms(minutes)
            days_str = f"{(minutes // 1440)}일" if minutes is not None else ""

            values = [name, company, number, klass,
                      status_txt, last_in_str, last_out_str,
                      dur_str, days_str]
            for j, val in enumerate(values):
                self.tableWidget2.setItem(i, j, QTableWidgetItem(str(val)))

        self.tableWidget2.setVisible(True)

    # ===== 기타 UI =====
    def on_off_clicked(self):
        self.preview_enabled = not self.preview_enabled
        if self.videoLabel:
            self.videoLabel.setVisible(self.preview_enabled)

    def on_plate_selection_changed(self, text: str):
        if not self.openButton:
            return
        number = (text or "").strip()
        self.openButton.setEnabled(bool(number) and self.is_registered(number))

    # ===== DB 조회 유틸 =====
    def is_registered(self, number: str) -> bool:
        try:
            conn = connect_db(); cur = conn.cursor()
            cur.execute("SELECT 1 FROM parking WHERE number=%s LIMIT 1", (number,))
            exists = cur.fetchone() is not None
            cur.close(); conn.close()
            return exists
        except Exception as e:
            print("[DB ERROR] is_registered:", e)
            return False

    # ===== 실시간 요약 갱신 (label_2 + tableWidget) =====
    def refresh_parking_summary(self):
        try:
            cnt = get_current_count()
            self.parkingCountLabel.setText(f"실시간 주차정보: {cnt}대")
        except Exception:
            self.parkingCountLabel.setText("실시간 주차정보: -")

        try:
            rows = fetch_current_parked_rows()
            self.tableWidget.setRowCount(len(rows))
            for i, row in enumerate(rows):
                for j, val in enumerate(row):
                    self.tableWidget.setItem(i, j, QTableWidgetItem(str(val)))
        except Exception:
            self.tableWidget.setRowCount(0)

    # ===== 종료 정리 =====
    def closeEvent(self, e):
        self.stop_detector()
        if hasattr(self, "arduino") and self.arduino:
            self.arduino.close()
        super().closeEvent(e)

# ================== 엔트리 ==================
def main():
    app = QApplication(sys.argv)
    w = MainWindow()
    w.setWindowTitle("Parking ANPR – 실시간 프리뷰/대수/목록 + 자동/수동 OPEN + 관리뷰(토글)")
    w.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
