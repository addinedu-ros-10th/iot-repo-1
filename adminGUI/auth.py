#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
from PyQt6.QtWidgets import QMainWindow, QMessageBox, QApplication, QLabel, QComboBox
from PyQt6 import uic
from PyQt6.QtCore import pyqtSignal, QTimer
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
        self.user_role = None
        self.connect_db()

        # 버튼 연결
        self.loginSuccessBtn.clicked.connect(self.test_login_success)

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

    def test_login_success(self):
        """테스트용 로그인 성공 버튼"""
        self.user_role = self.roleComboBox.currentText()  # 선택된 권한 가져오기
        message = f"테스트용 로그인 성공 (권한: {self.user_role})"
        self.statusLabel.setText(f"상태: {message}")
        QMessageBox.information(self, "로그인 성공", message)
        self.open_main_window()

    def open_main_window(self):
        """홈 화면을 열고 현재 창을 숨깁니다."""
        self.home_window = HomeWindow(self.user_role)
        self.home_window.show()
        self.hide()

    def closeEvent(self, event):
        if self.db_conn:
            self.db_conn.close()
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = AuthWindow()
    window.show()
    sys.exit(app.exec())