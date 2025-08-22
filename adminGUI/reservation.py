#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
from PyQt6.QtWidgets import QMainWindow, QMessageBox, QTableWidgetItem, QLineEdit, QAbstractItemView, QComboBox, QHeaderView
from PyQt6 import uic
from PyQt6.QtCore import QTimer, QDate, QTime, QLocale, QDateTime
import mysql.connector
from datetime import datetime, timedelta
import random

class ReservationWindow(QMainWindow):
    def __init__(self, user_role, current_user_id="bombtol"):
        super().__init__()
        try:
            uic.loadUi("reservation.ui", self)
        except FileNotFoundError:
            QMessageBox.critical(self, "오류", "reservation.ui 파일을 찾을 수 없습니다.")
            sys.exit(1)
            
        self.user_role = user_role
        self.current_user_id = current_user_id
        self.db_conn = None
        self.rooms = {}
        self.users = {}
        self.connect_db()

        # 현재 시간으로 초기값 설정
        now = datetime.now()
        one_hour_later = now + timedelta(hours=1)
        
        # 시작 날짜/시간을 현재 시간으로 설정 (초는 00으로 고정)
        self.startingDateInput.setCalendarPopup(True)
        self.startingDateInput.setLocale(QLocale(QLocale.Language.English, QLocale.Country.UnitedStates))
        self.startingDateInput.setDisplayFormat("yyyy-MM-dd")
        self.startingDateInput.setDate(QDate(now.year, now.month, now.day))
        self.startingTimeInput.setTime(QTime(now.hour, now.minute, 0)) # 초를 00으로 고정
        
        # 종료 날짜/시간을 한 시간 뒤로 설정 (초는 00으로 고정)
        self.endingDateInput.setCalendarPopup(True)
        self.endingDateInput.setLocale(QLocale(QLocale.Language.English, QLocale.Country.UnitedStates))
        self.endingDateInput.setDisplayFormat("yyyy-MM-dd")
        self.endingDateInput.setDate(QDate(one_hour_later.year, one_hour_later.month, one_hour_later.day))
        self.endingTimeInput.setTime(QTime(one_hour_later.hour, one_hour_later.minute, 0)) # 초를 00으로 고정
        
        self.reservationTable.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.reservationTable.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.reservationTable.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)

        self.createBtn.clicked.connect(self.create_reservation)
        self.editCancelBtn.clicked.connect(self.edit_cancel_reservation)
        self.calendarView.selectionChanged.connect(self.update_reservations)

        self.timer = QTimer()
        self.timer.timeout.connect(self.update_reservations)
        self.timer.start(5000)

        self.toggle_buttons()
        self.load_users()
        self.update_rooms()
        self.update_rooms_combobox()
        self.load_users_to_combobox() # 사용자 콤보박스 로드
        self.update_reservations()
        
        # UID 콤보박스 선택 시 이름 자동 채우기 로직 연결
        self.userIDComboBox.currentIndexChanged.connect(self.update_user_name_from_combobox)


    def connect_db(self):
        try:
            self.db_conn = mysql.connector.connect(
                host="database-1.c1kkeqig4j9x.ap-northeast-2.rds.amazonaws.com",
                port=3306,
                user="root",
                password="12345678",
                database="joeffice"
            )
            self.statusbar.showMessage("DB 연결 성공")
        except mysql.connector.Error as err:
            self.statusbar.showMessage(f"DB 연결 실패: {err}")
            QMessageBox.critical(self, "오류", f"데이터베이스 연결 실패: {err}")
            sys.exit(1)

    def load_users(self):
        self.users = {}
        if self.db_conn and self.db_conn.is_connected():
            try:
                cursor = self.db_conn.cursor()
                cursor.execute("SELECT uid, name, company FROM users")
                for uid, name, company in cursor.fetchall():
                    self.users[uid] = {'name': name, 'company': company}
            except Exception as e:
                print(f"사용자 정보 로드 실패: {e}")

    def load_users_to_combobox(self):
        """users 테이블의 UID를 콤보박스에 로드"""
        if self.db_conn and self.db_conn.is_connected():
            try:
                cursor = self.db_conn.cursor()
                cursor.execute("SELECT uid FROM users ORDER BY uid")
                uids = [row[0] for row in cursor.fetchall()]
                if hasattr(self, 'userIDComboBox'):
                    self.userIDComboBox.clear()
                    self.userIDComboBox.addItems(uids)
                    if self.current_user_id in uids:
                        self.userIDComboBox.setCurrentText(self.current_user_id)
                else:
                    print("userIDComboBox가 UI에 정의되지 않음.")
            except Exception as e:
                self.statusbar.showMessage(f"사용자 콤보박스 갱신 실패: {e}")

    def update_user_name_from_combobox(self):
        """콤보박스 선택에 따라 이름 필드 자동 채우기"""
        selected_uid = self.userIDComboBox.currentText()
        if selected_uid in self.users:
            self.userNameInput.setText(self.users[selected_uid]['name'])
        else:
            self.userNameInput.clear()

    def toggle_buttons(self):
        is_allowed = self.user_role in ["user", "admin"]
        self.createBtn.setEnabled(is_allowed)
        self.editCancelBtn.setEnabled(is_allowed)

    def update_rooms(self):
        if self.db_conn and self.db_conn.is_connected():
            try:
                cursor = self.db_conn.cursor()
                cursor.execute("SELECT room_name, capacity, location, equipment FROM rooms")
                rooms = cursor.fetchall()
                self.roomTable.setRowCount(len(rooms))
                for row, (name, capacity, location, equipment) in enumerate(rooms):
                    self.roomTable.setItem(row, 0, QTableWidgetItem(name))
                    self.roomTable.setItem(row, 1, QTableWidgetItem(str(capacity)))
                    self.roomTable.setItem(row, 2, QTableWidgetItem(location))
                    self.roomTable.setItem(row, 3, QTableWidgetItem(equipment))
            except Exception as e:
                self.statusbar.showMessage(f"회의실 목록 갱신 실패: {e}")
        
        # 테이블의 컬럼 너비를 창에 맞게 자동으로 조절
        self.roomTable.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

    def update_rooms_combobox(self):
        if self.db_conn and self.db_conn.is_connected():
            try:
                cursor = self.db_conn.cursor()
                cursor.execute("SELECT room_name FROM rooms")
                room_names = [row[0] for row in cursor.fetchall()]
                self.roomComboBox.clear()
                self.roomComboBox.addItems(room_names)
            except Exception as e:
                self.statusbar.showMessage(f"회의실 목록 갱신 실패: {e}")

    def update_reservations(self):
        if self.db_conn and self.db_conn.is_connected():
            try:
                cursor = self.db_conn.cursor()
                cursor.execute("""
                    SELECT 
                        uid,
                        name,
                        company,
                        room_name,
                        start_time,
                        end_time,
                        auth_code,
                        reservation_status
                    FROM reservations
                    WHERE DATE(start_time) = %s
                """, (self.calendarView.selectedDate().toPyDate(),))
                reservations = cursor.fetchall()
                
                self.reservationTable.setColumnCount(8)
                self.reservationTable.setHorizontalHeaderLabels([
                    "UID", "이름", "회사", "회의실명", "시작 시간", "종료 시간",
                    "인증 번호", "상태"
                ])
                self.reservationTable.setRowCount(len(reservations))
                
                for row, (uid, name, company, room_name, start_dt, end_dt, auth_code, status) in enumerate(reservations):
                    self.reservationTable.setItem(row, 0, QTableWidgetItem(uid))
                    self.reservationTable.setItem(row, 1, QTableWidgetItem(name))
                    self.reservationTable.setItem(row, 2, QTableWidgetItem(company))
                    self.reservationTable.setItem(row, 3, QTableWidgetItem(room_name))
                    self.reservationTable.setItem(row, 4, QTableWidgetItem(start_dt.strftime('%Y-%m-%d %H:%M:%S')))
                    self.reservationTable.setItem(row, 5, QTableWidgetItem(end_dt.strftime('%Y-%m-%d %H:%M:%S')))
                    self.reservationTable.setItem(row, 6, QTableWidgetItem(auth_code or "N/A"))
                    self.reservationTable.setItem(row, 7, QTableWidgetItem(status))
            except Exception as e:
                self.statusbar.showMessage(f"예약 현황 갱신 실패: {e}")
        
        # 테이블의 컬럼 너비를 창에 맞게 자동으로 조절
        self.reservationTable.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

    def create_reservation(self):
        if self.user_role not in ["user", "admin"] or not self.db_conn or not self.db_conn.is_connected():
            QMessageBox.warning(self, "권한 없음", "예약 권한이 없습니다.")
            return

        try:
            selected_room_name = self.roomComboBox.currentText()
            
            start_date = self.startingDateInput.date().toPyDate()
            start_time = self.startingTimeInput.time().toPyTime()
            end_date = self.endingDateInput.date().toPyDate()
            end_time = self.endingTimeInput.time().toPyTime()

            start_datetime = datetime.combine(start_date, start_time)
            end_datetime = datetime.combine(end_date, end_time)

            if end_datetime <= start_datetime:
                QMessageBox.warning(self, "시간 오류", "종료 시간이 시작 시간보다 늦어야 합니다.")
                return

            cursor = self.db_conn.cursor()
            
            cursor.execute("""
                SELECT COUNT(*)
                FROM reservations
                WHERE room_name = %s
                AND NOT (end_time <= %s OR start_time >= %s)
            """, (selected_room_name, start_datetime, end_datetime))
            
            if cursor.fetchone()[0] > 0:
                QMessageBox.warning(self, "중복 예약", "선택한 시간대에 이미 예약이 있습니다.")
                return
            
            uid = self.userIDComboBox.currentText().strip()
            name_input = self.userNameInput.text().strip()
            if not uid or not name_input:
                QMessageBox.warning(self, "경고", "직원 코드와 이름을 모두 입력하세요.")
                return
            
            cursor.execute("SELECT name, company FROM users WHERE uid = %s AND name = %s", (uid, name_input))
            user_info_tuple = cursor.fetchone()

            if not user_info_tuple:
                QMessageBox.warning(self, "경고", "일치하는 사용자 정보가 없습니다. 직원 코드와 이름을 확인하세요.")
                return

            name, company = user_info_tuple
            
            auth_code = str(random.randint(1000, 9999))
            
            cursor.execute("""
                INSERT INTO reservations (uid, name, company, room_name, start_time, end_time, auth_code, reservation_status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, 'BOOKED')
            """, (uid, name, company, selected_room_name, start_datetime, end_datetime, auth_code))
            
            self.db_conn.commit()
            
            QMessageBox.information(self, "예약 생성 성공", 
                                    f"예약이 생성되었습니다.\n\n"
                                    f"회의실: {selected_room_name}\n"
                                    f"시간: {start_datetime.strftime('%Y-%m-%d %H:%M')} ~ {end_datetime.strftime('%Y-%m-%d %H:%M')}\n"
                                    f"인증 번호: {auth_code}")
            
            self.statusbar.showMessage("예약 생성 성공")
            self.update_reservations()
        except Exception as e:
            self.statusbar.showMessage(f"예약 생성 실패: {e}")
            QMessageBox.critical(self, "오류", f"예약 생성 실패: {e}")

    def edit_cancel_reservation(self):
        if self.user_role not in ["user", "admin"] or not self.db_conn or not self.db_conn.is_connected():
            QMessageBox.warning(self, "권한 없음", "예약 권한이 없습니다.")
            return

        selected_row = self.reservationTable.currentRow()
        if selected_row < 0:
            QMessageBox.warning(self, "경고", "예약 목록에서 취소할 예약을 선택하세요.")
            return

        res_uid = self.reservationTable.item(selected_row, 0).text()
        res_start_time_str = self.reservationTable.item(selected_row, 4).text()
        res_start_time = datetime.strptime(res_start_time_str, '%Y-%m-%d %H:%M:%S')

        if self.user_role == "admin" or res_uid == self.current_user_id:
            action = QMessageBox.question(self, "작업 선택", "선택한 예약을 취소할까요?",
                                          QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                          QMessageBox.StandardButton.No)
            if action == QMessageBox.StandardButton.Yes:
                try:
                    cursor = self.db_conn.cursor()
                    cursor.execute("""
                        UPDATE reservations SET reservation_status = 'CANCELED' 
                        WHERE uid = %s AND start_time = %s
                    """, (res_uid, res_start_time))
                    self.db_conn.commit()
                    self.statusbar.showMessage("예약 취소 성공")
                    self.update_reservations()
                except Exception as e:
                    self.statusbar.showMessage(f"예약 취소 실패: {e}")
                    QMessageBox.critical(self, "오류", f"예약 취소 실패: {e}")
        else:
            QMessageBox.warning(self, "권한 오류", "본인 예약 또는 관리자 권한이 필요합니다.")

    def closeEvent(self, event):
        if self.db_conn:
            self.db_conn.close()
        event.accept()

if __name__ == '__main__':
    from PyQt6.QtWidgets import QApplication
    app = QApplication(sys.argv)
    window = ReservationWindow(user_role="user", current_user_id="651ac301") 
    window.show()
    sys.exit(app.exec())
