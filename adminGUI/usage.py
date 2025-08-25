#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
from PyQt6.QtWidgets import QMainWindow, QTableWidget, QTableWidgetItem, QHeaderView, QCalendarWidget
from PyQt6 import uic
from PyQt6.QtCore import QDate, QTimer
from PyQt6.QtGui import QColor
import mysql.connector
from datetime import datetime, timedelta, time

class UsageWindow(QMainWindow):
    def __init__(self, user_role):
        super().__init__()
        uic.loadUi("usage.ui", self)
        self.user_role = user_role
        
        # MySQL 데이터베이스 연결 정보
        self.db_conn = mysql.connector.connect(
            host="database-1.c1kkeqig4j9x.ap-northeast-2.rds.amazonaws.com",
            port=3306,
            user="root",
            password="12345678",
            database="joeffice"
        )
        
        self.calendarWidget.setSelectedDate(QDate.currentDate())
        self.calendarWidget.selectionChanged.connect(self.update_usage_table)
        
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_usage_table)
        self.timer.start(15000)
        
        self.update_usage_table()

    def update_usage_table(self):
        if not self.db_conn.is_connected():
            return
        
        cursor = self.db_conn.cursor()
        selected_date = self.calendarWidget.selectedDate().toPyDate()
        
        # ⬅️ **수정된 부분**: 시간대 변환 로직을 모두 제거합니다.
        # 선택된 날짜의 시작과 끝 시간을 정의합니다.
        start_of_day = datetime.combine(selected_date, time.min)
        end_of_day = datetime.combine(selected_date, time.max)

        # 현재 시간을 가져옵니다.
        current_time = datetime.now()

        # 시간 슬롯을 생성합니다.
        time_slots = [start_of_day + timedelta(hours=i) for i in range(24)]
        
        cursor.execute("SELECT room_name FROM rooms ORDER BY room_name")
        room_names = [row[0] for row in cursor.fetchall()]
        
        reservations = {}
        for room_name in room_names:
            # ⬅️ **수정된 부분**: UTC 변환 없이 DB를 조회합니다.
            cursor.execute("""
                SELECT start_time, end_time FROM reservations
                WHERE room_name = %s AND end_time >= %s AND start_time <= %s
                AND reservation_status IN ('BOOKED', 'CHECKED_IN')
            """, (room_name, start_of_day, end_of_day))
            
            # ⬅️ **수정된 부분**: KST 변환 없이 DB 데이터를 그대로 사용합니다.
            reservations[room_name] = list(cursor.fetchall())
        
        cursor.close()
        
        self.usageTable.setRowCount(len(room_names) * 2)
        self.usageTable.setColumnCount(12)
        
        am_header_labels = [ts.strftime("%H시") for ts in time_slots[:12]]
        pm_header_labels = [ts.strftime("%H시") for ts in time_slots[12:]]
        self.usageTable.setHorizontalHeaderLabels(am_header_labels + pm_header_labels)

        row = 0
        for i, room_name in enumerate(room_names):
            self.usageTable.setVerticalHeaderItem(row, QTableWidgetItem(f"{room_name} (00:00-12:00)"))
            for c_idx in range(12):
                time_slot = time_slots[c_idx]
                item = self.create_table_item(time_slot, reservations.get(room_name, []), current_time)
                self.usageTable.setItem(row, c_idx, item)
            row += 1

            self.usageTable.setVerticalHeaderItem(row, QTableWidgetItem(f"{room_name} (12:00-24:00)"))
            for c_idx in range(12):
                time_slot = time_slots[12 + c_idx]
                item = self.create_table_item(time_slot, reservations.get(room_name, []), current_time)
                self.usageTable.setItem(row, c_idx, item)
            row += 1

        self.usageTable.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.usageTable.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

    def create_table_item(self, time_slot, res_list, current_time):
        start_of_hour = time_slot
        end_of_hour = time_slot + timedelta(hours=1)

        booked_reservations = [
            res for res in res_list if res[0] < end_of_hour and res[1] > start_of_hour
        ]
        
        item = QTableWidgetItem("")
        
        if booked_reservations:
            display_text = "\n".join(
                [f"{start.strftime('%H:%M')}-{end.strftime('%H:%M')}" for start, end in booked_reservations]
            )
            item.setText(display_text)
            item.setBackground(QColor(255, 165, 0))
        elif start_of_hour < current_time:
            item.setBackground(QColor(255, 255, 255))
            item.setText("")
        else:
            item.setText("예약 가능")
            item.setBackground(QColor(0, 255, 0))
        
        return item

    def closeEvent(self, event):
        self.timer.stop()
        if self.db_conn.is_connected():
            self.db_conn.close()
        event.accept()

if __name__ == "__main__":
    from PyQt6.QtWidgets import QApplication
    app = QApplication(sys.argv)
    window = UsageWindow(user_role="user")
    window.show()
    sys.exit(app.exec())