#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
from PyQt6.QtWidgets import (QMainWindow, QMessageBox, QTableWidgetItem, QLineEdit, 
                             QAbstractItemView, QComboBox, QHeaderView, QPushButton, 
                             QHBoxLayout, QWidget, QVBoxLayout) # QVBoxLayout 임포트 추가
from PyQt6 import uic
from PyQt6.QtCore import QTimer, QDate, QTime, QLocale, QDateTime
import mysql.connector
from datetime import datetime, timedelta
import random
import pytz # 시간대 처리를 위한 라이브러리

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

        # --- 시간대 객체 정의 ---
        self.KST = pytz.timezone('Asia/Seoul')
        self.UTC = pytz.utc

        self.connect_db()

        # 현재 시간(KST)으로 초기값 설정
        now_kst = datetime.now(self.KST)
        one_hour_later = now_kst + timedelta(hours=1)
        
        # 시작 날짜/시간 설정
        self.startingDateInput.setCalendarPopup(True)
        self.startingDateInput.setLocale(QLocale(QLocale.Language.English, QLocale.Country.UnitedStates))
        self.startingDateInput.setDisplayFormat("yyyy-MM-dd")
        self.startingDateInput.setDate(QDate(now_kst.year, now_kst.month, now_kst.day))
        self.startingTimeInput.setTime(QTime(now_kst.hour, now_kst.minute, 0))
        
        # 종료 날짜/시간 설정
        self.endingDateInput.setCalendarPopup(True)
        self.endingDateInput.setLocale(QLocale(QLocale.Language.English, QLocale.Country.UnitedStates))
        self.endingDateInput.setDisplayFormat("yyyy-MM-dd")
        self.endingDateInput.setDate(QDate(one_hour_later.year, one_hour_later.month, one_hour_later.day))
        self.endingTimeInput.setTime(QTime(one_hour_later.hour, one_hour_later.minute, 0))
        
        self.reservationTable.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.reservationTable.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.reservationTable.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)

        # --- 양보 요청 버튼 동적 생성 및 시그널 연결 ---
        self.setup_extra_buttons()

        # --- 기존 시그널 연결 ---
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
        self.load_users_to_combobox()
        self.update_reservations()
        
        self.userIDComboBox.currentIndexChanged.connect(self.update_user_name_from_combobox)

    def setup_extra_buttons(self):
        """양보 요청 버튼을 생성하고 기존 레이아웃에 추가"""
        self.requestConcessionBtn = QPushButton("양보 요청하기")
        self.requestConcessionBtn.setEnabled(False)
        self.requestConcessionBtn.clicked.connect(self.request_concession)
        
        # createBtn이 포함된 레이아웃을 찾아서 새 버튼 추가
        if self.createBtn.parentWidget() and self.createBtn.parentWidget().layout():
            layout = self.createBtn.parentWidget().layout()
            # QHBoxLayout 또는 QVBoxLayout인지 확인
            if isinstance(layout, (QHBoxLayout, QVBoxLayout)):
                layout.addWidget(self.requestConcessionBtn)

    def connect_db(self):
        try:
            self.db_conn = mysql.connector.connect(
                host="database-1.c1kkeqig4j9x.ap-northeast-2.rds.amazonaws.com",
                port=3306,
                user="root",
                password="12345678",
                database="joeffice"
            )
            self.statusBar().showMessage("DB 연결 성공")
        except mysql.connector.Error as err:
            self.statusBar().showMessage(f"DB 연결 실패: {err}")
            QMessageBox.critical(self, "오류", f"데이터베이스 연결 실패: {err}")
            sys.exit(1)

    def load_users(self):
        self.users = {}
        if self.db_conn and self.db_conn.is_connected():
            try:
                cursor = self.db_conn.cursor(dictionary=True)
                cursor.execute("SELECT uid, name, company FROM users")
                for row in cursor.fetchall():
                    self.users[row['uid']] = {'name': row['name'], 'company': row['company']}
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
                self.statusBar().showMessage(f"사용자 콤보박스 갱신 실패: {e}")

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
                self.statusBar().showMessage(f"회의실 목록 갱신 실패: {e}")

    def update_rooms_combobox(self):
        if self.db_conn and self.db_conn.is_connected():
            try:
                cursor = self.db_conn.cursor()
                cursor.execute("SELECT room_name FROM rooms")
                room_names = [row[0] for row in cursor.fetchall()]
                self.roomComboBox.clear()
                self.roomComboBox.addItems(room_names)
            except Exception as e:
                self.statusBar().showMessage(f"회의실 목록 갱신 실패: {e}")

    def update_reservations(self):
        if self.db_conn and self.db_conn.is_connected():
            try:
                cursor = self.db_conn.cursor(dictionary=True)
                selected_date_kst = self.calendarView.selectedDate().toPyDate()
                start_of_day_kst = self.KST.localize(datetime.combine(selected_date_kst, datetime.min.time()))
                end_of_day_kst = self.KST.localize(datetime.combine(selected_date_kst, datetime.max.time()))
                
                start_of_day_utc = start_of_day_kst.astimezone(self.UTC)
                end_of_day_utc = end_of_day_kst.astimezone(self.UTC)

                cursor.execute("""
                    SELECT uid, name, company, room_name, start_time, end_time, auth_code, reservation_status
                    FROM reservations
                    WHERE start_time >= %s AND start_time <= %s
                """, (start_of_day_utc, end_of_day_utc))
                reservations = cursor.fetchall()
                
                self.reservationTable.setColumnCount(8)
                self.reservationTable.setHorizontalHeaderLabels(["UID", "이름", "회사", "회의실명", "시작 시간", "종료 시간", "인증 번호", "상태"])
                self.reservationTable.setRowCount(len(reservations))
                
                for row, res in enumerate(reservations):
                    start_time_kst = res['start_time'].replace(tzinfo=self.UTC).astimezone(self.KST)
                    end_time_kst = res['end_time'].replace(tzinfo=self.UTC).astimezone(self.KST)

                    self.reservationTable.setItem(row, 0, QTableWidgetItem(res['uid']))
                    self.reservationTable.setItem(row, 1, QTableWidgetItem(res['name']))
                    self.reservationTable.setItem(row, 2, QTableWidgetItem(res['company']))
                    self.reservationTable.setItem(row, 3, QTableWidgetItem(res['room_name']))
                    self.reservationTable.setItem(row, 4, QTableWidgetItem(start_time_kst.strftime('%Y-%m-%d %H:%M:%S')))
                    self.reservationTable.setItem(row, 5, QTableWidgetItem(end_time_kst.strftime('%Y-%m-%d %H:%M:%S')))
                    self.reservationTable.setItem(row, 6, QTableWidgetItem(res['auth_code'] or "N/A"))
                    self.reservationTable.setItem(row, 7, QTableWidgetItem(res['reservation_status']))
                self.reservationTable.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
            except Exception as e:
                self.statusBar().showMessage(f"예약 현황 갱신 실패: {e}")

    def create_reservation(self):
        if self.user_role not in ["user", "admin"]:
            QMessageBox.warning(self, "권한 없음", "예약 권한이 없습니다.")
            return

        # 양보 요청 버튼은 예약 시도 시 항상 비활성화
        self.requestConcessionBtn.setEnabled(False)

        try:
            selected_room_name = self.roomComboBox.currentText()
            
            start_datetime_naive = datetime.combine(self.startingDateInput.date().toPyDate(), self.startingTimeInput.time().toPyTime())
            end_datetime_naive = datetime.combine(self.endingDateInput.date().toPyDate(), self.endingTimeInput.time().toPyTime())

            start_datetime_kst = self.KST.localize(start_datetime_naive)
            end_datetime_kst = self.KST.localize(end_datetime_naive)
            start_datetime_utc = start_datetime_kst.astimezone(self.UTC)
            end_datetime_utc = end_datetime_kst.astimezone(self.UTC)

            if end_datetime_utc <= start_datetime_utc:
                QMessageBox.warning(self, "시간 오류", "종료 시간이 시작 시간보다 늦어야 합니다.")
                return

            cursor = self.db_conn.cursor()
            
            # --- 모든 주요 회의실이 찼는지 확인 ---
            main_rooms = ('회의실 A', '회의실 B', '회의실 C')
            cursor.execute(f"""
                SELECT COUNT(DISTINCT room_name) FROM reservations
                WHERE room_name IN {main_rooms}
                AND NOT (end_time <= %s OR start_time >= %s)
                AND reservation_status IN ('BOOKED', 'CHECKED_IN')
            """, (start_datetime_utc, end_datetime_utc))
            
            if cursor.fetchone()[0] >= len(main_rooms):
                QMessageBox.information(self, "예약 불가", "모든 회의실(A, B, C)이 해당 시간에 예약되어 있습니다. 양보 요청을 시도할 수 있습니다.")
                self.requestConcessionBtn.setEnabled(True) # 양보 요청 버튼 활성화
                return

            # --- 기존 예약 로직 (선택한 회의실이 비었는지 확인) ---
            cursor.execute("""
                SELECT COUNT(*) FROM reservations
                WHERE room_name = %s AND NOT (end_time <= %s OR start_time >= %s)
                AND reservation_status IN ('BOOKED', 'CHECKED_IN')
            """, (selected_room_name, start_datetime_utc, end_datetime_utc))
            
            if cursor.fetchone()[0] > 0:
                QMessageBox.warning(self, "중복 예약", f"'{selected_room_name}'은(는) 선택한 시간대에 이미 예약이 있습니다.")
                return
            
            uid = self.userIDComboBox.currentText().strip()
            name = self.userNameInput.text().strip()
            company = self.users.get(uid, {}).get('company', '')

            if not uid or not name:
                QMessageBox.warning(self, "경고", "직원 코드와 이름을 모두 입력하세요.")
                return
            
            auth_code = str(random.randint(1000, 9999))
            
            cursor.execute("""
                INSERT INTO reservations (uid, name, company, room_name, start_time, end_time, auth_code, reservation_status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, 'BOOKED')
            """, (uid, name, company, selected_room_name, start_datetime_utc, end_datetime_utc, auth_code))
            
            self.db_conn.commit()
            
            QMessageBox.information(self, "예약 생성 성공", 
                                    f"예약이 생성되었습니다.\n\n"
                                    f"회의실: {selected_room_name}\n"
                                    f"시간: {start_datetime_kst.strftime('%Y-%m-%d %H:%M')} ~ {end_datetime_kst.strftime('%Y-%m-%d %H:%M')}\n"
                                    f"인증 번호: {auth_code}")
            
            self.statusBar().showMessage("예약 생성 성공")
            self.update_reservations()
        except Exception as e:
            self.statusBar().showMessage(f"예약 생성 실패: {e}")
            QMessageBox.critical(self, "오류", f"예약 생성 실패: {e}")

    def request_concession(self):
        """현재 선택된 시간에 예약된 사용자들에게 양보를 요청하는 시뮬레이션"""
        try:
            start_datetime_naive = datetime.combine(self.startingDateInput.date().toPyDate(), self.startingTimeInput.time().toPyTime())
            end_datetime_naive = datetime.combine(self.endingDateInput.date().toPyDate(), self.endingTimeInput.time().toPyTime())
            start_datetime_utc = self.KST.localize(start_datetime_naive).astimezone(self.UTC)
            end_datetime_utc = self.KST.localize(end_datetime_naive).astimezone(self.UTC)

            cursor = self.db_conn.cursor(dictionary=True)
            main_rooms = ('회의실 A', '회의실 B', '회의실 C')
            cursor.execute(f"""
                SELECT room_name, name FROM reservations
                WHERE room_name IN {main_rooms}
                AND NOT (end_time <= %s OR start_time >= %s)
                AND reservation_status IN ('BOOKED', 'CHECKED_IN')
            """, (start_datetime_utc, end_datetime_utc))
            
            occupants = cursor.fetchall()
            if not occupants:
                QMessageBox.information(self, "정보", "요청할 대상 예약이 없습니다.")
                return

            message = "다음 예약자에게 양보 요청 메시지를 보내시겠습니까?\n\n"
            for occupant in occupants:
                message += f"- {occupant['room_name']}: {occupant['name']}\n"

            reply = QMessageBox.question(self, "양보 요청 확인", message,
                                         QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                         QMessageBox.StandardButton.No)

            if reply == QMessageBox.StandardButton.Yes:
                # 실제로는 이 부분에서 알림(이메일, 슬랙 등) 로직이 실행됩니다.
                # 여기서는 시뮬레이션으로 메시지만 표시합니다.
                QMessageBox.information(self, "요청 전송 완료", "양보 요청이 전송되었습니다.")
                self.requestConcessionBtn.setEnabled(False)

        except Exception as e:
            QMessageBox.critical(self, "오류", f"양보 요청 중 오류 발생: {e}")

    def edit_cancel_reservation(self):
        if self.user_role not in ["user", "admin"]:
            QMessageBox.warning(self, "권한 없음", "예약 권한이 없습니다.")
            return

        selected_row = self.reservationTable.currentRow()
        if selected_row < 0:
            QMessageBox.warning(self, "경고", "취소할 예약을 선택하세요.")
            return

        res_uid = self.reservationTable.item(selected_row, 0).text()
        res_start_time_str = self.reservationTable.item(selected_row, 4).text()
        
        start_time_kst_naive = datetime.strptime(res_start_time_str, '%Y-%m-%d %H:%M:%S')
        start_time_kst = self.KST.localize(start_time_kst_naive)
        start_time_utc = start_time_kst.astimezone(self.UTC)

        if self.user_role == "admin" or res_uid == self.current_user_id:
            action = QMessageBox.question(self, "작업 선택", "선택한 예약을 취소하시겠습니까?",
                                          QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                          QMessageBox.StandardButton.No)
            if action == QMessageBox.StandardButton.Yes:
                try:
                    cursor = self.db_conn.cursor()
                    cursor.execute("""
                        UPDATE reservations SET reservation_status = 'CANCELED' 
                        WHERE uid = %s AND start_time = %s
                    """, (res_uid, start_time_utc))
                    self.db_conn.commit()
                    self.statusBar().showMessage("예약 취소 성공")
                    self.update_reservations()
                except Exception as e:
                    self.statusBar().showMessage(f"예약 취소 실패: {e}")
        else:
            QMessageBox.warning(self, "권한 오류", "본인의 예약만 취소할 수 있습니다.")

    def closeEvent(self, event):
        if self.db_conn:
            self.db_conn.close()
        event.accept()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = ReservationWindow(user_role="user", current_user_id="651ac301") 
    window.show()
    sys.exit(app.exec())
