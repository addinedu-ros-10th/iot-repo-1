#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
from PyQt6.QtWidgets import QMainWindow, QMessageBox
from PyQt6 import uic
from PyQt6.QtCore import QTimer
import mysql.connector
from datetime import datetime

# 다른 창 클래스 임포트
from extra import ExtraWindow
from reservation import ReservationWindow
from usage import UsageWindow
from reservation_check import ReservationCheckWindow

class HomeWindow(QMainWindow):
    def __init__(self, user_role, parent=None):
        super().__init__(parent)
        uic.loadUi("home.ui", self)
        self.user_role = user_role
        self.welcomeLabel.setText(f"환영합니다! (권한: {self.user_role})")
        
        self.db_conn = None
        self.connect_db()

        # 버튼 연결
        self.reservationBtn.clicked.connect(self.open_reservation)
        self.usageBtn.clicked.connect(self.open_usage)
        self.extraBtn.clicked.connect(self.open_extra)
        self.checkReservationBtn.clicked.connect(self.open_reservation_check)

        # 60초마다 예약 상태를 자동으로 업데이트
        self.status_timer = QTimer()
        self.status_timer.timeout.connect(self.update_reservation_statuses)
        self.status_timer.start(2000)

        self.toggle_buttons()

    def connect_db(self):
        """데이터베이스에 연결합니다."""
        try:
            self.db_conn = mysql.connector.connect(
                host="database-1.c1kkeqig4j9x.ap-northeast-2.rds.amazonaws.com",
                port=3306,
                user="root",
                password="12345678",
                database="joeffice"
            )
            # self.statusBar().showMessage("DB 연결 성공")
        except mysql.connector.Error as err:
            QMessageBox.critical(self, "오류", f"데이터베이스 연결 실패: {err}")
            sys.exit(1)

    def update_reservation_statuses(self):
        """예약 시간이 지난 예약을 'CHECKED_OUT' 상태로 자동 변경합니다."""
        if self.db_conn and self.db_conn.is_connected():
            try:
                cursor = self.db_conn.cursor()
                now = datetime.now()
                
                cursor.execute("""
                    UPDATE reservations
                    SET reservation_status = 'CHECKED_OUT', updated_at = %s
                    WHERE end_time <= %s AND reservation_status IN ('BOOKED', 'CHECKED_IN')
                """, (now, now))
                
                if cursor.rowcount > 0:
                    self.db_conn.commit()
                    print(f"자동 상태 업데이트: {cursor.rowcount}개의 예약 상태가 CHECKED_OUT으로 변경되었습니다.")
                
            except Exception as e:
                print(f"자동 상태 업데이트 실패: {e}")

    def toggle_buttons(self):
        self.reservationBtn.setVisible(True)
        self.usageBtn.setVisible(True)
        self.extraBtn.setVisible(False)
        self.checkReservationBtn.setVisible(True)

        if self.user_role == "admin":
            self.reservationBtn.setVisible(True)
            self.extraBtn.setVisible(True)
        elif self.user_role == "user":
            self.reservationBtn.setVisible(False)
            self.extraBtn.setVisible(False)

    def open_reservation(self):
        self.reservation_window = ReservationWindow(self.user_role)
        self.reservation_window.show()

    def open_usage(self):
        self.usage_window = UsageWindow(self.user_role)
        self.usage_window.show()

    def open_extra(self):
        self.extra_window = ExtraWindow(self.user_role)
        self.extra_window.show()

    def open_reservation_check(self):
        """예약 인증 창을 엽니다."""
        self.reservation_check_window = ReservationCheckWindow()
        self.reservation_check_window.show()

    def closeEvent(self, event):
        self.status_timer.stop()
        if self.db_conn and self.db_conn.is_connected():
            self.db_conn.close()
        if self.parent():
            self.parent().show()
        event.accept()

if __name__ == "__main__":
    from PyQt6.QtWidgets import QApplication
    app = QApplication(sys.argv)
    window = HomeWindow(user_role="user")
    window.show()
    sys.exit(app.exec())