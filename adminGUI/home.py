from PyQt6.QtWidgets import QMainWindow
from PyQt6 import uic
from extra import ExtraWindow
from integration import IntegrationWindow
from reservation import ReservationWindow
from usage import UsageWindow

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

        self.toggle_buttons()

    def toggle_buttons(self):
        self.reservationBtn.setEnabled(True)
        self.usageBtn.setEnabled(True)
        self.extraBtn.setEnabled(self.user_role in ["user", "admin"])
        self.integrationBtn.setEnabled(self.user_role == "admin")

    def open_reservation(self):
        self.reservation_window = ReservationWindow(self.user_role)
        self.reservation_window.show()
        self.hide()

    def open_usage(self):
        self.usage_window = UsageWindow(self.user_role)
        self.usage_window.show()
        self.hide()

    def open_extra(self):
        self.extra_window = ExtraWindow(self.user_role)
        self.extra_window.show()
        self.hide()

    def open_integration(self):
        self.integration_window = IntegrationWindow(self.user_role)
        self.integration_window.show()
        self.hide()

    def closeEvent(self, event):
        if self.parent():
            self.parent().show()
        event.accept()