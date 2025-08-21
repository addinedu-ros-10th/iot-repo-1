#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os, sys, time, re
import mysql.connector
import cv2
import pytesseract
from ultralytics import YOLO

import serial
import serial.tools.list_ports

from PyQt6 import uic
from PyQt6.QtCore import QThread, pyqtSignal, Qt
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QDialog,
    QListWidget, QListWidgetItem,
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
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    cur.close(); conn.close()

def insert_parking_row(name: str, company: str, number: str, klass: str):
    conn = connect_db(); cur = conn.cursor()
    cur.execute(
        "INSERT INTO parking (name, company, number, class) VALUES (%s,%s,%s,%s)",
        (name, company, number, klass)
    )
    cur.close(); conn.close()

# ================== 아두이노 직렬 설정 ==================
ARDUINO_BAUD = 115200   # ← 아두이노 스케치 Serial.begin(115200)과 반드시 동일
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
            time.sleep(1.8)  # 보드 리셋 대기
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

# ---- Tesseract 경로/언어 준비 ----
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
PLATE_PATTERN = re.compile(r"\b\d{2,3}[가-힣]\d{4}\b")  # 예: 12가3456, 123가4567
DEDUP_SECONDS = 6
DETECT_LIMIT = 10

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

# ================== Detector Thread (미리보기 포함) ==================
class DetectorThread(QThread):
    plateDetected = pyqtSignal(str)     # plate 텍스트
    frameReady    = pyqtSignal(QImage)  # 미리보기 프레임
    done          = pyqtSignal()

    def __init__(self, limit=DETECT_LIMIT, parent=None):
        super().__init__(parent)
        self._running = True
        self.limit = limit
        self.last_seen = {}
        self.collected = set()
        self._last_emit_ts = 0.0  # 프리뷰 스로틀용

    def stop(self):
        self._running = False

    def run(self):
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
            while self._running:
                if len(self.collected) >= self.limit: break

                ok, frame = cap.read()
                if not ok:
                    self.plateDetected.emit("[WARN] Frame grab failed."); break

                # ---------- 미리보기 (~15fps) ----------
                now = time.time()
                if now - self._last_emit_ts >= (1/15):
                    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    h, w, ch = rgb.shape
                    qimg = QImage(rgb.data, w, h, ch*w, QImage.Format.Format_RGB888)
                    self.frameReady.emit(qimg.copy())
                    self._last_emit_ts = now

                # ---------- 탐지 & OCR ----------
                results = model.predict(source=frame, conf=CONF_THRES, iou=IOU_THRES, imgsz=IMGSZ, verbose=False)
                now2 = time.time()
                for r in results:
                    if r.boxes is None: continue
                    for b in r.boxes:
                        if not self._running or len(self.collected) >= self.limit: break
                        x1, y1, x2, y2 = b.xyxy[0].cpu().numpy().astype(int).tolist()
                        pad = int(0.06 * max(1, x2 - x1))
                        xx1 = max(0, x1 - pad); yy1 = max(0, y1 - pad)
                        xx2 = min(frame.shape[1]-1, x2 + pad); yy2 = min(frame.shape[0]-1, y2 + pad)
                        crop = frame[yy1:yy2, xx1:xx2]

                        plate = ocr_plate(crop)
                        if not plate: continue
                        last_t = self.last_seen.get(plate, 0)
                        if now2 - last_t < DEDUP_SECONDS: continue
                        self.last_seen[plate] = now2
                        if plate in self.collected: continue

                        self.collected.add(plate)
                        self.plateDetected.emit(plate)
                        if len(self.collected) >= self.limit: break
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

        # 미리보기 on/off 상태
        self.preview_enabled = True

        # 컨테이너/레이아웃
        container = self.centralWidget() if hasattr(self,"centralWidget") and self.centralWidget() else self
        layout = container.layout()
        if layout is None:
            layout = QVBoxLayout(container); container.setLayout(layout)

        # QListWidget 확보
        self.listPlates = self.findChild(QListWidget, "listPlates")
        if self.listPlates is None:
            self.listPlates = QListWidget(self)
            self.listPlates.setObjectName("listPlates")
            layout.addWidget(self.listPlates)

        # ✅ 영상 전용 아이템(0번 셀) 구성
        self._init_video_item(height=260)

        # 등록 버튼 (인식된 번호 등록)
        self.registerButton = self.findChild(QPushButton, "registerButton")
        if self.registerButton is None:
            self.registerButton = QPushButton("등록", self)
            self.registerButton.setObjectName("registerButton")
            layout.addWidget(self.registerButton)
        self.registerButton.clicked.connect(self.on_register_clicked)

        # 🔘 offButton (있으면 연결만)
        self.offButton = self.findChild(QPushButton, "offButton")
        if self.offButton:
            self.offButton.clicked.connect(self.on_off_clicked)

        # 🔓 openButton (DB 등록된 번호 선택시에만 활성화)
        self.openButton = self.findChild(QPushButton, "openButton")
        if self.openButton:
            self.openButton.setEnabled(False)
            self.openButton.clicked.connect(self.on_open_clicked)
            # 리스트에서 선택이 바뀔 때마다 DB 검사
            self.listPlates.currentTextChanged.connect(self.on_plate_selection_changed)

        # 🆕 newregisterButton (번호 직접 등록)
        self.newregisterButton = self.findChild(QPushButton, "newregisterButton")
        if self.newregisterButton:
            self.newregisterButton.clicked.connect(self.on_newregister_clicked)

        # DB 준비
        try:
            ensure_parking_table()
        except Exception as e:
            QMessageBox.critical(self, "DB 오류", f"테이블 준비 실패: {e}")

        # 아두이노 컨트롤러
        self.arduino = ArduinoController()  # 포트 자동 탐색

        # 감지 스레드 시작
        self.det = DetectorThread(limit=DETECT_LIMIT, parent=self)
        self.det.plateDetected.connect(self.on_plate_detected)
        self.det.frameReady.connect(self.on_frame_ready)    # 미리보기
        self.det.done.connect(self.on_detect_done)
        self.det.start()

        QApplication.instance().aboutToQuit.connect(self._cleanup_thread)

    def _init_video_item(self, height: int = 240):
        self.videoLabel = QLabel(self)
        self.videoLabel.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.videoLabel.setText("웹캠 미리보기")
        self.videoLabel.setMinimumHeight(height)
        self.videoLabel.setStyleSheet("background:#111; color:#ccc;")

        self.videoItem = QListWidgetItem(self.listPlates)
        self.videoItem.setFlags(Qt.ItemFlag.NoItemFlags)
        self.videoItem.setSizeHint(self.videoLabel.sizeHint())

        self.listPlates.addItem(self.videoItem)
        self.listPlates.setItemWidget(self.videoItem, self.videoLabel)

    # 미리보기 프레임 수신 → 0번 셀에 그리기
    def on_frame_ready(self, qimg: QImage):
        if not getattr(self, "preview_enabled", True):
            return
        pix = QPixmap.fromImage(qimg)
        cell_width = self.listPlates.viewport().width()
        self.videoLabel.setPixmap(pix.scaled(
            cell_width,
            self.videoLabel.height(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        ))

    # 번호 수신
    def on_plate_detected(self, plate: str):
        if plate.startswith("[ERR]") or plate.startswith("[WARN]"):
            QMessageBox.warning(self, "알림", plate); return
        self.listPlates.addItem(plate)
        # 선택이 바뀌면 on_plate_selection_changed가 DB 검사해서 버튼 상태를 갱신함

    def on_detect_done(self):
        pass

    # 등록 버튼: 스레드 정지 → (인식된 번호) 등록 다이얼로그
    def on_register_clicked(self):
        self._cleanup_thread()
        items = self.listPlates.selectedItems()
        if not items:
            QMessageBox.information(self, "안내", "먼저 리스트에서 차량번호를 선택하세요."); return
        number = items[0].text().strip()
        dlg = RegisterDialog(number=number, parent=self)
        if dlg.exec():   # 저장되었으면, 현재 선택 번호 기준으로 openButton 상태 갱신
            self.on_plate_selection_changed(number)

    # 🆕 newregisterButton: 스레드 정지 → (번호 직접 입력) 등록 다이얼로그
    def on_newregister_clicked(self):
        self._cleanup_thread()
        dlg = ManualRegisterDialog(parent=self)
        if dlg.exec():
            # 수동 등록 후에도, 만약 현재 선택된 번호가 DB에 존재하면 버튼 활성화 갱신
            cur = self.listPlates.currentItem()
            if cur:
                self.on_plate_selection_changed(cur.text())

    # 🔘 offButton: 미리보기(웹캠 화면)만 숨김
    def on_off_clicked(self):
        self.preview_enabled = False
        try:
            if hasattr(self, "videoItem") and self.videoItem is not None:
                self.videoItem.setHidden(True)
        except Exception:
            pass
        if hasattr(self, "videoLabel") and self.videoLabel is not None:
            self.videoLabel.clear()
            self.videoLabel.setText("")

    # 🔓 openButton: 등록된 차량만 OPEN 신호 전송
    def on_open_clicked(self):
        items = self.listPlates.selectedItems()
        if not items:
            QMessageBox.information(self, "안내", "차량번호를 선택하세요."); return
        number = items[0].text().strip()
        if not self.is_registered(number):
            QMessageBox.information(self, "안내", "등록된 차량이 아닙니다."); return
        if not self.arduino.send("OPEN\n"):
            QMessageBox.warning(self, "아두이노", "OPEN 명령 전송 실패")

    # 리스트 선택 변경 시: DB 검사해 openButton 활성/비활성
    def on_plate_selection_changed(self, text: str):
        if not self.openButton:
            return
        number = (text or "").strip()
        self.openButton.setEnabled(bool(number) and self.is_registered(number))

    # DB에 등록된 차량인지 확인
    def is_registered(self, number: str) -> bool:
        try:
            conn = connect_db(); cur = conn.cursor()
            cur.execute("SELECT 1 FROM parking WHERE number=%s LIMIT 1", (number,))
            exists = cur.fetchone() is not None
            cur.close(); conn.close()
            return exists
        except Exception as e:
            print("[DB ERROR]", e)
            return False

    def _cleanup_thread(self):
        if hasattr(self,"det") and self.det.isRunning():
            self.det.stop()
            self.det.wait(2000)
        if hasattr(self, "arduino") and self.arduino:
            self.arduino.close()

    def closeEvent(self, e):
        self._cleanup_thread()
        super().closeEvent(e)

# ================== 엔트리 ==================
def main():
    app = QApplication(sys.argv)
    w = MainWindow()
    w.setWindowTitle("Parking ANPR – 등록/수동등록 + DB 검증 + Arduino OPEN")
    w.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
