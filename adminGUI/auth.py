#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
from PyQt6.QtWidgets import QMainWindow, QMessageBox, QApplication
from PyQt6.uic import loadUi
import mysql.connector

# home.py 파일에서 HomeWindow 클래스를 가져옵니다.
# 이 코드를 실행하려면 동일한 디렉토리에 home.py와 HomeWindow 클래스가 정의되어 있어야 합니다.
try:
    from home import HomeWindow
except ImportError:
    # home.py가 없을 경우를 대비한 임시 클래스
    class HomeWindow(QMainWindow):
        def __init__(self, user_role=None):
            super().__init__()
            self.setWindowTitle("홈 화면 (임시)")
            self.setGeometry(100, 100, 400, 300)
            print(f"임시 홈 화면이 '{user_role}' 권한으로 열렸습니다.")


class AuthWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        try:
            # uic.loadUi가 아니라 loadUi를 직접 사용합니다.
            loadUi("auth.ui", self)
        except FileNotFoundError:
            QMessageBox.critical(self, "오류", "auth.ui 파일을 찾을 수 없습니다.")
            sys.exit(1)
        except Exception as e:
            # .ui 파일의 위젯 이름이 코드와 일치하지 않을 때 발생하는 오류 등을 잡기 위함
            QMessageBox.critical(self, "UI 파일 오류", f"auth.ui 파일을 로드하는 중 오류가 발생했습니다: {e}")
            sys.exit(1)


        self.db_conn = None
        self.user_role = None
        self.connect_db()

        # .ui 파일에 정의된 위젯 이름이 정확한지 확인하세요.
        # 예: self.loginSuccessBtn, self.roleComboBox, self.statusLabel
        try:
            # 버튼 연결
            self.loginSuccessBtn.clicked.connect(self.test_login_success)
        except AttributeError as e:
            QMessageBox.critical(self, "위젯 오류", f".ui 파일에 필요한 위젯이 없습니다: {e}")
            self.close()


    def connect_db(self):
        """데이터베이스에 연결합니다."""
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
        except AttributeError:
            # statusbar가 .ui 파일에 없는 경우
            print("상태 표시줄(statusbar)을 찾을 수 없습니다.")


    def test_login_success(self):
        """테스트용 로그인 성공 버튼 핸들러"""
        try:
            self.user_role = self.roleComboBox.currentText()  # 선택된 권한 가져오기
            message = f"테스트용 로그인 성공 (권한: {self.user_role})"
            self.statusLabel.setText(f"상태: {message}")
            QMessageBox.information(self, "로그인 성공", message)
            self.open_main_window()
        except AttributeError as e:
            QMessageBox.critical(self, "위젯 오류", f"로그인 처리 중 위젯을 찾을 수 없습니다: {e}")


    def open_main_window(self):
        """홈 화면을 열고 현재 창을 숨깁니다."""
        self.home_window = HomeWindow(self.user_role)
        self.home_window.show()
        self.hide()

    def closeEvent(self, event):
        """창이 닫힐 때 데이터베이스 연결을 종료합니다."""
        if self.db_conn and self.db_conn.is_connected():
            self.db_conn.close()
            print("데이터베이스 연결이 종료되었습니다.")
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = AuthWindow()
    window.show()
    sys.exit(app.exec())
