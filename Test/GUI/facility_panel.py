#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 설비 제어·모니터링 (관리자용 간결 UI) - 조명/냉난방 분리 + AUTO 모드

import sys, os, re
from PyQt6.QtWidgets import QApplication, QMainWindow, QTableWidgetItem
from PyQt6.QtCore import Qt, QTimer
from PyQt6 import uic

import serial, serial.tools.list_ports

UI_PATH = os.path.join(os.path.dirname(__file__), "facility_panel_simple.ui")
from_class = uic.loadUiType(UI_PATH)[0]

LINE_RE = re.compile(
    r"TEMP:(?P<t>[-\d\.]+)C\s+HUM:(?P<h>[-\d\.]+)%\s+ENABLE:(?P<en>[01])\s+STATE:(?P<st>[A-Z_]+)(?:.*?\bLIGHT:(?P<light>ON|OFF))?(?:.*?\bMODE:(?P<mode>[A-Z]+))?",
    re.IGNORECASE,
)

# 시뮬레이터 상태
SIM_BUILD = dict(t=25.0, h=50.0, en=0, st="DISABLED", light="OFF", mode_hvac="OFF", mode_light="OFF")
SIM_ROOM  = dict(t=26.0, h=55.0, en=0, st="DISABLED", light="OFF", mode_hvac="OFF", mode_light="OFF")

# 직렬 명령(펌웨어 약속: A=auto, 1=on, 0=off)
CMD = {
    "BUILD_HVAC": {"AUTO": "HE A", "ON": "HE 1", "OFF": "HE 0"},
    "BUILD_LIGHT":{"AUTO": "HL A", "ON": "HL 1", "OFF": "HL 0"},
    "ROOM_HVAC":  {"AUTO": "EN A", "ON": "EN 1", "OFF": "EN 0"},
    "ROOM_LIGHT": {"AUTO": "EL A", "ON": "EL 1", "OFF": "EL 0"},
}
CMD_STATUS = "HR"

MODE_ITEMS = ["AUTO", "ON", "OFF"]  # 콤보박스 순서 고정

class FacilityPanel(QMainWindow, from_class):
    def __init__(self):
        super().__init__()
        self.setupUi(self)

        self.ser_build = None
        self.ser_room  = None

        # 포트
        self.btn_refresh_ports.clicked.connect(self.refresh_ports)
        self.refresh_ports()

        # 모드 콤보 초기화(없으면 무시)
        for cb in ("cmb_build_hvac_mode", "cmb_build_light_mode",
                   "cmb_room_hvac_mode", "cmb_room_light_mode"):
            if hasattr(self, cb):
                box = getattr(self, cb)
                if box.count() == 0:
                    box.addItems(MODE_ITEMS)

        # 시그널 연결
        if hasattr(self, "cmb_build_hvac_mode"):
            self.cmb_build_hvac_mode.currentIndexChanged.connect(self._on_build_hvac_mode)
        if hasattr(self, "cmb_build_light_mode"):
            self.cmb_build_light_mode.currentIndexChanged.connect(self._on_build_light_mode)
        if hasattr(self, "cmb_room_hvac_mode"):
            self.cmb_room_hvac_mode.currentIndexChanged.connect(self._on_room_hvac_mode)
        if hasattr(self, "cmb_room_light_mode"):
            self.cmb_room_light_mode.currentIndexChanged.connect(self._on_room_light_mode)

        self.btn_build_refresh.clicked.connect(self.query_build)
        self.btn_room_refresh.clicked.connect(self.query_room)
        self.btn_refresh_all.clicked.connect(self.refresh_all)

        # 테이블
        self.tbl_status.setColumnCount(6)
        self.tbl_status.setHorizontalHeaderLabels(["대상","온도(°C)","습도(%)","ENABLE","STATE","LIGHT"])
        self.tbl_status.setRowCount(2)
        self._init_row(0, "건물")
        self._init_row(1, "회의실")

        # 주기 모니터링
        self.timer = QTimer(self)
        self.timer.setInterval(5000)
        self.timer.timeout.connect(self.refresh_all)
        self.timer.start()

        # 시작 동기화
        QTimer.singleShot(200, self.refresh_all)

        # 초기 콤보 상태(시뮬레이터 기준)
        self._set_combo_safely("cmb_build_hvac_mode", "OFF")
        self._set_combo_safely("cmb_build_light_mode", "OFF")
        self._set_combo_safely("cmb_room_hvac_mode",  "OFF")
        self._set_combo_safely("cmb_room_light_mode", "OFF")

    # ---------- 유틸 ----------
    def _set_status(self, msg:str):
        self.statusbar.showMessage(msg)
        if hasattr(self, "lbl_msg"):
            self.lbl_msg.setText(f"메시지: {msg}")

    def _init_row(self, row:int, title:str):
        item = QTableWidgetItem(title)
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.tbl_status.setItem(row, 0, item)
        for col in range(1, 6):
            self.tbl_status.setItem(row, col, QTableWidgetItem("-"))

    def _open_serial(self, port):
        if not port:
            return None
        try:
            return serial.Serial(port=port, baudrate=9600, timeout=1)
        except Exception as e:
            self._set_status(f"{port} 연결 실패: {e}")
            return None

    def refresh_ports(self):
        # 콤보 리빌드
        self.cmb_build_port.clear()
        self.cmb_room_port.clear()
        ports = [p.device for p in serial.tools.list_ports.comports()]
        for dev in ports:
            self.cmb_build_port.addItem(dev)
            self.cmb_room_port.addItem(dev)

        # 기존 포트 닫기
        for ser in (self.ser_build, self.ser_room):
            try:
                if ser and ser.is_open: ser.close()
            except: pass

        # 자동 연결(첫 항목)
        self.ser_build = self._open_serial(self.cmb_build_port.currentText() or None)
        self.ser_room  = self._open_serial(self.cmb_room_port.currentText() or None)
        self._set_status("포트 목록 갱신")

    def _write_and_readline(self, ser, line):
        if not ser: return None
        try:
            ser.reset_input_buffer()
            ser.write((line.strip()+"\n").encode("utf-8"))
            ser.flush()
            return ser.readline().decode(errors="ignore").strip()
        except Exception as e:
            self._set_status(f"직렬 통신 오류: {e}")
            return None

    def _is_sim(self) -> bool:
        try:
            return self.chk_simulate.isChecked()
        except Exception:
            return True

    @staticmethod
    def _ser_ok(ser) -> bool:
        try:
            return bool(ser and ser.is_open)
        except Exception:
            return False

    def _set_combo_safely(self, name:str, mode:str):
        if not hasattr(self, name): return
        box = getattr(self, name)
        try:
            idx = MODE_ITEMS.index(mode.upper())
        except ValueError:
            idx = 0
        # 시그널 일시 차단 후 선택
        try:
            old = box.blockSignals(True)
            box.setCurrentIndex(idx)
        finally:
            box.blockSignals(old)

    # ---------- 모드 핸들러 (건물) ----------
    def _on_build_hvac_mode(self, idx:int):
        mode = MODE_ITEMS[idx]
        if self._is_sim() or not self._ser_ok(self.ser_build):
            SIM_BUILD["mode_hvac"] = mode
            if mode == "AUTO":
                SIM_BUILD.update(st="AUTO")
            elif mode == "ON":
                SIM_BUILD.update(en=1, st="IDLE")
            else:
                SIM_BUILD.update(en=0, st="DISABLED")
            self._update_build_status_sim()
            return
        self._send_mode(self.ser_build, "BUILD_HVAC", mode, target_row=0)

    def _on_build_light_mode(self, idx:int):
        mode = MODE_ITEMS[idx]
        if self._is_sim() or not self._ser_ok(self.ser_build):
            SIM_BUILD["mode_light"] = mode
            if mode == "AUTO":
                pass  # 조명 자동 로직은 컨트롤러가 수행한다고 가정
            elif mode == "ON":
                SIM_BUILD.update(light="ON")
            else:
                SIM_BUILD.update(light="OFF")
            self._update_build_status_sim()
            return
        self._send_mode(self.ser_build, "BUILD_LIGHT", mode, target_row=0)

    # ---------- 모드 핸들러 (회의실) ----------
    def _on_room_hvac_mode(self, idx:int):
        mode = MODE_ITEMS[idx]
        if self._is_sim() or not self._ser_ok(self.ser_room):
            SIM_ROOM["mode_hvac"] = mode
            if mode == "AUTO":
                SIM_ROOM.update(st="AUTO")
            elif mode == "ON":
                SIM_ROOM.update(en=1, st="IDLE")
            else:
                SIM_ROOM.update(en=0, st="DISABLED")
            self._update_room_status_sim()
            return
        self._send_mode(self.ser_room, "ROOM_HVAC", mode, target_row=1)

    def _on_room_light_mode(self, idx:int):
        mode = MODE_ITEMS[idx]
        if self._is_sim() or not self._ser_ok(self.ser_room):
            SIM_ROOM["mode_light"] = mode
            if mode == "AUTO":
                pass
            elif mode == "ON":
                SIM_ROOM.update(light="ON")
            else:
                SIM_ROOM.update(light="OFF")
            self._update_room_status_sim()
            return
        self._send_mode(self.ser_room, "ROOM_LIGHT", mode, target_row=1)

    def _send_mode(self, ser, key:str, mode:str, target_row:int):
        cmd = CMD[key][mode]
        resp = self._write_and_readline(ser, cmd)
        if target_row == 0 and hasattr(self, "lbl_build_status") and resp:
            self.lbl_build_status.setText(resp)
        if target_row == 1 and hasattr(self, "lbl_room_status") and resp:
            self.lbl_room_status.setText(resp)
        self._post_write_refresh(ser, target_row)

    def _update_build_status_sim(self):
        s = SIM_BUILD
        if hasattr(self, "lbl_build_status"):
            self.lbl_build_status.setText(
                f"TEMP:{s['t']:.1f}C HUM:{s['h']:.1f}% ENABLE:{s['en']} STATE:{s['st']} LIGHT:{s['light']}"
            )
        self._update_table_row(0, s['t'], s['h'], s['en'], s['st'], s['light'])

    def _update_room_status_sim(self):
        s = SIM_ROOM
        if hasattr(self, "lbl_room_status"):
            self.lbl_room_status.setText(
                f"TEMP:{s['t']:.1f}C HUM:{s['h']:.1f}% ENABLE:{s['en']} STATE:{s['st']} LIGHT:{s['light']}"
            )
        self._update_table_row(1, s['t'], s['h'], s['en'], s['st'], s['light'])

    # ---------- 상태 조회 ----------
    def query_build(self):
        if self._is_sim() or not self._ser_ok(self.ser_build):
            self._update_build_status_sim()
            return
        line = self._write_and_readline(self.ser_build, CMD_STATUS)
        if not line: return
        self.lbl_build_status.setText(line)
        self._parse_and_update(0, line)

    def query_room(self):
        if self._is_sim() or not self._ser_ok(self.ser_room):
            self._update_room_status_sim()
            return
        line = self._write_and_readline(self.ser_room, CMD_STATUS)
        if not line: return
        self.lbl_room_status.setText(line)
        self._parse_and_update(1, line)

    # ---------- 파싱/테이블 ----------
    def _parse_and_update(self, row:int, line:str):
        try:
            m = LINE_RE.search(line)
            if m:
                t = float(m.group("t"))
                h = float(m.group("h"))
                en = int(m.group("en"))
                st = m.group("st").upper()
                light = (m.group("light") or "-").upper()
            else:
                # 느슨한 백업 파서
                up = line.upper()
                t = float(self._between(line, "TEMP:", "C"))
                h = float(self._between(line, "HUM:", "%"))
                en = 1 if "ENABLE:1" in up else 0
                st = self._after(up, "STATE:").split()[0]
                light = "ON" if "LIGHT:ON" in up else ("OFF" if "LIGHT:OFF" in up else "-")
            self._update_table_row(row, t, h, en, st, light)
        except Exception:
            self._set_status(f"파싱 실패: {line}")

    def _update_table_row(self, row:int, t, h, en, st, light):
        vals = [f"{t:.1f}", f"{h:.1f}", str(en), str(st), str(light)]
        for i, v in enumerate(vals, start=1):
            item = QTableWidgetItem(v)
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.tbl_status.setItem(row, i, item)

    @staticmethod
    def _between(s, a, b):
        i = s.find(a); j = s.find(b, i+len(a))
        return s[i+len(a):j].strip()

    @staticmethod
    def _after(s, a):
        i = s.find(a)
        return s[i+len(a):].strip() if i >= 0 else ""

    # ---------- 버튼: 전체 새로고침 ----------
    def refresh_all(self):
        self.query_build()
        self.query_room()

    # ---------- 쓰기 후 동기화 ----------
    def _post_write_refresh(self, ser, row:int):
        line = self._write_and_readline(ser, CMD_STATUS)
        if not line: return
        if row == 0 and hasattr(self, "lbl_build_status"):
            self.lbl_build_status.setText(line)
        if row == 1 and hasattr(self, "lbl_room_status"):
            self.lbl_room_status.setText(line)
        self._parse_and_update(row, line)

    # ---------- 종료 ----------
    def closeEvent(self, ev):
        for ser in (self.ser_build, self.ser_room):
            try:
                if ser and ser.is_open: ser.close()
            except: pass
        ev.accept()

# ---- main ----
if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = FacilityPanel()
    w.show()
    sys.exit(app.exec())
