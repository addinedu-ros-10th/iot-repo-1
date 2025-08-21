import sys
from PyQt6.QtWidgets import QMainWindow, QMessageBox, QApplication, QLabel
from PyQt6 import uic
from PyQt6.QtCore import pyqtSignal, QTimer
import serial
import struct
import mysql.connector

# home.py 파일에서 HomeWindow 클래스를 가져옵니다.
from home import HomeWindow

class AuthWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        try:
            uic.loadUi("auth.ui", self)
        except FileNotFoundError:
            QMessageBox.critical(self, "오류", "auth.ui 파일을 찾을 수 없습니다.")
            sys.exit(1)

        self.db_conn = None
        self.serial_conn = None
        self.user_role = None
        self.connect_db()
        self.connect_serial()

        # 버튼 연결
        self.rfidBtn.clicked.connect(self.authenticate_rfid)
        self.loginBtn.clicked.connect(self.authenticate_id)
        # 시험용 버튼 연결
        self.testBtn.clicked.connect(self.test_login)

    def connect_db(self):
        try:
            self.db_conn = mysql.connector.connect(
                host="database-1.c1kkeqig4j9x.ap-northeast-2.rds.amazonaws.com",
                port=3306,
                user="root",
                password="12345678",  # RDS 비밀번호
                database="joeffice"
            )
            self.statusbar.showMessage("DB 연결 성공")
        except mysql.connector.Error as err:
            self.statusbar.showMessage(f"DB 연결 실패: {err}")
            QMessageBox.critical(self, "오류", f"데이터베이스 연결 실패: {err}")

    def connect_serial(self):
        try:
            self.serial_conn = serial.Serial(port='/dev/ttyACM0', baudrate=9600, timeout=1)
            self.statusbar.showMessage("시리얼 연결 성공")
        except serial.SerialException as e:
            self.statusbar.showMessage(f"시리얼 연결 실패: {e}")

    def authenticate_id(self):
        """사번/ID를 이용한 시험용 로그인 성공 로직"""
        user_id = self.idInput.text().strip()
        if user_id:
            # 여기서는 DB 연결 없이 무조건 성공했다고 가정
            self.user_role = "admin" # 또는 "user"
            self.statusLabel.setText(f"상태: 시험용 로그인 성공 (권한: {self.user_role})")
            QMessageBox.information(self, "로그인 성공", f"시험용으로 로그인되었습니다: {user_id}")
            self.open_main_window()
        else:
            self.statusLabel.setText("상태: 사번/ID를 입력하세요.")
            QMessageBox.warning(self, "경고", "사번/ID를 입력해야 합니다.")

    def authenticate_rfid(self):
        """RFID 인증을 이용한 시험용 로그인 성공 로직"""
        # 여기서는 시리얼 통신 없이 무조건 성공했다고 가정
        self.user_role = "user" # 또는 "admin"
        self.statusLabel.setText(f"상태: 시험용 RFID 인증 성공 (권한: {self.user_role})")
        QMessageBox.information(self, "RFID 인증 성공", "시험용 RFID 인증이 완료되었습니다.")
        self.open_main_window()
    
    def test_login(self):
        """시험용 로그인 성공 로직"""
        self.user_role = "admin"
        self.statusLabel.setText(f"상태: 시험용 로그인 성공 (권한: {self.user_role})")
        QMessageBox.information(self, "로그인 성공", "시험용으로 관리자 로그인되었습니다.")
        self.open_main_window()

    def open_main_window(self):
        """홈 화면을 열고 현재 창을 숨깁니다."""
        self.home_window = HomeWindow(self.user_role)
        self.home_window.show()
        self.hide()

    def closeEvent(self, event):
        if self.db_conn:
            self.db_conn.close()
        if self.serial_conn:
            self.serial_conn.close()
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = AuthWindow()
    window.show()
    sys.exit(app.exec())
