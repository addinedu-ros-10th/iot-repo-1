#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
from PyQt6.QtWidgets import QMainWindow
from PyQt6 import uic
from extra import ExtraWindow
from integration import IntegrationWindow
from reservation import ReservationWindow
from usage import UsageWindow
from reservation_check import ReservationCheckWindow # 예약 인증 모듈 임포트

class HomeWindow(QMainWindow):
    def __init__(self, user_role, parent=None):
        super().__init__(parent)
        uic.loadUi("home.ui", self)
        self.user_role = user_role
        self.welcomeLabel.setText(f"환영합니다! (권한: {self.user_role})")

        # 버튼 연결
        self.reservationBtn.clicked.connect(self.open_reservation)
        self.usageBtn.clicked.connect(self.open_usage)
        self.extraBtn.clicked.connect(self.open_extra)
        self.integrationBtn.clicked.connect(self.open_integration)
        self.checkReservationBtn.clicked.connect(self.open_reservation_check) # 새로운 버튼 연결

        self.toggle_buttons()

    def toggle_buttons(self):
        self.reservationBtn.setEnabled(True)
        self.usageBtn.setEnabled(True)
        self.extraBtn.setEnabled(self.user_role in ["user", "admin"])
        self.integrationBtn.setEnabled(self.user_role == "admin")
        self.checkReservationBtn.setEnabled(True) # 예약 인증은 모든 사용자가 가능

    def open_reservation(self):
        self.reservation_window = ReservationWindow(self.user_role)
        self.reservation_window.show()

    def open_usage(self):
        self.usage_window = UsageWindow(self.user_role)
        self.usage_window.show()

    def open_extra(self):
        self.extra_window = ExtraWindow(self.user_role)
        self.extra_window.show()

    def open_integration(self):
        self.integration_window = IntegrationWindow(self.user_role)
        self.integration_window.show()

    def open_reservation_check(self):
        """예약 인증 창을 엽니다."""
        self.reservation_check_window = ReservationCheckWindow()
        self.reservation_check_window.show()

    def closeEvent(self, event):
        if self.parent():
            self.parent().show()
        event.accept()

if __name__ == "__main__":
    from PyQt6.QtWidgets import QApplication
    app = QApplication(sys.argv)
    # 테스트용 HomeWindow. 실제로는 AuthWindow에서 생성되어야 합니다.
    window = HomeWindow(user_role="user")
    window.show()
    sys.exit(app.exec())
