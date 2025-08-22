# users_test -> users로 table 변경 한 것

#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
from PyQt6.QtWidgets import *
from PyQt6.QtCore import *
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6 import uic
import serial
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo
import csv
import os

# --- MySQL 커넥터 로드 ---
try:
    import mysql.connector
except ImportError:
    print("[ERROR] mysql-connector-python 미설치. 다음 명령으로 설치하세요:")
    print("   pip install mysql-connector-python")
    sys.exit(1)

from_class = uic.loadUiType("iot_project_access.ui")[0]


# ==========================
#  RFID 수신 스레드
# ==========================
class Receiver(QThread):
    detected = pyqtSignal(bytes)  # 4바이트 UID

    def __init__(self, conn, parent=None):
        super().__init__(parent)
        self.conn = conn
        self.is_running = False

    def run(self):
        if self.conn is None:
            return
        print("recv start")
        self.is_running = True
        try:
            self.conn.reset_input_buffer()
        except Exception as e:
            print("[SERIAL][WARN] reset_input_buffer:", e)

        while self.is_running:
            try:
                line = self.conn.read_until(b"\n")
            except Exception as e:
                print("[SERIAL][ERROR] read_until:", e)
                continue

            if not line:
                continue
            try:
                msg = line.decode("utf-8", errors="ignore").strip()
            except Exception:
                continue

            # 기대 포맷: "UID a20df603"
            if msg.startswith("UID "):
                uid_hex = msg[4:].strip().lower()
                if len(uid_hex) == 8:
                    self.detected.emit(bytes.fromhex(uid_hex))
                else:
                    print("[WARN] invalid UID:", msg)

    def stop(self):
        self.is_running = False
        print("recv stop")

# 냉난방 시스템 =======================
class HvacReader(QThread):
    line_rx = pyqtSignal(str)
    def __init__(self, ser, parent=None):
        super().__init__(parent)
        self.ser = ser
        self._run = False
    def run(self):
        if not self.ser:
            return
        self._run = True
        buf = b""
        try:
            self.ser.reset_input_buffer()
        except Exception:
            pass
        while self._run and self.ser and self.ser.is_open:
            try:
                chunk = self.ser.read(64)
                if not chunk:
                    continue
                buf += chunk
                while b"\n" in buf or b"\r" in buf:
                    for sep in (b"\r\n", b"\n", b"\r"):
                        if sep in buf:
                            line, buf = buf.split(sep, 1)
                            s = line.decode("utf-8", errors="ignore").strip()
                            if s:
                                self.line_rx.emit(s)
                            break
                    else:
                        break
            except Exception:
                break
    def stop(self):
        self._run = False
# 냉난방 시스템 =============================


# ==========================
#  메인 다이얼로그
# ==========================
class MyDialog(QDialog, from_class):
    def __init__(self):
        super().__init__()
        self.setupUi(self)
        self.conn = None  # RFID 포트 초기화
        self.hvac_conn = None # HVAC 포트 초기화
        self.hvac_recv = None # HVAC 수신 스레드

# 냉난방 시스템 ===============================
        self._hvac_enabled_cache = None  # 마지막으로 보낸 enable 값(변화 있을 때만 전송)
        self._auto_hvac = True          # 자동 전송 on/off (필요시 False로 바꾸면 수동만)
# 냉난방 시스템 =====================================

        # 설정: 중복 태깅 쿨다운(초)
        self.cooldown_secs = 10

        # 시리얼 연결(오프라인 모드 허용)
        self.conn = self.try_open_serial()
        if self.conn:
            self.recv = Receiver(self.conn)
            self.recv.detected.connect(self.detected)
            self.recv.start()
            self.uidLabel.setText("카드 대주세요")
        else:
            self.recv = None
            self.uidLabel.setText("오프라인 모드: 카드 대주세요 (RFID 미연결)")

# 냉난방 시스템 =============================================
        # RFID 포트는 self.conn으로 이미 열려 있음
        self.hvac_conn = self.try_open_hvac_serial(exclude=self.conn.port if self.conn else None)
        if self.hvac_conn:
            print(f"[SERIAL] HVAC connected: {self.hvac_conn.port}")
        else:
            print("[SERIAL] HVAC not connected (off-line mode)")
# 냉난방 시스템 ========================================================


        # DB/유저 로드
        self.init_db()
        self.load_users()  # users → self.users 캐시

        # UI 초기화
        self.current_uid_hex = None
        self.registerButton.setDisabled(True)
        self.registerButton.clicked.connect(self.register_user)
        self.tableWidget.setVisible(False)
        self.managementButton.clicked.connect(self.toggle_management_view)

        # 테이블 준비 & 초기 로드
        self._updating_table = False  # 편집 이벤트 루프 방지 플래그
        self.setup_table()
        self.tableWidget.itemChanged.connect(self.on_item_changed)

        # 오늘 출근자 테이블/라벨
        self.setup_present_table()
        self.refresh_all_views()

        # 실시간 갱신 타이머 (15초)
        self.headcount_timer = QTimer(self)
        self.headcount_timer.setInterval(15000)
        self.headcount_timer.timeout.connect(self.refresh_headcount)
        self.headcount_timer.timeout.connect(self.refresh_present_table)
        self.headcount_timer.start()

        # 단축키
        QShortcut(QKeySequence("Delete"), self, activated=self.delete_selected_rows)
        QShortcut(QKeySequence("F5"), self, activated=self.reconnect_serial)

# ======================== 냉난방 시스템 여기 추가함 ===============================
        # === HVAC 제어 상태/단축키 ===
        # self._hvac_enabled_cache = None  # 마지막으로 보낸 enable 값(변화 있을 때만 전송)
        # self._auto_hvac = True          # 자동 전송 on/off (필요시 False로 바꾸면 수동만)

        # 수동 단축키: Ctrl+1=HE 1, Ctrl+0=HE 0, Ctrl+R=HR
        QShortcut(QKeySequence("Ctrl+1"), self, activated=lambda: self.send_he(True))
        QShortcut(QKeySequence("Ctrl+0"), self, activated=lambda: self.send_he(False))
        # QShortcut(QKeySequence("Ctrl+R"), self, activated=self.send_hr)


        # (옵션) 주기 상태 폴링: 10초마다 HR
        # self._hr_timer = QTimer(self)
        # self._hr_timer.setInterval(10000)
        # self._hr_timer.timeout.connect(self.send_hr)
        # self._hr_timer.start()

        # --------- HVAC 직렬 명령 ----------
    # def _serial_send_line(self, text: str):
    #     """줄 단위 전송(CRLF)"""
    #     if not (self.conn and getattr(self.conn, "is_open", False)):
    #         print("[SERIAL] not connected; skip:", text)
    #         return
    #     try:
    #         self.conn.write((text + "\r\n").encode("utf-8"))
    #         print("[TX]", text)
    #     except Exception as e:
    #         print("[SERIAL][ERROR] write:", e)

    def _serial_send_line(self, text: str):
        """HVAC 포트가 있으면 그쪽으로, 없으면 기존 RFID conn으로 보냄"""
        ser = None
        if hasattr(self, "hvac_conn") and self.hvac_conn and getattr(self.hvac_conn, "is_open", False):
            ser = self.hvac_conn
        elif self.conn and getattr(self.conn, "is_open", False):
            ser = self.conn
        else:
            print("[SERIAL] not connected; skip:", text)
            return
        try:
            ser.write((text + "\r\n").encode("utf-8"))
            print(f"[TX] {text} -> {ser.port}")
        except Exception as e:
            print("[SERIAL][ERROR] write:", e)


    def send_he(self, enable: bool):
        self._serial_send_line(f"HE {'1' if enable else '0'}")
        self._hvac_enabled_cache = enable  # 수동 보낸 경우 캐시 갱신

    # def send_hr(self):
    #     self._serial_send_line("HR")

    def try_open_hvac_serial(self, exclude=None, baudrate=9600):
        """RFID 포트(exclude)를 제외한 다른 ttyACM/ttyUSB를 찾아 HVAC용으로 연다."""
        try:
            import serial.tools.list_ports as lp
            ports = [p.device for p in lp.comports()]
            # 우선순위 간단: exclude 제외 + ttyACM/ttyUSB
            for dev in ports:
                if exclude and dev == exclude:
                    continue
                if "ttyACM" in dev or "ttyUSB" in dev:
                    try:
                        s = serial.Serial(port=dev, baudrate=baudrate, timeout=1)
                        return s
                    except Exception:
                        continue
            return None
        except Exception as e:
            print("[SERIAL][HVAC] scan failed:", e)
            return None
        
    # -------- HVAC 직렬 명령 --------
    def _serial_send_line(self, text: str):
        """HVAC 포트가 있으면 그쪽으로, 없으면 기존 RFID conn으로 보냄"""
        ser = None
        if hasattr(self, "hvac_conn") and self.hvac_conn and getattr(self.hvac_conn, "is_open", False):
            ser = self.hvac_conn
        elif self.conn and getattr(self.conn, "is_open", False):
            ser = self.conn
        else:
            print("[SERIAL] not connected; skip:", text)
            return
        try:
            ser.write((text + "\r\n").encode("utf-8"))
            print("[TX]", text, "->", ser.port)
        except Exception as e:
            print("[SERIAL][ERROR] write:", e)

    def send_he(self, enable: bool):
        self._serial_send_line(f"HE {'1' if enable else '0'}")
        self._hvac_enabled_cache = enable  # 캐시 갱신(자동 제어에서 사용)

    def send_hr(self):
        self._serial_send_line("HR")



# ============================================================



    # ---------------- 시리얼 도우미 ----------------
    def try_open_serial(self, port="/dev/ttyACM0", baudrate=9600):
        try:
            return serial.Serial(port=port, baudrate=baudrate, timeout=1)
        except Exception as e:
            print(f"[SERIAL] 포트 열기 실패: {e} -> 오프라인 모드로 계속 진행")
            return None

    def reconnect_serial(self):
        """F5: 미연결 시 재연결 시도"""
        if self.conn and getattr(self.conn, "is_open", False):
            QMessageBox.information(self, "시리얼", "이미 연결되어 있습니다.")
            return
        self.conn = self.try_open_serial()
        if self.conn:
            if self.recv is None:
                self.recv = Receiver(self.conn)
                self.recv.detected.connect(self.detected)
            self.recv.conn = self.conn
            self.recv.start()
            self.uidLabel.setText("카드 대주세요 (연결됨)")
            QMessageBox.information(self, "시리얼", "연결 성공")
        else:
            QMessageBox.warning(self, "시리얼", "연결 실패 (오프라인 모드 유지)")

    # ---------------- 공통 유틸 ----------------
    def _td_to_hms(self, val) -> str:
        """mysql TIME -> timedelta/time/str -> 'HH:MM:SS'"""
        if val is None:
            return ""
        try:
            if isinstance(val, timedelta):
                total = int(val.total_seconds())
                sign = "-" if total < 0 else ""
                total = abs(total)
                h = total // 3600
                m = (total % 3600) // 60
                s = total % 60
                return f"{sign}{h:02d}:{m:02d}:{s:02d}"
            elif isinstance(val, datetime.time):
                return val.strftime("%H:%M:%S")
        except Exception:
            pass
        return str(val)

    def _today_kst(self) -> str:
        return datetime.now(ZoneInfo("Asia/Seoul")).date().isoformat()

    def _is_valid_date(self, s: str) -> bool:
        try:
            datetime.strptime(s, "%Y-%m-%d")
            return True
        except Exception:
            return False

    def _normalize_time(self, s: str):
        s = s.strip()
        for fmt in ("%H:%M:%S", "%H:%M"):
            try:
                t = datetime.strptime(s, fmt).time()
                return t.strftime("%H:%M:%S")
            except Exception:
                continue
        return None

    def _combine_date_time(self, date_str: str, time_str: str) -> datetime:
        dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M:%S")
        return dt.replace(tzinfo=None)

    def _canonical_action(self, action: str) -> str:
        if action in ("IN", "FIRST_IN"):
            return "IN"
        if action in ("OUT", "LAST_OUT"):
            return "OUT"
        return action

    # ---------------- MySQL 초기화 ----------------
    def init_db(self):
        self.db = mysql.connector.connect(
            host="database-1.c1kkeqig4j9x.ap-northeast-2.rds.amazonaws.com",
            port=3306,
            user="joeffice_user",
            password="12345678",
            database="joeffice",
            autocommit=True,
        )
        cur = self.db.cursor()
        # 출퇴근 로그 테이블
        cur.execute("""
            CREATE TABLE IF NOT EXISTS access_log (
                id BIGINT AUTO_INCREMENT PRIMARY KEY,
                uid VARCHAR(16) NOT NULL,
                name VARCHAR(100),
                company VARCHAR(100),
                ts DATETIME NOT NULL,
                action ENUM('IN','OUT','FIRST_IN','LAST_OUT') NOT NULL,
                INDEX idx_uid_date (uid, ts)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
        # 사용자 마스터
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                uid VARCHAR(16) PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                company VARCHAR(100) NOT NULL,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
        cur.close()

    # ---------------- 사용자 로드 ----------------
    def load_users(self):
        self.users = {}
        self.users_csv_path = os.path.join(os.path.dirname(__file__), "users.csv")

        try:
            cur = self.db.cursor()
            cur.execute("SELECT uid, name, company FROM users")
            for uid, name, company in cur.fetchall():
                if uid:
                    self.users[uid.strip().lower()] = (name or "", company or "")
            cur.close()
        except Exception as e:
            print("[WARN] users 로드 실패:", e)

        # (선택) CSV → DB 백필
        if not self.users and os.path.exists(self.users_csv_path):
            print("[INFO] users 비어있음 → users.csv에서 로드 후 DB 반영")
            import_rows = []
            with open(self.users_csv_path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    uid = (row.get("uid_hex") or "").strip().lower()
                    name = (row.get("name") or "").strip()
                    company = (row.get("company") or "").strip()
                    if uid:
                        self.users[uid] = (name, company)
                        import_rows.append((uid, name, company))
            if import_rows:
                cur = self.db.cursor()
                cur.executemany(
                    "INSERT INTO users(uid, name, company) VALUES (%s, %s, %s) "
                    "ON DUPLICATE KEY UPDATE name=VALUES(name), company=VALUES(company)",
                    import_rows
                )
                cur.close()

    # ---------------- 출퇴근 기록 ----------------
    def _is_duplicate_action(self, uid: str, action: str, now_ts: datetime) -> bool:
        """같은 계열(IN/FIRST_IN, OUT/LAST_OUT) 연속 태깅 쿨다운"""
        cur = self.db.cursor()
        cur.execute("SELECT ts, action FROM access_log WHERE uid=%s ORDER BY id DESC LIMIT 1", (uid,))
        row = cur.fetchone()
        cur.close()
        if not row:
            return False
        last_ts, last_action = row
        if self._canonical_action(last_action) != self._canonical_action(action):
            return False
        delta = (now_ts - last_ts).total_seconds()
        return (0 <= delta < self.cooldown_secs)

    def infer_next_action(self, uid_hex: str) -> str:
        today = date.today().isoformat()
        cur = self.db.cursor()
        cur.execute(
            """
            SELECT action
              FROM access_log
             WHERE uid=%s AND DATE(ts)=%s
             ORDER BY id DESC
             LIMIT 1
            """,
            (uid_hex, today)
        )
        row = cur.fetchone()
        cur.close()
        last = self._canonical_action(row[0]) if row else None
        return "OUT" if last == "IN" else "IN"

    def _normalize_day_flags(self, date_str: str):
        """해당 날짜: FIRST_IN, LAST_OUT 각각 1건만 유지되도록 정규화"""
        cur = self.db.cursor()
        # 초기화
        cur.execute("UPDATE access_log SET action='IN'  WHERE DATE(ts)=%s AND action='FIRST_IN'", (date_str,))
        cur.execute("UPDATE access_log SET action='OUT' WHERE DATE(ts)=%s AND action='LAST_OUT'", (date_str,))

        # 가장 이른 IN 1건 → FIRST_IN
        cur.execute(
            """
            SELECT id FROM access_log
            WHERE DATE(ts)=%s AND action IN ('IN','FIRST_IN')
            ORDER BY ts ASC
            LIMIT 1
            """,
            (date_str,)
        )
        row = cur.fetchone()
        if row:
            cur.execute("UPDATE access_log SET action='FIRST_IN' WHERE id=%s", (row[0],))

        # 가장 늦은 OUT 1건 → LAST_OUT
        cur.execute(
            """
            SELECT id FROM access_log
            WHERE DATE(ts)=%s AND action IN ('OUT','LAST_OUT')
            ORDER BY ts DESC
            LIMIT 1
            """,
            (date_str,)
        )
        row = cur.fetchone()
        if row:
            cur.execute("UPDATE access_log SET action='LAST_OUT' WHERE id=%s", (row[0],))
        cur.close()

    def record_event(self, uid_hex: str):
        name, company = self.users.get(uid_hex, ("Unknown", "Unknown"))
        action = self.infer_next_action(uid_hex)
        now_ts = datetime.now(ZoneInfo("Asia/Seoul")).replace(tzinfo=None)
        today = now_ts.date().isoformat()

        # 중복 방지
        if self._is_duplicate_action(uid_hex, action, now_ts):
            print(f"[SKIP] duplicate {action} for {uid_hex}")
            return

        # --- 현재 인원(이벤트 전) 계산
        present_before = self._present_count(today)

        # 1) 기본은 그대로 INSERT (일단 IN/OUT로 넣고, 나중에 플래그 업데이트)
        cur = self.db.cursor()
        cur.execute(
            "INSERT INTO access_log (uid, name, company, ts, action) VALUES (%s, %s, %s, %s, %s)",
            (uid_hex, name, company, now_ts, action)
        )
        inserted_id = cur.lastrowid
        cur.close()

        # 2) 플래그 결정(이벤트 드리븐)
        #   - IN 직전 인원이 0이었다면 -> 오늘의 첫 출근이므로 이번 이벤트를 FIRST_IN으로 지정
        #   - OUT 직후 인원이 0이라면 -> 오늘의 마지막 퇴근이므로 이번 이벤트를 LAST_OUT으로 지정
        #   - 그 외에는 모두 평범한 IN/OUT 유지
        if action in ("IN", "FIRST_IN"):
            if present_before == 0:
                # 오늘의 첫 출근 확정: 이번 이벤트를 FIRST_IN으로 바꿈
                cur = self.db.cursor()
                # 혹시 기존 FIRST_IN이 찍혀있으면 IN으로 되돌림(수정/삭제로 꼬인 날 대비)
                cur.execute(
                    "UPDATE access_log SET action='IN' WHERE DATE(ts)=%s AND action='FIRST_IN'",
                    (today,)
                )
                cur.execute("UPDATE access_log SET action='FIRST_IN' WHERE id=%s", (inserted_id,))
                cur.close()
            else:
                # 첫 출근이 아님 → 그냥 IN 유지
                pass

            # 누군가 출근했다면 그 날에 남아있는 LAST_OUT은 무효. (근무가 재개된 상태이므로)
            self._clear_last_out_flag_for_day(today)

        else:  # OUT or LAST_OUT(추론상 OUT일 것)
            # 삽입 후 인원 계산(= present_after)
            present_after = self._present_count(today)

            if present_after == 0:
                # 오늘 마지막 퇴근 확정: 기존 LAST_OUT 지우고 이번 이벤트를 LAST_OUT으로
                self._clear_last_out_flag_for_day(today)
                cur = self.db.cursor()
                cur.execute("UPDATE access_log SET action='LAST_OUT' WHERE id=%s", (inserted_id,))
                cur.close()
            else:
                # 아직 사람이 남아있음 → 이번 것은 OUT 유지, 그리고 혹시 남아있는 LAST_OUT이 있었다면 OUT으로 되돌려서 '가짜 마지막' 방지
                self._clear_last_out_flag_for_day(today)

        print(f"[ATTEND] {now_ts} {uid_hex} {name} {company} -> {action}")
        self.uidLabel.setText(f"{uid_hex}")
        self.refresh_all_views()

        # 냉난방 시스템 추가 부분 =====================
        pc = self._present_count(today)
        self._maybe_send_hvac_by_occupancy(pc)
        # ==========================================


    # ---------------- 신규 사용자 등록 ----------------
    def register_user(self):
        if not self.current_uid_hex:
            QMessageBox.information(self, "등록", "등록할 UID가 없습니다. 먼저 카드를 태그하세요.")
            return
        uid_hex = self.current_uid_hex

        if uid_hex in self.users:
            QMessageBox.information(self, "등록", "이미 등록된 UID입니다.")
            self.registerButton.setDisabled(True)
            return

        name, ok1 = QInputDialog.getText(self, "이름 입력", "이름:")
        if not ok1 or not name.strip():
            return
        company, ok2 = QInputDialog.getText(self, "회사 입력", "회사:")
        if not ok2 or not company.strip():
            return

        try:
            cur = self.db.cursor()
            cur.execute(
                "INSERT INTO users (uid, name, company) VALUES (%s, %s, %s) "
                "ON DUPLICATE KEY UPDATE name=VALUES(name), company=VALUES(company)",
                (uid_hex, name.strip(), company.strip())
            )
            cur.close()
        except Exception as e:
            QMessageBox.critical(self, "오류", f"DB users 저장 실패:\n{e}")
            return

        self.users[uid_hex] = (name.strip(), company.strip())

        try:
            cur = self.db.cursor()
            cur.execute(
                """
                UPDATE access_log
                   SET name=%s, company=%s
                 WHERE uid=%s
                   AND (name IS NULL OR name='' OR name='Unknown'
                    OR  company IS NULL OR company='' OR company='Unknown')
                """,
                (name.strip(), company.strip(), uid_hex)
            )
            cur.close()
        except Exception as e:
            print("[WARN] past events update failed:", e)

        # CSV 백업(선택)
        try:
            new_file = not os.path.exists(self.users_csv_path)
            with open(self.users_csv_path, "a", encoding="utf-8", newline="") as f:
                writer = csv.writer(f)
                if new_file:
                    writer.writerow(["uid_hex", "name", "company"])
                writer.writerow([uid_hex, name.strip(), company.strip()])
        except Exception as e:
            print("[WARN] users.csv 저장 실패:", e)

        QMessageBox.information(self, "등록 완료", f"{uid_hex}\n{name} / {company} 등록되었습니다.")
        self.registerButton.setDisabled(True)
        self.refresh_all_views()

    # ---------------- 카드 감지 콜백 ----------------
    def detected(self, uid_bytes: bytes):
        uid_hex = uid_bytes.hex()
        print("detected:", uid_hex)
        self.current_uid_hex = uid_hex

        if uid_hex not in self.users:
            self.registerButton.setDisabled(False)
            self.uidLabel.setText(f"{uid_hex} (미등록) / 태그됨")
        else:
            self.registerButton.setDisabled(True)

        self.record_event(uid_hex)

    # ---------------- 테이블 구성/조회/갱신 ----------------
    def setup_table(self):
        tw = self.tableWidget
        tw.setColumnCount(6)
        tw.setHorizontalHeaderLabels(["UID", "이름", "회사", "날짜", "출근시간", "퇴근시간"])
        header = tw.horizontalHeader()
        header.setStretchLastSection(True)
        tw.verticalHeader().setVisible(False)
        try:
            tw.setEditTriggers(QAbstractItemView.EditTrigger.AllEditTriggers)
            tw.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
            tw.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        except AttributeError:
            tw.setEditTriggers(QAbstractItemView.AllEditTriggers)
            tw.setSelectionBehavior(QAbstractItemView.SelectRows)
            tw.setSelectionMode(QAbstractItemView.ExtendedSelection)
        tw.setAlternatingRowColors(True)
        tw.setSortingEnabled(True)

    def fetch_daily_spans(self):
        """
        (uid, 날짜)별 첫 IN/마지막 OUT 집계 + 해당 날짜의 전사 FIRST_IN/ LAST_OUT 주인 여부
        """
        cur = self.db.cursor()
        cur.execute(
            """
            SELECT
                al.uid,
                COALESCE(NULLIF(u.name,''), NULLIF(al.name,''), 'Unknown')      AS name,
                COALESCE(NULLIF(u.company,''), NULLIF(al.company,''), 'Unknown') AS company,
                DATE(al.ts) AS d,
                TIME(MIN(CASE WHEN al.action IN ('IN','FIRST_IN')  THEN al.ts END)) AS first_in,
                TIME(MAX(CASE WHEN al.action IN ('OUT','LAST_OUT') THEN al.ts END)) AS last_out,
                CASE WHEN al.uid = df.first_uid THEN 1 ELSE 0 END AS is_first_in_owner,
                CASE WHEN al.uid = dl.last_uid  THEN 1 ELSE 0 END AS is_last_out_owner
            FROM access_log al
            LEFT JOIN users u ON u.uid = al.uid
            LEFT JOIN (
                SELECT DATE(ts) AS d, uid AS first_uid
                FROM access_log
                WHERE action='FIRST_IN'
            ) df ON df.d = DATE(al.ts)
            LEFT JOIN (
                SELECT DATE(ts) AS d, uid AS last_uid
                FROM access_log
                WHERE action='LAST_OUT'
            ) dl ON dl.d = DATE(al.ts)
            GROUP BY al.uid, DATE(al.ts), df.first_uid, dl.last_uid, u.name, u.company
            ORDER BY d DESC, name ASC
            """
        )
        rows = cur.fetchall()
        cur.close()
        return rows

    def refresh_table(self):
        rows = self.fetch_daily_spans()
        tw = self.tableWidget

        self._updating_table = True
        tw.setRowCount(len(rows))

        STAR = " ★"

        for r, (uid, name, company, d, first_in, last_out, is_first_owner, is_last_owner) in enumerate(rows):
            fi = self._td_to_hms(first_in)
            lo = self._td_to_hms(last_out)
            fi_disp = f"{fi}{STAR}" if fi and is_first_owner else fi
            lo_disp = f"{lo}{STAR}" if lo and is_last_owner else lo

            values = [
                uid or "",
                name or "",
                company or "",
                str(d) if d else "",
                fi_disp,
                lo_disp,
            ]

            for c, val in enumerate(values):
                it = QTableWidgetItem(val)
                it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                # 메타 저장: uid, 날짜, 원래값(표시 텍스트)
                it.setData(Qt.ItemDataRole.UserRole, uid or "")
                it.setData(Qt.ItemDataRole.UserRole + 1, str(d) if d else "")
                it.setData(Qt.ItemDataRole.UserRole + 2, val)

                # UID(0)만 편집 불가
                if c == 0:
                    it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)
                else:
                    it.setFlags(it.flags() | Qt.ItemFlag.ItemIsEditable)
                tw.setItem(r, c, it)

        tw.resizeColumnsToContents()
        self._updating_table = False

    # ---------------- 편집 반영 로직 ----------------
    def on_item_changed(self, item: QTableWidgetItem):
        if self._updating_table:
            return

        row = item.row()
        col = item.column()
        new_text = (item.text() or "").strip()

        uid = item.data(Qt.ItemDataRole.UserRole) or ""
        old_date = item.data(Qt.ItemDataRole.UserRole + 1) or ""  # 이 행의 원래 날짜
        old_val = item.data(Qt.ItemDataRole.UserRole + 2) or ""

        if col == 0:
            return  # UID는 편집 불가

        try:
            if col == 1:  # 이름
                self._update_user_name(uid, new_text)
            elif col == 2:  # 회사
                self._update_user_company(uid, new_text)
            elif col == 3:  # 날짜
                if not self._is_valid_date(new_text):
                    raise ValueError("날짜는 YYYY-MM-DD 형식이어야 합니다.")
                self._update_date_for_boundaries(uid, old_date, new_text)
                self._normalize_day_flags(new_text)      # 정규화
                if old_date:
                    self._normalize_day_flags(old_date)  # 원래 날짜도 정규화
                item.setData(Qt.ItemDataRole.UserRole + 1, new_text)

            elif col == 4:  # 출근시간 (첫 IN)
                date_text = self.tableWidget.item(row, 3).text().strip()
                if not self._is_valid_date(date_text):
                    raise ValueError("날짜 셀 값이 유효하지 않습니다(YYYY-MM-DD).")
                if new_text == "":
                    self._clear_first_in(uid, date_text)
                else:
                    t = self._normalize_time(new_text)
                    if t is None:
                        raise ValueError("시간은 HH:MM 또는 HH:MM:SS 형식이어야 합니다.")
                    self._update_first_in_time(uid, date_text, t)
                self._normalize_day_flags(date_text)

            elif col == 5:  # 퇴근시간 (마지막 OUT)
                date_text = self.tableWidget.item(row, 3).text().strip()
                if not self._is_valid_date(date_text):
                    raise ValueError("날짜 셀 값이 유효하지 않습니다(YYYY-MM-DD).")
                if new_text == "":
                    self._clear_last_out(uid, date_text)
                else:
                    t = self._normalize_time(new_text)
                    if t is None:
                        raise ValueError("시간은 HH:MM 또는 HH:MM:SS 형식이어야 합니다.")
                    self._update_last_out_time(uid, date_text, t)
                self._normalize_day_flags(date_text)

            else:
                return

        except Exception as e:
            QMessageBox.warning(self, "입력 오류", str(e))
            self._updating_table = True
            item.setText(old_val)
            self._updating_table = False
            return

        self.refresh_all_views()

    # ======== 행 삭제(선택 행의 UID/날짜 전체 삭제) ========
    def delete_selected_rows(self):
        tw = self.tableWidget
        sel_rows = sorted(set(idx.row() for idx in tw.selectedIndexes()))
        if not sel_rows:
            QMessageBox.information(self, "삭제", "삭제할 행을 선택하세요.")
            return

        targets = []
        for r in sel_rows:
            uid_item = tw.item(r, 0)
            date_item = tw.item(r, 3)
            if not uid_item or not date_item:
                continue
            uid = uid_item.text().strip()
            d = date_item.text().strip()
            if uid and d:
                targets.append((uid, d))

        if not targets:
            QMessageBox.information(self, "삭제", "유효한 UID/날짜가 없습니다.")
            return

        msg = "\n".join(f"{u} / {d}" for u, d in targets)
        resp = QMessageBox.question(
            self,
            "행 삭제",
            f"아래 {len(targets)}개 UID/날짜의 모든 기록(IN/OUT)을 삭제할까요?\n\n{msg}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if resp != QMessageBox.StandardButton.Yes:
            return

        cur = self.db.cursor()
        touched_days = set()
        for uid, d in targets:
            cur.execute("DELETE FROM access_log WHERE uid=%s AND DATE(ts)=%s", (uid, d))
            touched_days.add(d)
        cur.close()

        # 삭제 후 날짜별 정규화
        for d in touched_days:
            self._normalize_day_flags(d)

        self.refresh_all_views()
        QMessageBox.information(self, "삭제 완료", f"{len(targets)}개 날짜의 기록을 삭제했습니다.")

    # ======== DB 업데이트 헬퍼 ========
    def _update_user_name(self, uid: str, new_name: str):
        cur = self.db.cursor()
        cur.execute("UPDATE users SET name=%s WHERE uid=%s", (new_name, uid))
        if cur.rowcount == 0:
            _, cur_company = self.users.get(uid, ("Unknown", "Unknown"))
            cur.execute(
                "INSERT INTO users (uid, name, company) VALUES (%s, %s, %s)",
                (uid, new_name, cur_company or "Unknown")
            )
        cur.close()
        old_company = self.users.get(uid, ("Unknown", "Unknown"))[1]
        self.users[uid] = (new_name, old_company)
        try:
            cur2 = self.db.cursor()
            cur2.execute(
                """
                UPDATE access_log
                   SET name=%s
                 WHERE uid=%s
                   AND (name IS NULL OR name='' OR name='Unknown')
                """,
                (new_name, uid)
            )
            cur2.close()
        except Exception as e:
            print("[WARN] access_log name backfill failed:", e)

    def _update_user_company(self, uid: str, new_company: str):
        cur = self.db.cursor()
        cur.execute("UPDATE users SET company=%s WHERE uid=%s", (new_company, uid))
        if cur.rowcount == 0:
            cur_name, _ = self.users.get(uid, ("Unknown", "Unknown"))
            cur.execute(
                "INSERT INTO users (uid, name, company) VALUES (%s, %s, %s)",
                (uid, cur_name or "Unknown", new_company)
            )
        cur.close()
        old_name = self.users.get(uid, ("Unknown", "Unknown"))[0]
        self.users[uid] = (old_name, new_company)
        try:
            cur2 = self.db.cursor()
            cur2.execute(
                """
                UPDATE access_log
                   SET company=%s
                 WHERE uid=%s
                   AND (company IS NULL OR company='' OR company='Unknown')
                """,
                (new_company, uid)
            )
            cur2.close()
        except Exception as e:
            print("[WARN] access_log company backfill failed:", e)

    def _get_boundary_event(self, uid: str, date_str: str, action: str, earliest: bool):
        cur = self.db.cursor()
        order = "ASC" if earliest else "DESC"
        cur.execute(
            f"""
            SELECT id, ts
              FROM access_log
             WHERE uid=%s AND DATE(ts)=%s AND action IN (%s, %s)
             ORDER BY ts {order}
             LIMIT 1
            """,
            (uid, date_str, action, 'FIRST_IN' if action == 'IN' else 'LAST_OUT')
        )
        row = cur.fetchone()
        cur.close()
        if not row:
            return None
        return row[0], row[1]

    def _update_event_dt(self, event_id: int, new_dt: datetime):
        cur = self.db.cursor()
        cur.execute("UPDATE access_log SET ts=%s WHERE id=%s", (new_dt, event_id))
        cur.close()

    def _insert_event(self, uid: str, action: str, dt: datetime):
        name, company = self.users.get(uid, ("Unknown", "Unknown"))
        cur = self.db.cursor()
        cur.execute(
            "INSERT INTO access_log (uid, name, company, ts, action) VALUES (%s, %s, %s, %s, %s)",
            (uid, name, company, dt, action)
        )
        cur.close()

    def _update_date_for_boundaries(self, uid: str, old_date: str, new_date: str):
        if not old_date:
            return
        min_in = self._get_boundary_event(uid, old_date, action='IN', earliest=True)
        max_out = self._get_boundary_event(uid, old_date, action='OUT', earliest=False)

        if min_in:
            eid, ts = min_in
            new_dt = self._combine_date_time(new_date, ts.strftime("%H:%M:%S"))
            self._update_event_dt(eid, new_dt)

        if max_out:
            eid, ts = max_out
            new_dt = self._combine_date_time(new_date, ts.strftime("%H:%M:%S"))
            self._update_event_dt(eid, new_dt)

    def _update_first_in_time(self, uid: str, date_str: str, time_str: str):
        row = self._get_boundary_event(uid, date_str, action='IN', earliest=True)
        new_dt = self._combine_date_time(date_str, time_str)
        if row:
            eid, _ts = row
            self._update_event_dt(eid, new_dt)
        else:
            self._insert_event(uid, 'IN', new_dt)

    def _update_last_out_time(self, uid: str, date_str: str, time_str: str):
        row = self._get_boundary_event(uid, date_str, action='OUT', earliest=False)
        new_dt = self._combine_date_time(date_str, time_str)
        if row:
            eid, _ts = row
            self._update_event_dt(eid, new_dt)
        else:
            self._insert_event(uid, 'OUT', new_dt)

    def _clear_action_on_date(self, uid: str, date_str: str, action: str):
        cur = self.db.cursor()
        if action == 'IN':
            cur.execute("DELETE FROM access_log WHERE uid=%s AND DATE(ts)=%s AND action IN ('IN','FIRST_IN')",
                        (uid, date_str))
        else:
            cur.execute("DELETE FROM access_log WHERE uid=%s AND DATE(ts)=%s AND action IN ('OUT','LAST_OUT')",
                        (uid, date_str))
        cur.close()

    def _clear_first_in(self, uid: str, date_str: str):
        self._clear_action_on_date(uid, date_str, 'IN')

    def _clear_last_out(self, uid: str, date_str: str):
        self._clear_action_on_date(uid, date_str, 'OUT')

    # ---------------- 실시간 인원/오늘 출근자 ----------------
    def setup_present_table(self):
        tw2 = self.tableWidget_2
        tw2.setColumnCount(5)
        tw2.setHorizontalHeaderLabels(["UID", "이름", "회사", "날짜", "출근시간"])
        tw2.horizontalHeader().setStretchLastSection(True)
        tw2.verticalHeader().setVisible(False)
        try:
            tw2.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
            tw2.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
            tw2.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        except AttributeError:
            tw2.setEditTriggers(QAbstractItemView.NoEditTriggers)
            tw2.setSelectionBehavior(QAbstractItemView.SelectRows)
            tw2.setSelectionMode(QAbstractItemView.SingleSelection)
        tw2.setAlternatingRowColors(True)
        tw2.setSortingEnabled(True)

    def refresh_headcount(self):
        """
        label_2: 오늘(uid별) 마지막 이벤트가 IN/FIRST_IN 인 사람 수
        """
        today = self._today_kst()
        cur = self.db.cursor()
        cur.execute(
            """
            SELECT COUNT(*) FROM (
                SELECT al.uid
                FROM access_log al
                JOIN (
                        SELECT uid, MAX(ts) AS max_ts
                        FROM access_log
                        WHERE DATE(ts)=%s
                        GROUP BY uid
                ) m ON m.uid=al.uid AND m.max_ts=al.ts
                WHERE DATE(al.ts)=%s AND al.action IN ('IN','FIRST_IN')
                GROUP BY al.uid
            ) AS present
            """,
            (today, today)
        )
        row = cur.fetchone()
        cur.close()
        n = row[0] if row else 0
        try:
            self.label_2.setText(f"실시간 근무 인원: {n}명")
        except Exception:
            pass

# 냉난방 시스템 추가 부분 ============================
        self._maybe_send_hvac_by_occupancy(n)  # 인원 변화에 따라 HE 자동 전송

    def _maybe_send_hvac_by_occupancy(self, present_count: int):
        """
        present_count > 0이면 HE 1, ==0이면 HE 0.
        마지막으로 보낸 값과 달라질 때만 전송.
        """
        if not self._auto_hvac:
            return
        want_enable = (present_count > 0)
        if self._hvac_enabled_cache is None or self._hvac_enabled_cache != want_enable:
            self.send_he(want_enable)  # 내부에서 캐시 갱신됨
            print(f"[HVAC] auto {'ENABLE' if want_enable else 'DISABLE'} (present={present_count})")
# =======================================

    def fetch_today_attendees(self):
        """오늘 최초 IN(FIRST_IN 포함) 시간"""
        today = self._today_kst()
        cur = self.db.cursor()
        cur.execute(
            """
            SELECT
                al.uid,
                COALESCE(NULLIF(u.name,''), 'Unknown')    AS name,
                COALESCE(NULLIF(u.company,''), 'Unknown') AS company,
                DATE(al.ts)                               AS d,
                TIME(MIN(al.ts))                          AS first_in
            FROM access_log al
            LEFT JOIN users u ON u.uid = al.uid
            WHERE DATE(al.ts)=%s AND al.action IN ('IN','FIRST_IN')
            GROUP BY al.uid, DATE(al.ts), u.name, u.company
            ORDER BY first_in ASC
            """,
            (today,)
        )
        rows = cur.fetchall()
        cur.close()
        return rows
    
    def _present_count(self, date_str: str) -> int:
        """
        date_str(YYYY-MM-DD) 기준, uid별 '마지막 이벤트'가 IN/FIRST_IN인 사람 수를 리턴
        """
        cur = self.db.cursor()
        cur.execute(
            """
            SELECT COUNT(*) FROM (
                SELECT al.uid
                FROM access_log al
                JOIN (
                        SELECT uid, MAX(ts) AS max_ts
                        FROM access_log
                        WHERE DATE(ts)=%s
                        GROUP BY uid
                ) m ON m.uid=al.uid AND m.max_ts=al.ts
                WHERE DATE(al.ts)=%s AND al.action IN ('IN','FIRST_IN')
                GROUP BY al.uid
            ) AS present
            """,
            (date_str, date_str)
        )
        row = cur.fetchone()
        cur.close()
        return int(row[0] if row else 0)
    
    def _clear_last_out_flag_for_day(self, date_str: str):
        cur = self.db.cursor()
        cur.execute(
            "UPDATE access_log SET action='OUT' WHERE DATE(ts)=%s AND action='LAST_OUT'",
            (date_str,)
        )
        cur.close()

    def refresh_present_table(self):
        rows = self.fetch_today_attendees()
        tw2 = self.tableWidget_2
        tw2.setRowCount(len(rows))
        for r, (uid, name, company, d, first_in) in enumerate(rows):
            vals = [uid or "", name or "", company or "", str(d) if d else "", self._td_to_hms(first_in)]
            for c, v in enumerate(vals):
                it = QTableWidgetItem(v)
                it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                tw2.setItem(r, c, it)
        tw2.resizeColumnsToContents()

    def refresh_all_views(self):
        self.refresh_table()
        self.refresh_present_table()
        self.refresh_headcount()

    # ---------------- 종료 정리 ----------------
    def closeEvent(self, event):
        try:
            if self.recv is not None:
                self.recv.stop()
                self.recv.wait(1000)
        except Exception:
            pass
        try:
            if self.conn and getattr(self.conn, "is_open", False):
                self.conn.close()
        except Exception:
            pass
        try:
            if hasattr(self, "db") and self.db.is_connected():
                self.db.close()

        except Exception:
            pass
        event.accept()

    # ---------------- 관리 버튼 ----------------
    def toggle_management_view(self):
        want_show = not self.tableWidget.isVisible()
        self.tableWidget.setVisible(want_show)
        if want_show:
            self.refresh_all_views()
        try:
            self.managementButton.setText("닫기" if want_show else "관리")
        except Exception:
            pass


if __name__ == "__main__":
    app = QApplication(sys.argv)
    dlg = MyDialog()
    dlg.show()
    sys.exit(app.exec())
