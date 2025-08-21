from PyQt6.QtWidgets import QMainWindow, QMessageBox, QTableWidgetItem, QLineEdit
from PyQt6 import uic
from PyQt6.QtCore import QTimer, QDate, QTime, QLocale, QDateTime
import mysql.connector
from datetime import datetime

class ReservationWindow(QMainWindow):
    def __init__(self, user_role):
        super().__init__()
        uic.loadUi("reservation.ui", self)
        self.user_role = user_role
        self.db_conn = None
        self.rooms = {}
        self.connect_db()
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_reservations)
        self.timer.start(5000)

        self.startingDateInput.setCalendarPopup(True)
        self.startingDateInput.setLocale(QLocale(QLocale.Language.English, QLocale.Country.UnitedStates))
        self.startingDateInput.setDisplayFormat("yyyy-MM-dd")

        self.endingDateInput.setCalendarPopup(True)
        self.endingDateInput.setLocale(QLocale(QLocale.Language.English, QLocale.Country.UnitedStates))
        self.endingDateInput.setDisplayFormat("yyyy-MM-dd")

        self.createBtn.clicked.connect(self.create_reservation)
        self.editCancelBtn.clicked.connect(self.edit_cancel_reservation)
        self.calendarView.selectionChanged.connect(self.update_reservations)

        self.toggle_buttons()
        self.update_rooms()
        self.update_rooms_combobox()
        self.update_reservations()

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

    def toggle_buttons(self):
        self.createBtn.setEnabled(self.user_role in ["user", "admin"])
        self.editCancelBtn.setEnabled(self.user_role in ["user", "admin"])

    def update_rooms(self):
        if self.db_conn and self.db_conn.is_connected():
            try:
                cursor = self.db_conn.cursor()
                cursor.execute("SELECT room_id, room_name, capacity, location, equipment FROM rooms")
                rooms = cursor.fetchall()
                self.roomTable.setRowCount(len(rooms))
                for row, (room_id, name, capacity, location, equipment) in enumerate(rooms):
                    self.roomTable.setItem(row, 0, QTableWidgetItem(name))
                    self.roomTable.setItem(row, 1, QTableWidgetItem(str(capacity)))
                    self.roomTable.setItem(row, 2, QTableWidgetItem(location))
                    self.roomTable.setItem(row, 3, QTableWidgetItem(equipment))
                    self.rooms[name] = room_id
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
                self.statusbar.showMessage(f"회의실 콤보박스 갱신 실패: {e}")

    def update_reservations(self):
        if self.db_conn and self.db_conn.is_connected():
            try:
                cursor = self.db_conn.cursor()
                cursor.execute("""
                    SELECT reservation_id, room_name, start_datetime, end_datetime, user_id, user_name
                    FROM reservations
                    WHERE DATE(start_datetime) = %s
                """, (self.calendarView.selectedDate().toPyDate(),))
                reservations = cursor.fetchall()
                
                self.reservationTable.setColumnCount(6)
                self.reservationTable.setHorizontalHeaderLabels(["예약 ID", "회의실명", "시작 시간", "종료 시간", "예약자 ID", "예약자 이름"])
                self.reservationTable.setRowCount(len(reservations))
                
                for row, (res_id, room_name, start_dt, end_dt, user_id, user_name) in enumerate(reservations):
                    self.reservationTable.setItem(row, 0, QTableWidgetItem(str(res_id)))
                    self.reservationTable.setItem(row, 1, QTableWidgetItem(room_name))
                    self.reservationTable.setItem(row, 2, QTableWidgetItem(start_dt.strftime('%Y-%m-%d %H:%M:%S')))
                    self.reservationTable.setItem(row, 3, QTableWidgetItem(end_dt.strftime('%Y-%m-%d %H:%M:%S')))
                    self.reservationTable.setItem(row, 4, QTableWidgetItem(user_id))
                    self.reservationTable.setItem(row, 5, QTableWidgetItem(user_name or ""))
            except Exception as e:
                self.statusbar.showMessage(f"예약 현황 갱신 실패: {e}")
                print(f"Debug - update_reservations error: {e}")

    def create_reservation(self):
        if self.user_role in ["user", "admin"] and self.db_conn and self.db_conn.is_connected():
            try:
                selected_room_name = self.roomComboBox.currentText()
                start_date = self.startingDateInput.date().toPyDate()
                start_time = self.startingTimeInput.time().toPyTime()
                end_date = self.endingDateInput.date().toPyDate()
                end_time = self.endingTimeInput.time().toPyTime()

                user_id = self.userIDInput.text().strip()
                user_name = self.userNameInput.text().strip()

                if not user_id or not user_name:
                    QMessageBox.warning(self, "경고", "예약자 ID와 이름을 모두 입력해주세요.")
                    return
                
                # DATETIME 결합
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
                    AND (
                        (start_datetime < %s AND end_datetime > %s) OR
                        (start_datetime < %s AND end_datetime >= %s)
                    )
                """, (selected_room_name, end_datetime, start_datetime, end_datetime, start_datetime))
                if cursor.fetchone()[0] > 0:
                    QMessageBox.warning(self, "중복 예약", "선택한 시간대에 이미 예약이 있습니다.")
                    return

                cursor.execute("""
                    INSERT INTO reservations (user_id, user_name, room_name, start_datetime, end_datetime, status)
                    VALUES (%s, %s, %s, %s, %s, 'pending')
                """, (user_id, user_name, selected_room_name, start_datetime, end_datetime))
                self.db_conn.commit()
                self.statusbar.showMessage("예약 생성 성공")
                self.update_reservations()
            except Exception as e:
                self.statusbar.showMessage(f"예약 생성 실패: {e}")
                print(f"Debug - create_reservation error: {e}")
                QMessageBox.critical(self, "오류", f"예약 생성 실패: {e}")

    def edit_cancel_reservation(self):
        if self.user_role in ["user", "admin"] and self.db_conn and self.db_conn.is_connected():
            selected_row = self.reservationTable.currentRow()
            if selected_row >= 0:
                res_id = int(self.reservationTable.item(selected_row, 0).text())
                user_id = self.reservationTable.item(selected_row, 4).text()
                if self.user_role == "admin" or user_id == "user1":
                    action = QMessageBox.question(self, "작업 선택", "수정할까요, 취소할까요?", QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel)
                    if action == QMessageBox.Yes:
                        pass  # 수정 로직은 나중에 구현
                    elif action == QMessageBox.No:
                        cursor = self.db_conn.cursor()
                        cursor.execute("DELETE FROM reservations WHERE reservation_id = %s", (res_id,))
                        self.db_conn.commit()
                        self.statusbar.showMessage("예약 취소 성공")
                    self.update_reservations()
                else:
                    QMessageBox.warning(self, "권한 오류", "본인 예약 또는 관리자 권한이 필요합니다.")

    def closeEvent(self, event):
        if self.db_conn:
            self.db_conn.close()
        event.accept()