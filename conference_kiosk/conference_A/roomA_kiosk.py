#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 회의실 A의 인증번호 확인 PyQt 코드입니다

import sys
from datetime import datetime
from PyQt6.QtWidgets import QApplication, QMainWindow, QMessageBox
from PyQt6.QtCore import QTimer
from PyQt6 import uic

import mysql.connector
import serial, serial.tools.list_ports

# ====== 설정 (방마다 달라질 값) ======
ROOM_NAME = "회의실 B"      # ← 방 이름으로 필터 (reservations.room_name 있을 때 사용)
ROOM_ID   = None            # ← 방 ID로 필터 (reservations.room_id 있을 때 사용). 예: 1
PREFER_SERIAL_PORT = None   # 예: "/dev/ttyACM0" (None이면 자동 탐색)

DB_CFG = dict(
    host="database-1.c1kkeqig4j9x.ap-northeast-2.rds.amazonaws.com",
    port=3306,
    user="root",
    password="12345678",
    database="joeffice",
)

# ====== PyQt 메인 윈도우 ======
from_class = uic.loadUiType("roomA_kiosk.ui")[0]

class RoomKiosk(QMainWindow, from_class):
    def __init__(self):
        super().__init__()
        self.setupUi(self)

        self.db = self._connect_db()
        self.ser = self._open_serial(PREFER_SERIAL_PORT)
        self._off_timer = None

        # 스키마 자동 감지
        self.schema = self._detect_schema()  # dict: {mode, res_room_col, rooms_pk, rooms_name_col}

        # 버튼 연결
        self.btn_enter.clicked.connect(self.verify_and_start)
        self.btn_status.clicked.connect(self.poll_hvac_status)

        # 시작 상태표시
        self._set_statusbar("준비 완료")
        try:
            self.le_code.setInputMask("9999;_")  # 숫자 4자리 힌트
        except Exception:
            pass

    # ---------- infra ----------
    def _set_statusbar(self, msg: str):
        try:
            self.statusbar.showMessage(msg)
        except Exception:
            print(msg)

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
        # 간단히 한 줄 응답 읽기(없으면 넘어감)
        try:
            resp = self.ser.readline().decode(errors="ignore").strip()
            if resp:
                print("[HVAC RESP]", resp)
        except Exception:
            pass

    # ---------- 스키마 자동 감지 ----------
    def _detect_schema(self):
        """
        reservations/rooms 실제 컬럼을 확인해 필터 방법을 정한다.
        반환 예:
        {
          "mode": "by_name",            # or "by_id"
          "res_room_col": "room_name",  # or "room_id"
          "rooms_pk": "room_id" or "id" (by_id일 때만 사용)
          "rooms_name_col": "room_name"/"name"/None  (라벨 표시용)
        }
        """
        if not (self.db and self.db.is_connected()):
            raise RuntimeError("DB 연결 필요")

        cur = self.db.cursor()
        cur.execute("SHOW COLUMNS FROM reservations")
        res_cols = {r[0] for r in cur.fetchall()}

        cur.execute("SHOW COLUMNS FROM rooms")
        room_cols = {r[0] for r in cur.fetchall()}

        # 1) reservations.room_name 있으면 이름으로 필터 (JOIN 불필요)
        if "room_name" in res_cols and ROOM_NAME:
            return {
                "mode": "by_name",
                "res_room_col": "room_name",
                "rooms_pk": None,
                "rooms_name_col": "room_name"
            }

        # 2) 아니면 reservations.room_id 있으면 ID로 필터 (JOIN 사용)
        if "room_id" in res_cols and ROOM_ID is not None:
            rooms_pk = "room_id" if "room_id" in room_cols else ("id" if "id" in room_cols else None)
            if not rooms_pk:
                raise RuntimeError("rooms 테이블의 PK(room_id 또는 id)가 필요합니다.")
            rooms_name_col = "room_name" if "room_name" in room_cols else ("name" if "name" in room_cols else None)
            return {
                "mode": "by_id",
                "res_room_col": "room_id",
                "rooms_pk": rooms_pk,
                "rooms_name_col": rooms_name_col
            }

        # 3) 둘 다 없는 경우 → 에러
        raise RuntimeError("reservations 테이블에 room_name 또는 room_id 컬럼이 필요합니다.")

    # ---------- 핵심 로직 ----------
    def verify_and_start(self):
        """인증번호 확인 → CHECKED_IN 전환 → EN 1 → 종료 타이머 세팅"""
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
                # reservations.room_name으로 필터
                cur.execute(f"""
                    SELECT
                        reservations.`id`,
                        reservations.`uid`,
                        reservations.`name`,
                        reservations.`start_time`,
                        reservations.`end_time`,
                        reservations.`reservation_status`,
                        reservations.`room_name`
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
                # by_id: reservations.room_id + rooms JOIN
                cur.execute(f"""
                    SELECT
                        reservations.`id`,
                        reservations.`uid`,
                        reservations.`name`,
                        reservations.`start_time`,
                        reservations.`end_time`,
                        reservations.`reservation_status`
                        {"," if self.schema['rooms_name_col'] else ""} 
                        {f"rooms.`{self.schema['rooms_name_col']}`" if self.schema['rooms_name_col'] else ""}
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

                room_display = (
                    row.get(self.schema["rooms_name_col"], f"Room #{ROOM_ID}")
                    if (row and self.schema["rooms_name_col"])
                    else f"Room #{ROOM_ID}"
                )

            if not row:
                QMessageBox.warning(self, "인증 실패", "번호가 틀리거나 시간대가 아닙니다.")
                return

            # 처음 입실이면 CHECKED_IN로 전환
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

            # 종료 타이머
            remain_ms = max(0, int((row["end_time"] - now).total_seconds() * 1000))
            if self._off_timer:
                self._off_timer.stop()
            self._off_timer = QTimer(self)
            self._off_timer.setSingleShot(True)
            self._off_timer.timeout.connect(lambda: self._auto_stop(row["id"]))
            self._off_timer.start(remain_ms)

            # UI 업데이트
            self.lbl_msg.setText(
                f"입실 완료: {room_display}\n"
                f"종료 예정: {row['end_time'].strftime('%Y-%m-%d %H:%M')}"
            )
            self.le_code.clear()
            self._set_statusbar("입실/자동가동 처리 완료")

        except Exception as e:
            QMessageBox.critical(self, "오류", f"인증 처리 실패: {e}")

    def _auto_stop(self, reservation_id: int):
        """예약 종료 시각 도달 →ENE 0 → FINISHED"""
        # HVAC OFF
        try:
            self._send_cmd("EN 0")
        except Exception as e:
            self._set_statusbar(f"HVAC OFF 실패: {e}")

        # 상태 업데이트
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

    def poll_hvac_status(self):
        """(선택) 상태조회 HR"""
        try:
            self._send_cmd("HR")
            # 스케치가 한 줄 더 보낼 수 있어 추가로 읽기 시도
            try:
                raw = self.ser.readline().decode(errors="ignore").strip()
                if raw:
                    self.lbl_status.setText(raw)  # TEMP/HUM/ENABLE/STATE 라인
            except Exception:
                pass
        except Exception as e:
            self._set_statusbar(f"상태 조회 실패: {e}")

    # ---------- 종료 처리 ----------
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

# ---------- main ----------
if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = RoomKiosk()
    w.show()
    sys.exit(app.exec())
