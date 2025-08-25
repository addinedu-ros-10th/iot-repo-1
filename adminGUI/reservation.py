#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
from PyQt6.QtWidgets import (QMainWindow, QMessageBox, QTableWidgetItem, 
                             QAbstractItemView, QHeaderView, QApplication, QPushButton)
from PyQt6 import uic
from PyQt6.QtCore import QTimer, QDate, QTime, QLocale
import mysql.connector
from datetime import datetime, timedelta # timedelta 추가
import random
from functools import partial # 버튼 클릭에 인자를 전달하기 위함

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

        # 현재 로컬 시간으로 초기값 설정
        now = datetime.now()
        one_hour_later = now + timedelta(hours=1)
        
        self.startingDateInput.setCalendarPopup(True)
        self.startingDateInput.setLocale(QLocale(QLocale.Language.English, QLocale.Country.UnitedStates))
        self.startingDateInput.setDisplayFormat("yyyy-MM-dd")
        self.startingDateInput.setDate(QDate(now.year, now.month, now.day))
        self.startingTimeInput.setTime(QTime(now.hour, now.minute, 0))
        
        self.endingDateInput.setCalendarPopup(True)
        self.endingDateInput.setLocale(QLocale(QLocale.Language.English, QLocale.Country.UnitedStates))
        self.endingDateInput.setDisplayFormat("yyyy-MM-dd")
        self.endingDateInput.setDate(QDate(one_hour_later.year, one_hour_later.month, one_hour_later.day))
        self.endingTimeInput.setTime(QTime(one_hour_later.hour, one_hour_later.minute, 0))
        
        self.reservationTable.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.reservationTable.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.reservationTable.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)

        self.createBtn.clicked.connect(self.create_reservation)
        self.editCancelBtn.clicked.connect(self.cancel_reservation)
        self.calendarView.selectionChanged.connect(self.update_reservations)

        self.timer = QTimer()
        self.timer.timeout.connect(self.update_reservations)
        self.timer.start(5000)

        self.toggle_buttons()
        self.load_users()
        self.update_rooms()
        self.update_rooms_combobox()
        self.load_users_to_combobox()
        self.update_reservations()
        
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
            except Exception as e:
                self.statusbar.showMessage(f"사용자 콤보박스 갱신 실패: {e}")

    def update_user_name_from_combobox(self):
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
                self.roomTable.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
            except Exception as e:
                self.statusbar.showMessage(f"회의실 목록 갱신 실패: {e}")

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
                selected_date = self.calendarView.selectedDate().toPyDate()
                
                # DB의 CONVERT_TZ 함수를 사용하여 KST 기준으로 날짜 필터링
                cursor.execute("""
                    SELECT uid, name, company, room_name, start_time, end_time, auth_code, reservation_status
                    FROM reservations WHERE DATE(CONVERT_TZ(start_time, 'UTC', 'Asia/Seoul')) = %s
                """, (selected_date,))
                reservations = cursor.fetchall()
                
                self.reservationTable.setColumnCount(9) # 양보 요청 버튼을 위해 컬럼 추가
                self.reservationTable.setHorizontalHeaderLabels([
                    "UID", "이름", "회사", "회의실명", "시작 시간", "종료 시간",
                    "인증 번호", "상태", "요청"
                ])
                self.reservationTable.setRowCount(len(reservations))
                
                kst_offset = timedelta(hours=9)
                
                for row, (uid, name, company, room_name, start_dt_utc, end_dt_utc, auth_code, status) in enumerate(reservations):
                    # UTC 시간을 KST로 변환
                    start_dt_kst = start_dt_utc + kst_offset
                    end_dt_kst = end_dt_utc + kst_offset
                    
                    self.reservationTable.setItem(row, 0, QTableWidgetItem(uid))
                    self.reservationTable.setItem(row, 1, QTableWidgetItem(name))
                    self.reservationTable.setItem(row, 2, QTableWidgetItem(company))
                    self.reservationTable.setItem(row, 3, QTableWidgetItem(room_name))
                    self.reservationTable.setItem(row, 4, QTableWidgetItem(start_dt_kst.strftime('%Y-%m-%d %H:%M:%S')))
                    self.reservationTable.setItem(row, 5, QTableWidgetItem(end_dt_kst.strftime('%Y-%m-%d %H:%M:%S')))
                    self.reservationTable.setItem(row, 6, QTableWidgetItem(auth_code or "N/A"))
                    self.reservationTable.setItem(row, 7, QTableWidgetItem(status))

                    # 양보 요청 버튼 추가
                    yield_button = QPushButton("양보 요청", self)
                    if uid == self.current_user_id or status != 'BOOKED':
                        yield_button.setEnabled(False) # 자신의 예약이나 지난 예약은 비활성화
                    else:
                        yield_button.clicked.connect(partial(self.request_yield, uid, name, room_name, start_dt_kst))
                    
                    self.reservationTable.setCellWidget(row, 8, yield_button)

                self.reservationTable.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
            except Exception as e:
                self.statusbar.showMessage(f"예약 현황 갱신 실패: {e}")

    def create_reservation(self):
        if self.user_role not in ["user", "admin"]:
            QMessageBox.warning(self, "권한 없음", "예약 권한이 없습니다.")
            return

        try:
            selected_room_name = self.roomComboBox.currentText()
            
            start_datetime_naive = datetime.combine(self.startingDateInput.date().toPyDate(), self.startingTimeInput.time().toPyTime())
            end_datetime_naive = datetime.combine(self.endingDateInput.date().toPyDate(), self.endingTimeInput.time().toPyTime())

            # KST(naive)를 UTC(naive)로 변환하여 DB에 저장
            kst_offset = timedelta(hours=9)
            start_datetime_utc = start_datetime_naive - kst_offset
            end_datetime_utc = end_datetime_naive - kst_offset

            if end_datetime_utc <= start_datetime_utc:
                QMessageBox.warning(self, "시간 오류", "종료 시간이 시작 시간보다 늦어야 합니다.")
                return

            cursor = self.db_conn.cursor()
            cursor.execute("""
                SELECT COUNT(*) FROM reservations WHERE room_name = %s AND NOT (end_time <= %s OR start_time >= %s)
                AND reservation_status IN ('BOOKED', 'CHECKED_IN')
            """, (selected_room_name, start_datetime_utc, end_datetime_utc))
            
            if cursor.fetchone()[0] > 0:
                QMessageBox.warning(self, "중복 예약", "선택한 시간대에 이미 예약이 있습니다.")
                return
            
            uid = self.userIDComboBox.currentText().strip()
            name_input = self.userNameInput.text().strip()
            if not uid or not name_input:
                QMessageBox.warning(self, "경고", "직원 코드와 이름을 모두 입력하세요.")
                return
            
            user_info = self.users.get(uid)
            if not user_info or user_info['name'] != name_input:
                QMessageBox.warning(self, "경고", "일치하는 사용자 정보가 없습니다.")
                return

            name, company = user_info['name'], user_info['company']
            auth_code = str(random.randint(1000, 9999))
            
            cursor.execute("""
                INSERT INTO reservations (uid, name, company, room_name, start_time, end_time, auth_code, reservation_status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, 'BOOKED')
            """, (uid, name, company, selected_room_name, start_datetime_utc, end_datetime_utc, auth_code))
            
            self.db_conn.commit()
            QMessageBox.information(self, "예약 성공", f"예약이 완료되었습니다.\n인증 번호: {auth_code}")
            self.update_reservations()
        except Exception as e:
            QMessageBox.critical(self, "오류", f"예약 생성 실패: {e}")

    def cancel_reservation(self):
        selected_row = self.reservationTable.currentRow()
        if selected_row < 0:
            QMessageBox.warning(self, "경고", "취소할 예약을 선택하세요.")
            return

        res_uid = self.reservationTable.item(selected_row, 0).text()
        start_time_str_kst = self.reservationTable.item(selected_row, 4).text()
        
        # KST 문자열을 naive datetime 객체로 변환 후 UTC로 변환
        start_time_naive_kst = datetime.strptime(start_time_str_kst, '%Y-%m-%d %H:%M:%S')
        start_time_utc = start_time_naive_kst - timedelta(hours=9)

        if self.user_role == "admin" or res_uid == self.current_user_id:
            reply = QMessageBox.question(self, "예약 취소", "선택한 예약을 취소하시겠습니까?",
                                          QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.Yes:
                try:
                    cursor = self.db_conn.cursor()
                    cursor.execute("""
                        UPDATE reservations SET reservation_status = 'CANCELED' 
                        WHERE uid = %s AND start_time = %s
                    """, (res_uid, start_time_utc))
                    self.db_conn.commit()
                    self.update_reservations()
                except Exception as e:
                    QMessageBox.critical(self, "오류", f"예약 취소 실패: {e}")
        else:
            QMessageBox.warning(self, "권한 오류", "본인의 예약만 취소할 수 있습니다.")

    def request_yield(self, target_uid, target_name, room_name, start_time):
        """ '양보 요청하기' 버튼 클릭 시 호출되는 함수 """
        reply = QMessageBox.question(self, '양보 요청',
                                     f"<b>{target_name}</b>님에게 <b>{room_name}</b>({start_time.strftime('%H:%M')} 시작) 예약에 대한\n"
                                     f"양보를 요청하시겠습니까?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)

        if reply == QMessageBox.StandardButton.Yes:
            # 실제 구현에서는 이 부분에 알림 전송 로직이 들어갑니다.
            print(f"요청 전송: {target_uid} 사용자에게 양보를 요청했습니다.")
            QMessageBox.information(self, "요청 완료", "양보 요청이 전송되었습니다.")

    def closeEvent(self, event):
        if self.db_conn:
            self.db_conn.close()
        event.accept()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    # user_role은 로그인 시스템 등에서 받아와야 합니다.
    window = ReservationWindow(user_role="user", current_user_id="651ac301") 
    window.show()
    sys.exit(app.exec())
