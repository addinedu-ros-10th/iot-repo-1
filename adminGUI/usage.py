from PyQt6.QtWidgets import QMainWindow, QMessageBox
from PyQt6 import uic
from PyQt6.QtCore import QTimer, QTime
import serial
import struct
import mysql.connector  # AWS RDS 연동

class UsageWindow(QMainWindow):
    def __init__(self, user_role):
        super().__init__()
        uic.loadUi("usage.ui", self)
        self.user_role = user_role
        self.db_conn = None
        self.serial_conn = None
        self.connect_db()
        self.connect_serial()
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_status)
        self.timer.start(5000)  # 5초 간격 상태 갱신

        # 버튼 연결
        self.simulateCheckinBtn.clicked.connect(self.simulate_checkin)
        self.cancelNoshowBtn.clicked.connect(self.simulate_noshow_cancel)
        self.simulateEndBtn.clicked.connect(self.simulate_end)

        self.toggle_buttons()
        self.update_status()

    def connect_db(self):
        try:
            self.db_conn = mysql.connector.connect(
                host="database-1.c1kkeqig4j9x.ap-northeast-2.rds.amazonaws.com",
                port=3306,
                user="root",
                password="12345678",  # RDS 비밀번호
                database="joeffice"
            )
            self.statusbar.showMessage("DB 연결 성공")
        except mysql.connector.Error as err:
            self.statusbar.showMessage(f"DB 연결 실패: {err}")
            QMessageBox.critical(self, "오류", f"데이터베이스 연결 실패: {err}")

    def connect_serial(self):
        try:
            self.serial_conn = serial.Serial(port='/dev/ttyACM0', baudrate=9600, timeout=1)
            self.statusbar.showMessage("시리얼 연결 성공")
        except serial.SerialException as e:
            self.statusbar.showMessage(f"시리얼 연결 실패: {e}")

    def toggle_buttons(self):
        self.simulateCheckinBtn.setEnabled(self.user_role == "admin")
        self.cancelNoshowBtn.setEnabled(self.user_role == "admin")
        self.simulateEndBtn.setEnabled(self.user_role == "admin")

    def update_status(self):
        if self.db_conn and self.db_conn.is_connected():
            try:
                cursor = self.db_conn.cursor()
                cursor.execute("SELECT status FROM reservations WHERE reservation_id = (SELECT MAX(reservation_id) FROM reservations)")
                status = cursor.fetchone()
                if status:
                    self.checkinStatus.setText(f"체크인 상태: {status[0]}")
                    if status[0] == "pending":
                        self.noshowStatus.setText("노쇼 상태: 경고 (5분 경과)")
                    else:
                        self.noshowStatus.setText("노쇼 상태: 정상")
                cursor.execute("SELECT equipment_status FROM system_status WHERE id = 1")
                equip_status = cursor.fetchone()
                self.equipmentStatus.setText(f"장비 상태: {equip_status[0] if equip_status else 'OFF'}")
                self.usageStatus.setText(f"사용 상태: {status[0] if status else '비활성'}")
            except Exception as e:
                self.statusbar.showMessage(f"상태 업데이트 실패: {e}")

    def simulate_checkin(self):
        if self.user_role == "admin" and self.serial_conn:
            try:
                self.send_serial(b'CHECKIN')
                cursor = self.db_conn.cursor()
                cursor.execute("UPDATE reservations SET status = 'confirmed' WHERE reservation_id = (SELECT MAX(reservation_id) FROM reservations)")
                self.db_conn.commit()
                self.checkinStatus.setText("체크인 상태: confirmed")
                self.statusbar.showMessage("체크인 성공")
            except Exception as e:
                self.statusbar.showMessage(f"체크인 실패: {e}")

    def simulate_noshow_cancel(self):
        if self.user_role == "admin" and self.db_conn and self.db_conn.is_connected():
            try:
                cursor = self.db_conn.cursor()
                cursor.execute("UPDATE reservations SET status = 'canceled' WHERE status = 'pending' AND TIMESTAMPDIFF(MINUTE, reservation_date, NOW()) > 5")
                self.db_conn.commit()
                self.noshowStatus.setText("노쇼 상태: 취소됨")
                self.statusbar.showMessage("노쇼 취소 완료")
            except Exception as e:
                self.statusbar.showMessage(f"노쇼 취소 실패: {e}")

    def simulate_end(self):
        if self.user_role == "admin" and self.serial_conn:
            try:
                self.send_serial(b'END')
                cursor = self.db_conn.cursor()
                cursor.execute("UPDATE system_status SET equipment_status = 'OFF' WHERE id = 1")
                cursor.execute("UPDATE reservations SET status = 'completed' WHERE reservation_id = (SELECT MAX(reservation_id) FROM reservations)")
                self.db_conn.commit()
                self.equipmentStatus.setText("장비 상태: OFF")
                self.usageStatus.setText("사용 상태: 완료")
                self.statusbar.showMessage("사용 종료 및 장비 OFF 완료")
            except Exception as e:
                self.statusbar.showMessage(f"종료 실패: {e}")

    def send_serial(self, command):
        if self.serial_conn and self.serial_conn.is_open:
            req_data = struct.pack('<2s', command) + b'\n'
            self.serial_conn.write(req_data)

    def closeEvent(self, event):
        if self.db_conn:
            self.db_conn.close()
        if self.serial_conn:
            self.serial_conn.close()
        event.accept()

