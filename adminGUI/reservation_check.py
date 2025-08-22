#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
from PyQt6.QtWidgets import QMainWindow, QMessageBox, QApplication, QComboBox, QVBoxLayout, QLabel, QGroupBox, QLineEdit, QFrame
from PyQt6 import uic
from PyQt6.QtCore import Qt
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
        self.handle_expired_reservations()  # 프로그램 시작 시 만료된 예약 처리
        self.load_users()
        self.load_users_to_combobox()

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

    def handle_expired_reservations(self):
        """
        예약 시간이 지났고, 'BOOKED' 상태인 예약을 찾아 'CHECKED_OUT' 상태로 자동 변경합니다.
        """
        if not self.db_conn or not self.db_conn.is_connected():
            return
            
        try:
            cursor = self.db_conn.cursor()
            now = datetime.now()
            
            # 종료 시간이 현재 시간보다 이전이고, 상태가 'BOOKED'인 예약을 찾음
            cursor.execute("""
                SELECT COUNT(*) FROM reservations
                WHERE end_time < %s AND reservation_status = 'BOOKED'
            """, (now,))
            
            count = cursor.fetchone()[0]
            
            if count > 0:
                # 상태를 'CHECKED_OUT'으로 일괄 변경
                cursor.execute("""
                    UPDATE reservations
                    SET reservation_status = 'CHECKED_OUT', updated_at = %s
                    WHERE end_time < %s AND reservation_status = 'BOOKED'
                """, (now, now))
                self.db_conn.commit()
                print(f"{count}개의 만료된 예약이 CHECKED_OUT 상태로 변경되었습니다.")
                QMessageBox.information(self, "자동 업데이트", f"{count}개의 만료된 예약이 자동으로 처리되었습니다.")
        except Exception as e:
            print(f"만료된 예약 처리 중 오류 발생: {e}")
        finally:
            cursor.close()

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
            self.userIDComboBox.currentIndexChanged.connect(self.update_user_name_input)
        else:
            print("UI에 userIDComboBox가 정의되지 않았습니다.")
            
    def update_user_name_input(self):
        """ automatically fills the name field based on the selected UID """
        selected_uid = self.userIDComboBox.currentText()
        if selected_uid in self.users:
            self.userNameInput.setText(self.users[selected_uid])
        else:
            self.userNameInput.clear()

    def find_auth_code(self):
        """직원 코드와 이름으로 예약 인증번호를 조회하는 함수"""
        uid = self.userIDComboBox.currentText().strip()
        user_name = self.userNameInput.text().strip()

        if not uid or not user_name:
            QMessageBox.warning(self, "경고", "직원 코드와 사용자 이름을 모두 선택하세요.")
            return

        # 기존 동적 위젯 초기화
        self.clear_dynamic_widgets()

        try:
            cursor = self.db_conn.cursor()
            now = datetime.now()
            print(f"디버깅 - 현재 시간: {now}")
            print(f"디버깅 - 입력된 UID: {uid}, 이름: {user_name}")

            # uid와 name으로 유효한 BOOKED 또는 CHECKED_IN 상태의 모든 예약을 찾음
            cursor.execute("""
                SELECT r.auth_code, r.room_name, r.start_time, r.end_time
                FROM reservations r
                LEFT JOIN users u ON r.uid = u.uid
                WHERE r.uid = %s AND u.name = %s
                AND (r.start_time >= %s OR (r.start_time <= %s AND r.end_time >= %s))
                AND r.reservation_status IN ('BOOKED', 'CHECKED_IN')
                ORDER BY r.start_time ASC
            """, (uid, user_name, now, now, now))

            results = cursor.fetchall()
            print(f"디버깅 - 쿼리 결과: {results}")  # 쿼리 결과를 출력

            if results:
                self.statusLabel.setText("상태: <font color='blue'>예약 정보가 확인되었습니다.</font>")
                self.create_dynamic_widgets(results)
            else:
                self.statusLabel.setText("상태: <font color='red'>일치하는 예약 정보가 없습니다.</font>")

        except Exception as e:
            QMessageBox.critical(self, "오류", f"예약 정보 조회 중 오류 발생: {e}")
            self.statusLabel.setText("상태: <font color='red'>오류 발생</font>")
            print(f"디버깅 - 예외 발생: {e}")
        finally:
            cursor.close()

    def create_dynamic_widgets(self, reservations):
        """ 여러 예약 정보를 동적으로 생성하여 표시 """
        group_box = self.reservationDetailsGroup
        
        # 기존 레이아웃 및 위젯 제거 (UI가 빈 상태이므로 안전)
        self.clear_dynamic_widgets()
        
        layout = QVBoxLayout(group_box)

        for auth_code, room_name, start_time, end_time in reservations:
            reservation_info_label = QLabel(
                f"<b>회의실:</b> {room_name}<br>"
                f"<b>시작:</b> {start_time.strftime('%Y-%m-%d %H:%M:%S')}<br>"
                f"<b>종료:</b> {end_time.strftime('%Y-%m-%d %H:%M:%S')}<br>"
                f"<b>인증 번호:</b> <font color='blue' size='5'><b>{auth_code}</b></font>"
            )
            reservation_info_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
            layout.addWidget(reservation_info_label)
            
            line = QFrame(group_box)
            line.setFrameShape(QFrame.Shape.HLine)
            line.setFrameShadow(QFrame.Shadow.Sunken)
            layout.addWidget(line)
        
        group_box.setLayout(layout)

    def clear_dynamic_widgets(self):
        """ 기존 동적 위젯을 제거 """
        group_box = self.reservationDetailsGroup
        if group_box.layout():
            while group_box.layout().count():
                child = group_box.layout().takeAt(0)
                if child.widget():
                    child.widget().deleteLater()

    def closeEvent(self, event):
        if self.db_conn:
            self.db_conn.close()
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = ReservationCheckWindow()
    window.show()
    sys.exit(app.exec())