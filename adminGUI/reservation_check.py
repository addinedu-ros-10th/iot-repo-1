#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
from PyQt6.QtWidgets import QMainWindow, QMessageBox, QApplication, QComboBox
from PyQt6 import uic
import mysql.connector
from datetime import datetime

class ReservationCheckWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        try:
            uic.loadUi("reservation_check.ui", self)
        except FileNotFoundError:
            QMessageBox.critical(self, "오류", "reservation_check.ui 파일을 찾을 수 없습니다.")
            sys.exit(1)

        self.db_conn = None
        self.users = {} 
        self.connect_db()
        self.load_users()
        self.load_users_to_combobox()

        # '인증 확인' 버튼 클릭 시 find_auth_code 함수 호출
        self.verifyBtn.clicked.connect(self.find_auth_code)

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

    def load_users(self):
        """ loads user info from users table into a cache dictionary """
        if self.db_conn and self.db_conn.is_connected():
            try:
                cursor = self.db_conn.cursor()
                cursor.execute("SELECT uid, name FROM users")
                for uid, name in cursor.fetchall():
                    self.users[uid] = name
            except Exception as e:
                print(f"사용자 정보 로드 실패: {e}")

    def load_users_to_combobox(self):
        """ loads UIDs from the users table into the combobox """
        if hasattr(self, 'userIDComboBox'):
            self.userIDComboBox.clear()
            uids = sorted(self.users.keys())
            self.userIDComboBox.addItems(uids)
            # 이름 자동 채우기 로직은 제거합니다.
            # self.userIDComboBox.currentIndexChanged.connect(self.update_user_name_input)
            # self.update_user_name_input()
        else:
            print("UI에 userIDComboBox가 정의되지 않았습니다.")
            
    def update_user_name_input(self):
        """ automatically fills the name field based on the selected UID """
        # 이름 자동 채우기 로직은 제거합니다.
        pass

    def find_auth_code(self):
        """직원 코드와 이름으로 예약 인증번호를 조회하는 함수"""
        uid = self.userIDComboBox.currentText().strip()
        # 사용자가 직접 입력한 이름을 가져옵니다.
        user_name = self.userNameInput.text().strip()

        if not uid or not user_name:
            QMessageBox.warning(self, "경고", "직원 코드와 사용자 이름을 모두 선택/입력하세요.")
            return

        try:
            cursor = self.db_conn.cursor()
            now = datetime.now()
            
            # uid와 name으로 유효한 BOOKED 상태의 예약을 찾음
            cursor.execute("""
                SELECT r.auth_code
                FROM reservations r
                LEFT JOIN users u ON r.uid = u.uid
                WHERE r.uid = %s AND u.name = %s
                AND r.start_time <= %s AND r.end_time >= %s
                AND r.reservation_status = 'BOOKED'
                ORDER BY r.start_time ASC LIMIT 1
            """, (uid, user_name, now, now))
            
            result = cursor.fetchone()
            
            if result:
                auth_code = result[0]
                self.authCodeInput.setText(auth_code)
                self.statusLabel.setText("상태: <font color='blue'>예약 정보가 확인되었습니다.</font>")
            else:
                self.authCodeInput.clear()
                self.statusLabel.setText("상태: <font color='red'>일치하는 예약 정보가 없습니다.</font>")

        except Exception as e:
            QMessageBox.critical(self, "오류", f"예약 정보 조회 중 오류 발생: {e}")
            self.statusLabel.setText("상태: <font color='red'>오류 발생</font>")
        finally:
            cursor.close()

    def closeEvent(self, event):
        if self.db_conn:
            self.db_conn.close()
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = ReservationCheckWindow()
    window.show()
    sys.exit(app.exec())
