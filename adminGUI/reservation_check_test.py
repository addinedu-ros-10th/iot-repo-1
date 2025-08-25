#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
from PyQt6.QtWidgets import (QMainWindow, QMessageBox, QApplication, QComboBox, 
                             QVBoxLayout, QLabel, QGroupBox, QLineEdit, QFrame, 
                             QPushButton, QHBoxLayout)
from PyQt6 import uic
from PyQt6.QtCore import Qt, QTimer
import mysql.connector
from datetime import datetime
import serial # pyserial 라이브러리 임포트

# --- Arduino 설정 ---
# 사용자의 PC에 연결된 Arduino 포트 이름으로 변경해야 합니다.
# 예: "/dev/ttyUSB0" (Linux) 또는 "/dev/tty.usbmodem14101" (macOS)
ARDUINO_PORT = "/dev/ttyUSB0" 
BAUD_RATE = 9600

class ReservationCheckWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        try:
            uic.loadUi("reservation_check.ui", self)
        except FileNotFoundError:
            QMessageBox.critical(self, "오류", "reservation_check.ui 파일을 찾을 수 없습니다.")
            sys.exit(1)

        # --- DB 및 Arduino 연결 초기화 ---
        self.db_conn = None
        self.serial_port = None
        self.users = {} 
        self.valid_reservations = [] # 인증 번호 확인을 위한 리스트

        self.connect_db()
        self.connect_to_arduino() # Arduino 연결 시도

        # --- 기존 로직 실행 ---
        self.handle_expired_reservations()
        self.load_users()
        self.load_users_to_combobox()

        # --- UI 동적 추가 및 시그널 연결 ---
        self.setup_auth_ui()
        self.verifyBtn.clicked.connect(self.find_auth_code)

        # Arduino로부터 데이터 수신을 위한 타이머
        self.timer = QTimer(self)
        self.timer.setInterval(100) # 100ms 마다
        self.timer.timeout.connect(self.read_from_arduino)
        self.timer.start()

    def setup_auth_ui(self):
        """인증번호 입력 및 문 열기 버튼 UI를 동적으로 생성하고 레이아웃에 추가"""
        self.authCodeInput = QLineEdit()
        self.authCodeInput.setPlaceholderText("4자리 인증 번호 입력")
        self.authCodeInput.setMaxLength(4)
        
        self.openDoorBtn = QPushButton("문 열기")
        self.openDoorBtn.setEnabled(False) # 처음에는 비활성화
        self.openDoorBtn.clicked.connect(self.check_and_open_door)

        # 수평 레이아웃에 위젯 추가
        auth_layout = QHBoxLayout()
        auth_layout.addWidget(self.authCodeInput)
        auth_layout.addWidget(self.openDoorBtn)

        # reservationDetailsGroup 아래에 새 레이아웃 추가
        main_layout = self.centralWidget().layout()
        if main_layout:
             # reservationDetailsGroup 위젯을 찾아서 그 아래에 추가
            groupbox_index = -1
            for i in range(main_layout.count()):
                widget = main_layout.itemAt(i).widget()
                if isinstance(widget, QGroupBox) and widget.objectName() == "reservationDetailsGroup":
                    groupbox_index = i
                    break
            if groupbox_index != -1:
                main_layout.insertLayout(groupbox_index + 1, auth_layout)
            else: # 못찾으면 그냥 맨 아래에 추가
                main_layout.addLayout(auth_layout)

    def connect_db(self):
        try:
            self.db_conn = mysql.connector.connect(
                host="database-1.c1kkeqig4j9x.ap-northeast-2.rds.amazonaws.com",
                port=3306,
                user="joeffice_user",
                password="12345678",
                database="joeffice"
            )
            print("DB 연결 성공")
        except mysql.connector.Error as err:
            QMessageBox.critical(self, "오류", f"데이터베이스 연결 실패: {err}")
            sys.exit(1)

    def connect_to_arduino(self):
        """Arduino와 시리얼 포트 연결"""
        try:
            self.serial_port = serial.Serial(ARDUINO_PORT, BAUD_RATE, timeout=0.1)
            # [수정] self.statusbar -> self.statusBar
            self.statusBar().showMessage(f"Arduino 연결 성공 ({ARDUINO_PORT})")
            print(f"Arduino 연결 성공 ({ARDUINO_PORT})")
        except serial.SerialException as e:
            # [수정] self.statusbar -> self.statusBar
            self.statusBar().showMessage(f"Arduino 연결 실패: {e}")
            print(f"Arduino 연결 실패: {e}")

    def handle_expired_reservations(self):
        if not self.db_conn or not self.db_conn.is_connected(): return
        try:
            cursor = self.db_conn.cursor()
            now = datetime.now()
            cursor.execute("UPDATE reservations SET reservation_status = 'CHECKED_OUT', updated_at = %s WHERE end_time < %s AND reservation_status = 'BOOKED'", (now, now))
            self.db_conn.commit()
            if cursor.rowcount > 0:
                print(f"{cursor.rowcount}개의 만료된 예약이 처리되었습니다.")
        except Exception as e:
            print(f"만료된 예약 처리 중 오류 발생: {e}")

    def load_users(self):
        if not (self.db_conn and self.db_conn.is_connected()): return
        try:
            cursor = self.db_conn.cursor(dictionary=True)
            cursor.execute("SELECT uid, name FROM users")
            self.users = {row['uid']: row['name'] for row in cursor.fetchall()}
        except Exception as e:
            print(f"사용자 정보 로드 실패: {e}")

    def load_users_to_combobox(self):
        if hasattr(self, 'userIDComboBox'):
            self.userIDComboBox.clear()
            self.userIDComboBox.addItems(sorted(self.users.keys()))
            self.userIDComboBox.currentIndexChanged.connect(self.update_user_name_input)
            if self.userIDComboBox.count() > 0:
                self.update_user_name_input()

    def update_user_name_input(self):
        selected_uid = self.userIDComboBox.currentText()
        self.userNameInput.setText(self.users.get(selected_uid, ""))

    def find_auth_code(self):
        uid = self.userIDComboBox.currentText().strip()
        user_name = self.userNameInput.text().strip()

        if not uid or not user_name:
            QMessageBox.warning(self, "경고", "직원 코드와 사용자 이름을 모두 선택하세요.")
            return

        self.clear_dynamic_widgets()
        self.valid_reservations = []

        try:
            cursor = self.db_conn.cursor(dictionary=True)
            now = datetime.now()
            query = """
                SELECT r.reservation_id, r.auth_code, r.room_name, r.start_time, r.end_time
                FROM reservations r
                JOIN users u ON r.uid = u.uid
                WHERE r.uid = %s AND u.name = %s
                AND (r.end_time >= %s)
                AND r.reservation_status IN ('BOOKED', 'CHECKED_IN')
                ORDER BY r.start_time ASC
            """
            cursor.execute(query, (uid, user_name, now))
            results = cursor.fetchall()

            if results:
                self.statusLabel.setText("상태: <font color='blue'>예약 정보가 확인되었습니다.</font>")
                self.create_dynamic_widgets(results)
                self.valid_reservations = results
                self.openDoorBtn.setEnabled(True)
            else:
                self.statusLabel.setText("상태: <font color='red'>일치하는 예약 정보가 없습니다.</font>")
                self.openDoorBtn.setEnabled(False)

        except Exception as e:
            QMessageBox.critical(self, "오류", f"예약 정보 조회 중 오류 발생: {e}")
        finally:
            cursor.close()

    def check_and_open_door(self):
        input_code = self.authCodeInput.text().strip()
        if not input_code:
            QMessageBox.warning(self, "경고", "4자리 인증 번호를 입력하세요.")
            return

        matching_reservation = next(
            (res for res in self.valid_reservations if str(res['auth_code']) == input_code),
            None
        )

        if matching_reservation:
            # 1. DB 상태 업데이트
            try:
                cursor = self.db_conn.cursor()
                cursor.execute("""
                    UPDATE reservations SET reservation_status = 'CHECKED_IN', updated_at = %s
                    WHERE reservation_id = %s AND reservation_status = 'BOOKED'
                """, (datetime.now(), matching_reservation['reservation_id']))
                self.db_conn.commit()
                print(f"예약 ID {matching_reservation['reservation_id']} 상태가 CHECKED_IN으로 업데이트되었습니다.")
            except Exception as e:
                QMessageBox.critical(self, "DB 오류", f"예약 상태 업데이트 실패: {e}")
                return

            # 2. Arduino에 신호 전송
            self.send_to_arduino('o')
            QMessageBox.information(self, "인증 성공", "인증되었습니다. 문을 엽니다.")
        else:
            QMessageBox.critical(self, "인증 실패", "인증 번호가 올바르지 않습니다.")
            self.authCodeInput.clear()

    def send_to_arduino(self, command):
        """Arduino에 명령(char) 전송"""
        if self.serial_port and self.serial_port.is_open:
            self.serial_port.write(command.encode('utf-8'))
            print(f"Arduino에 명령 전송: {command}")
        else:
            # [수정] self.statusbar -> self.statusBar
            self.statusBar().showMessage("Arduino가 연결되지 않았습니다.")

    def read_from_arduino(self):
        """Arduino로부터 데이터 읽어서 상태바에 표시"""
        if self.serial_port and self.serial_port.is_open and self.serial_port.in_waiting > 0:
            try:
                line = self.serial_port.readline().decode('utf-8').strip()
                if line:
                    # [수정] self.statusbar -> self.statusBar
                    self.statusBar().showMessage(f"Arduino: {line}")
                    print(f"Arduino로부터 수신: {line}")
            except Exception as e:
                print(f"Arduino 데이터 수신 오류: {e}")

    def create_dynamic_widgets(self, reservations):
        group_box = self.reservationDetailsGroup
        self.clear_dynamic_widgets()
        layout = QVBoxLayout(group_box)
        for res in reservations:
            label = QLabel(
                f"<b>회의실:</b> {res['room_name']}<br>"
                f"<b>시작:</b> {res['start_time'].strftime('%Y-%m-%d %H:%M')}<br>"
                f"<b>종료:</b> {res['end_time'].strftime('%Y-%m-%d %H:%M')}<br>"
                f"<b>인증 번호:</b> <font color='blue' size='5'><b>{res['auth_code']}</b></font>"
            )
            layout.addWidget(label)
            line = QFrame(); line.setFrameShape(QFrame.Shape.HLine); line.setFrameShadow(QFrame.Shadow.Sunken)
            layout.addWidget(line)
        group_box.setLayout(layout)

    def clear_dynamic_widgets(self):
        layout = self.reservationDetailsGroup.layout()
        if layout:
            while layout.count():
                child = layout.takeAt(0)
                if child.widget():
                    child.widget().deleteLater()

    def closeEvent(self, event):
        if self.db_conn and self.db_conn.is_connected():
            self.db_conn.close()
        if self.serial_port and self.serial_port.is_open:
            self.serial_port.close()
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = ReservationCheckWindow()
    window.show()
    sys.exit(app.exec())
