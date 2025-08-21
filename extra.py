from PyQt6.QtWidgets import QMainWindow, QMessageBox
from PyQt6 import uic
from PyQt6.QtCore import QTimer
import mysql.connector  # DB 연동
import smtplib  # 이메일 알림
from email.mime.text import MIMEText

class ExtraWindow(QMainWindow):
    def __init__(self, user_role):
        super().__init__()
        uic.loadUi("extra.ui", self)
        self.user_role = user_role
        self.db_conn = None
        self.connect_db()  # AWS RDS에 연결 시도
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_env_status)
        self.timer.start(10000)  # 10초 간격 환경 상태 갱신

        # 버튼 연결
        self.repeatBtn.clicked.connect(self.repeat_reservation)
        self.toggleEquipmentBtn.clicked.connect(self.toggle_equipment)
        self.sendNotificationBtn.clicked.connect(self.save_notification_settings)
        self.refreshEnvBtn.clicked.connect(self.update_env_status)
        self.generateReportBtn.clicked.connect(self.generate_report)

        self.toggle_buttons()
        self.update_env_status()

    def connect_db(self):
        try:
            self.db_conn = mysql.connector.connect(
                host="database-1.c1kkeqig4j9x.ap-northeast-2.rds.amazonaws.com",
                port=3306,
                user="root",
                password="12345678",  # RDS 비밀번호
                database="joeffice"  # 새 데이터베이스
            )
            self.statusbar.showMessage("DB 연결 성공")
        except mysql.connector.Error as err:
            self.statusbar.showMessage(f"DB 연결 실패: {err}")
            QMessageBox.critical(self, "오류", f"데이터베이스 연결 실패: {err}")

    def toggle_buttons(self):
        self.repeatBtn.setEnabled(self.user_role == "user" or self.user_role == "admin")
        self.toggleEquipmentBtn.setEnabled(self.user_role == "admin")
        self.sendNotificationBtn.setEnabled(self.user_role == "user" or self.user_role == "admin")
        self.refreshEnvBtn.setEnabled(True)
        self.generateReportBtn.setEnabled(self.user_role == "admin")

    def repeat_reservation(self):
        if self.user_role:
            cycle = self.repeatCombo.currentText()
            QMessageBox.information(self, "반복 예약", f"{cycle} 반복 예약 설정 완료.")

    def toggle_equipment(self):
        if self.user_role == "admin":
            current_state = "ON" if "OFF" in self.equipmentLabel.text() else "OFF"
            self.equipmentLabel.setText(f"장비 상태: {current_state}")
            QMessageBox.information(self, "장비 연동", f"장비가 {current_state} 되었습니다.")

    def save_notification_settings(self):
        if self.user_role:
            email = self.emailCheck.isChecked()
            push = self.pushCheck.isChecked()
            if email:
                self.send_email("예약 시작 전 알림", "회의가 10분 후 시작됩니다.")
            if push:
                self.send_push("예약 알림", "회의가 10분 후 시작됩니다.")
            QMessageBox.information(self, "알림 설정", "알림 설정 저장 완료.")

    def send_email(self, subject, message):
        try:
            server = smtplib.SMTP('smtp.gmail.com', 587)
            server.starttls()
            server.login('your_email@gmail.com', '12345678')  # 사용자의 계정 및 비밀번호
            msg = MIMEText(message)
            msg['Subject'] = subject
            msg['To'] = 'recipient@example.com'  # 수신자 이메일
            server.sendmail('your_email@gmail.com', 'recipient@example.com', msg.as_string())
            server.quit()
            self.statusbar.showMessage("이메일 알림 전송 성공")
        except Exception as e:
            self.statusbar.showMessage(f"이메일 알림 실패: {e}")

    def send_push(self, title, message):
        print(f"푸시 알림: {title} - {message}")  # 실제 푸시 서비스(FCM 등) 필요

    def update_env_status(self):
        if self.db_conn and self.db_conn.is_connected():
            try:
                cursor = self.db_conn.cursor()
                cursor.execute("SELECT pm_value, temperature, light_level FROM env_status LIMIT 1")  # 테이블 필드명 조정
                env_data = cursor.fetchone() or (25, 22.5, 500)
                self.pmLabel.setText(f"미세먼지: {env_data[0]} µg/m³")
                self.tempLabel.setText(f"온도: {env_data[1]}°C")
                self.lightLabel.setText(f"조도: {env_data[2]} lux")
            except Exception as e:
                self.pmLabel.setText(f"미세먼지: 오류 ({e})")
                self.tempLabel.setText(f"온도: 오류 ({e})")
                self.lightLabel.setText(f"조도: 오류 ({e})")
        else:
            self.pmLabel.setText("미세먼지: DB 연결 없음")
            self.tempLabel.setText("온도: DB 연결 없음")
            self.lightLabel.setText("조도: DB 연결 없음")

    def generate_report(self):
        if self.user_role == "admin" and self.db_conn and self.db_conn.is_connected():
            try:
                cursor = self.db_conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM reservations")
                usage = cursor.fetchone()[0]
                cursor.execute("SELECT COUNT(*) FROM reservations WHERE status = 'canceled'")
                cancel = cursor.fetchone()[0]
                cancel_rate = (cancel / usage) * 100 if usage else 0
                cursor.execute("SELECT start_time FROM reservations GROUP BY start_time ORDER BY COUNT(*) DESC LIMIT 1")
                peak = cursor.fetchone()[0] if cursor.rowcount > 0 else "미정"
                self.usageLabel.setText(f"사용률: {usage}%")
                self.cancelLabel.setText(f"취소율: {cancel_rate:.2f}%")
                self.peakLabel.setText(f"피크 시간대: {peak}")
                QMessageBox.information(self, "통계 리포트", "리포트 생성 완료.")
            except Exception as e:
                self.statusbar.showMessage(f"리포트 생성 실패: {e}")
        else:
            self.statusbar.showMessage("리포트 생성 실패: 관리자 권한 또는 DB 연결 필요")

    def closeEvent(self, event):
        if self.db_conn:
            self.db_conn.close()
        event.accept()
