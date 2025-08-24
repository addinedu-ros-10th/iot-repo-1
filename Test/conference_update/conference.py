#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 회의실 키오스크 (입실 성공 후에만 '퇴실' 가능, 퇴실 시 인증번호 재확인)
# PyQt6 + uic.loadUiType + QMainWindow (사용자 선호 포맷)

import sys
from datetime import datetime
from PyQt6.QtWidgets import QApplication, QMainWindow, QMessageBox
from PyQt6.QtCore import QTimer
from PyQt6 import uic

import mysql.connector
import serial, serial.tools.list_ports

# ====== 방/연결 설정 ======
ROOM_NAME = "회의실 B"      # reservations.room_name 사용할 때
ROOM_ID   = None            # reservations.room_id 사용할 때 (예: 1)
PREFER_SERIAL_PORT = None   # 예: "/dev/ttyACM0" (None이면 자동 탐색)

DB_CFG = dict(
    host="database-1.c1kkeqig4j9x.ap-northeast-2.rds.amazonaws.com",
    port=3306,
    user="root",
    password="12345678",
    database="joeffice",
)

# ====== UI 로드 ======
from_class = uic.loadUiType("roomA_kiosk.ui")[0]

class RoomKiosk(QMainWindow, from_class):
    def __init__(self):
        super().__init__()
        self.setupUi(self)

        # 연결
        self.db  = self._connect_db()
        self.ser = self._open_serial(PREFER_SERIAL_PORT)
        self._off_timer = None

        # 현재 체크인된 예약 정보(퇴실 시 재확인/처리용)
        self.active_resv = None  # dict(id, end_time, auth_code, room_display)

        # 스키마 자동 감지
        self.schema = self._detect_schema()  # {mode, res_room_col, rooms_pk, rooms_name_col}

        # 버튼 시그널
        self.btn_enter.clicked.connect(self.verify_and_start)
        self.btn_status.clicked.connect(self.poll_hvac_status)
        self.btn_leave.clicked.connect(self.leave_now)

        # 초기상태
        self.btn_leave.setEnabled(False)  # 입실 전엔 퇴실 비활성화
        self._set_statusbar("준비 완료")
        try:
            self.le_code.setInputMask("9999;_")  # 숫자 4자리 힌트(선택)
        except Exception:
            pass

    # ===== infra =====
    def _set_statusbar(self, msg: str):
        try: self.statusbar.showMessage(msg)
        except Exception: print(msg)

    def _connect_db(self):
        try:
            conn = mysql.connector.connect(**DB_CFG)
            self._set_statusbar("DB 연결 성공")
            return conn
        except Exception as e:
            self._set_statusbar(f"DB 연결 실패: {e}")
            QMessageBox.critical(self, "오류", f"데이터베이스 연결 실패: {e}")
            return None

    def _open_serial(self, prefer=None):
        try:
            port = prefer
            if not port:
                for p in serial.tools.list_ports.comports():
                    if "ACM" in p.device or "USB" in p.device:
                        port = p.device
                        break
            if not port:
                raise RuntimeError("HVAC 포트를 찾지 못했습니다. PREFER_SERIAL_PORT를 설정하세요.")
            s = serial.Serial(port=port, baudrate=9600, timeout=1)
            self.lbl_status.setText(f"HVAC 연결: {port}")
            return s
        except Exception as e:
            self.lbl_status.setText(f"HVAC 연결 실패: {e}")
            return None

    def _send_cmd(self, line: str):
        if not self.ser:
            raise RuntimeError("HVAC 미연결 상태입니다.")
        data = (line.strip() + "\n").encode("utf-8")
        self.ser.write(data)
        # 한 줄 응답만 가볍게 확인 (없으면 무시)
        try:
            resp = self.ser.readline().decode(errors="ignore").strip()
            if resp:
                print("[HVAC RESP]", resp)
        except Exception:
            pass

    # ===== 스키마 자동 감지 =====
    def _detect_schema(self):
        if not (self.db and self.db.is_connected()):
            raise RuntimeError("DB 연결 필요")

        cur = self.db.cursor()
        cur.execute("SHOW COLUMNS FROM reservations")
        res_cols = {r[0] for r in cur.fetchall()}

        cur.execute("SHOW COLUMNS FROM rooms")
        room_cols = {r[0] for r in cur.fetchall()}

        # 1) room_name 사용
        if "room_name" in res_cols and ROOM_NAME:
            return {
                "mode": "by_name",
                "res_room_col": "room_name",
                "rooms_pk": None,
                "rooms_name_col": "room_name"
            }

        # 2) room_id 사용
        if "room_id" in res_cols and ROOM_ID is not None:
            rooms_pk = "room_id" if "room_id" in room_cols else ("id" if "id" in room_cols else None)
            if not rooms_pk:
                raise RuntimeError("rooms 테이블 PK(room_id 또는 id)가 필요합니다.")
            rooms_name_col = "room_name" if "room_name" in room_cols else ("name" if "name" in room_cols else None)
            return {
                "mode": "by_id",
                "res_room_col": "room_id",
                "rooms_pk": rooms_pk,
                "rooms_name_col": rooms_name_col
            }

        raise RuntimeError("reservations 테이블에 room_name 또는 room_id 컬럼이 필요합니다.")

    # ===== 핵심: 입실 =====
    def verify_and_start(self):
        """인증번호 확인 → CHECKED_IN → EN 1 → 종료 타이머 → 퇴실 버튼 활성화"""
        code = self.le_code.text().strip()
        if not code:
            QMessageBox.warning(self, "입력", "인증번호 4자리를 입력하세요.")
            return
        if not (self.db and self.db.is_connected()):
            QMessageBox.warning(self, "경고", "DB 연결이 필요합니다.")
            return

        now = datetime.now()
        try:
            cur = self.db.cursor(dictionary=True)

            if self.schema["mode"] == "by_name":
                cur.execute(f"""
                    SELECT
                        reservations.`id`,
                        reservations.`uid`,
                        reservations.`name`,
                        reservations.`start_time`,
                        reservations.`end_time`,
                        reservations.`reservation_status`,
                        reservations.`room_name`,
                        reservations.`auth_code`
                    FROM reservations
                    WHERE reservations.`{self.schema['res_room_col']}` = %s
                      AND reservations.`auth_code` = %s
                      AND reservations.`start_time` <= %s
                      AND reservations.`end_time` >= %s
                      AND reservations.`reservation_status` IN ('BOOKED','CHECKED_IN')
                    ORDER BY reservations.`start_time` DESC
                    LIMIT 1
                """, (ROOM_NAME, code, now, now))
                row = cur.fetchone()
                room_display = ROOM_NAME

            else:
                cur.execute(f"""
                    SELECT
                        reservations.`id`,
                        reservations.`uid`,
                        reservations.`name`,
                        reservations.`start_time`,
                        reservations.`end_time`,
                        reservations.`reservation_status`,
                        reservations.`auth_code`,
                        rooms.`{self.schema['rooms_name_col']}` AS room_display
                    FROM reservations
                    JOIN rooms ON reservations.`{self.schema['res_room_col']}` = rooms.`{self.schema['rooms_pk']}`
                    WHERE rooms.`{self.schema['rooms_pk']}` = %s
                      AND reservations.`auth_code` = %s
                      AND reservations.`start_time` <= %s
                      AND reservations.`end_time` >= %s
                      AND reservations.`reservation_status` IN ('BOOKED','CHECKED_IN')
                    ORDER BY reservations.`start_time` DESC
                    LIMIT 1
                """, (ROOM_ID, code, now, now))
                row = cur.fetchone()
                room_display = (row["room_display"] if row and row.get("room_display") else f"Room #{ROOM_ID}")

            if not row:
                QMessageBox.warning(self, "인증 실패", "번호가 틀리거나 시간대가 아닙니다.")
                return

            # 처음 입실이면 CHECKED_IN으로 전환
            if row["reservation_status"] == "BOOKED":
                cur.execute("""
                    UPDATE reservations
                    SET reservation_status='CHECKED_IN'
                    WHERE `id`=%s
                """, (row["id"],))
                self.db.commit()

            # HVAC ON
            try:
                self._send_cmd("EN 1")
            except Exception as e:
                QMessageBox.critical(self, "HVAC 오류", f"HVAC ON 실패: {e}")
                return

            # 종료 타이머 (예약 끝나면 자동 OFF)
            remain_ms = max(0, int((row["end_time"] - now).total_seconds() * 1000))
            if self._off_timer:
                self._off_timer.stop()
            self._off_timer = QTimer(self)
            self._off_timer.setSingleShot(True)
            self._off_timer.timeout.connect(lambda: self._auto_stop(row["id"]))
            self._off_timer.start(remain_ms)

            # 활성 예약 저장 (퇴실 시 재확인용)
            self.active_resv = {
                "id": row["id"],
                "end_time": row["end_time"],
                "auth_code": row.get("auth_code", code),
                "room_display": room_display
            }
            self.btn_leave.setEnabled(True)  # 입실 성공 → 퇴실 가능

            # UI
            self.lbl_msg.setText(
                f"입실 완료: {room_display}\n"
                f"종료 예정: {row['end_time'].strftime('%Y-%m-%d %H:%M')}"
            )
            self.le_code.clear()
            self._set_statusbar("입실/자동가동 처리 완료")

        except Exception as e:
            QMessageBox.critical(self, "오류", f"인증 처리 실패: {e}")

    # ===== 핵심: 조기 퇴실 =====
    def leave_now(self):
        """입실 상태에서만 활성화. 인증번호 재입력 일치 시 즉시 OFF."""
        if not self.active_resv:
            QMessageBox.information(self, "안내", "입실 상태가 아닙니다.")
            return

        code = self.le_code.text().strip()
        if not code:
            QMessageBox.warning(self, "입력", "퇴실 확인을 위해 인증번호를 다시 입력하세요.")
            return
        if code != str(self.active_resv["auth_code"]):
            QMessageBox.warning(self, "인증 실패", "인증번호가 일치하지 않습니다.")
            return

        # HVAC OFF
        try:
            self._send_cmd("EN 0")
        except Exception as e:
            self._set_statusbar(f"HVAC OFF 실패: {e}")

        # DB 상태 FINISHED
        try:
            if self.db and self.db.is_connected():
                cur = self.db.cursor()
                cur.execute("""
                    UPDATE reservations
                    SET reservation_status='FINISHED'
                    WHERE `id`=%s AND reservation_status='CHECKED_IN'
                """, (self.active_resv["id"],))
                self.db.commit()
        except Exception as e:
            self._set_statusbar(f"조기 퇴실 DB 실패: {e}")

        # 타이머 해제 + 상태 초기화
        try:
            if self._off_timer:
                self._off_timer.stop()
                self._off_timer = None
        except Exception:
            pass

        self.lbl_msg.setText("퇴실 완료. 시스템을 종료했습니다.")
        self.btn_leave.setEnabled(False)
        self.active_resv = None
        self.le_code.clear()
        self._set_statusbar("조기 퇴실 처리 완료")

    # ===== 예약 종료 자동 OFF =====
    def _auto_stop(self, reservation_id: int):
        try:
            self._send_cmd("EN 0")
        except Exception as e:
            self._set_statusbar(f"HVAC OFF 실패: {e}")

        try:
            if self.db and self.db.is_connected():
                cur = self.db.cursor()
                cur.execute("""
                    UPDATE reservations
                    SET reservation_status='FINISHED'
                    WHERE `id`=%s AND reservation_status='CHECKED_IN'
                """, (reservation_id,))
                self.db.commit()
                self._set_statusbar("예약 종료 처리 완료")
        except Exception as e:
            self._set_statusbar(f"종료 상태 갱신 실패: {e}")

        # 상태 초기화
        self.btn_leave.setEnabled(False)
        self.active_resv = None
        self.le_code.clear()
        self.lbl_msg.setText("예약이 종료되어 시스템을 종료했습니다.")

    # ===== 상태 조회 (선택) =====
    def poll_hvac_status(self):
        try:
            self._send_cmd("HR")
            try:
                raw = self.ser.readline().decode(errors="ignore").strip()
                if raw:
                    self.lbl_status.setText(raw)  # TEMP/HUM/ENABLE/STATE 라인 등
            except Exception:
                pass
        except Exception as e:
            self._set_statusbar(f"상태 조회 실패: {e}")

    # ===== 안전 종료 =====
    def closeEvent(self, ev):
        # 안전을 위해 끄고 닫기
        try:
            if self.ser:
                try: self._send_cmd("EN 0")
                except: pass
                try: self.ser.close()
                except: pass
        finally:
            try:
                if self.db and self.db.is_connected():
                    self.db.close()
            finally:
                ev.accept()

# ===== main =====
if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = RoomKiosk()
    w.show()
    sys.exit(app.exec())
