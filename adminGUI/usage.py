#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
from PyQt6.QtWidgets import QMainWindow, QMessageBox, QTableWidget, QTableWidgetItem, QHeaderView
from PyQt6.QtGui import QColor
from PyQt6 import uic
from PyQt6.QtCore import QTimer, QTime, QDate
import mysql.connector
from datetime import datetime, timedelta

class UsageWindow(QMainWindow):
    def __init__(self, user_role):
        super().__init__()
        try:
            uic.loadUi("usage.ui", self)
        except FileNotFoundError:
            QMessageBox.critical(self, "오류", "usage.ui 파일을 찾을 수 없습니다.")
            sys.exit(1)

        self.user_role = user_role
        self.db_conn = None
        self.connect_db()

        self.update_usage_table()

        # 15초마다 테이블을 자동으로 갱신하는 타이머
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_usage_table)
        self.timer.start(15000)

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

    def update_usage_table(self):
        if not self.db_conn or not self.db_conn.is_connected():
            return
        
        try:
            # 1. 앞으로 6시간 동안의 시간대(슬롯) 생성 (1시간 단위)
            now = datetime.now().replace(minute=0, second=0, microsecond=0)
            time_slots = [now + timedelta(hours=i) for i in range(7)]
            
            # 2. 모든 회의실 정보 조회
            cursor = self.db_conn.cursor()
            cursor.execute("SELECT room_name FROM rooms ORDER BY room_name")
            room_names = [row[0] for row in cursor.fetchall()]
            
            # 3. 모든 회의실의 예약 현황 조회
            reservations = {}
            for room_name in room_names:
                cursor.execute("""
                    SELECT start_time, end_time FROM reservations
                    WHERE room_name = %s
                    AND end_time >= %s AND start_time <= %s
                    AND reservation_status IN ('BOOKED', 'CHECKED_IN')
                """, (room_name, now, now + timedelta(hours=6)))
                reservations[room_name] = cursor.fetchall()
            
            cursor.close()

            # 4. QTableWidget 업데이트
            self.usageTable.setRowCount(len(room_names))
            self.usageTable.setColumnCount(len(time_slots))
            
            # 헤더 설정
            header_labels = [ts.strftime("%H시") for ts in time_slots]
            self.usageTable.setHorizontalHeaderLabels(header_labels)
            self.usageTable.setVerticalHeaderLabels(room_names)

            for r_idx, room_name in enumerate(room_names):
                for c_idx, time_slot in enumerate(time_slots):
                    is_booked = False
                    end_time_str = ""
                    for start_dt, end_dt in reservations.get(room_name, []):
                        if start_dt <= time_slot < end_dt:
                            is_booked = True
                            end_time_str = end_dt.strftime("%H:%M")
                            break
                    
                    item = QTableWidgetItem(end_time_str if is_booked else "예약가능")
                    if is_booked:
                        item.setBackground(QColor(255, 182, 193)) # 연한 빨강
                    else:
                        item.setBackground(QColor(144, 238, 144)) # 연한 초록
                    
                    self.usageTable.setItem(r_idx, c_idx, item)
            
            self.usageTable.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
            self.usageTable.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)

        except Exception as e:
            self.statusbar.showMessage(f"예약 현황 갱신 실패: {e}")
            QMessageBox.critical(self, "오류", f"예약 현황 갱신 중 오류 발생: {e}")
            

    def closeEvent(self, event):
        self.timer.stop()
        if self.db_conn:
            self.db_conn.close()
        event.accept()

if __name__ == "__main__":
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtGui import QColor
    app = QApplication(sys.argv)
    window = UsageWindow(user_role="user")
    window.show()
    sys.exit(app.exec())