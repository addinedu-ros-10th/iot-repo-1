from PyQt6.QtWidgets import QMainWindow, QStatusBar
from PyQt6 import uic
from PyQt6.QtCore import QTimer
import serial
import struct
import mysql.connector
import websocket  # WebSocket 예시용 (pip install websocket-client 필요)

class IntegrationWindow(QMainWindow):
    def __init__(self, user_role):
        super().__init__()
        uic.loadUi("integration.ui", self)
        self.user_role = user_role
        self.conn = serial.Serial(port='/dev/ttyACM0', baudrate=9600, timeout=1)
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_status)
        self.timer.start(5000)  # 5초 간격 상태 갱신

        # 버튼 연결
        self.adminSyncBtn.clicked.connect(self.sync_admin)
        self.connectMobileWebBtn.clicked.connect(self.connect_mobile_web)
        self.rfidLinkBtn.clicked.connect(self.link_rfid)

        self.toggle_buttons()
        self.update_status()

    def toggle_buttons(self):
        self.adminSyncBtn.setEnabled(self.user_role == "admin")
        self.connectMobileWebBtn.setEnabled(self.user_role == "admin")
        self.rfidLinkBtn.setEnabled(self.user_role == "admin")

    def update_status(self):
        # DB에서 상태 조회 (예시)
        try:
            db_conn = mysql.connector.connect(
                host="database-1.c1kkeqig4j9x.ap-northeast-2.rds.amazonaws.com",
                port=3306,
                user="root",
                password="12345678",  # RDS 비밀번호
                database="joeffice"
            )
            cursor = db_conn.cursor()
            cursor.execute("SELECT status FROM system_status LIMIT 1")
            status = cursor.fetchone()
            db_conn.close()
            if status:
                self.syncLabel.setText(f"연동 상태: {status[0]}")
            else:
                self.syncLabel.setText("연동 상태: 대기")
        except:
            self.syncLabel.setText("연동 상태: 오류")

        # 모바일/웹 연동 상태 (모의)
        self.mobileWebLabel.setText("모바일/웹 연동: 연결됨" if self.is_mobile_connected() else "모바일/웹 연동: 미연동")
        # RFID 상태 (모의)
        self.rfidLabel.setText("RFID 연계: 활성화" if self.is_rfid_linked() else "RFID 연계: 비활성화")

    def sync_admin(self):
        if self.user_role == "admin":
            try:
                db_conn = mysql.connector.connect(
                    host="database-1.c1kkeqig4j9x.ap-northeast-2.rds.amazonaws.com",
                    port=3306,
                    user="root",
                    password="12345678",  # RDS 비밀번호
                    database="joeffice"
                )
                cursor = db_conn.cursor()
                cursor.execute("UPDATE system_status SET status = '동기화 완료' WHERE id = 1")
                db_conn.commit()
                db_conn.close()
                self.statusbar.showMessage("Admin 동기화 성공")
            except Exception as e:
                self.statusbar.showMessage(f"Admin 동기화 실패: {e}")

    def connect_mobile_web(self):
        if self.user_role == "admin":
            # WebSocket으로 모바일/웹 서버 연결 (예시)
            def on_open(ws):
                ws.send("CONNECT")
                self.mobileWebLabel.setText("모바일/웹 연동: 연결됨")
                self.statusbar.showMessage("모바일/웹 연결 성공")

            ws = websocket.WebSocketApp("ws://localhost:8765",
                                      on_open=on_open)
            ws.run_forever()

    def link_rfid(self):
        if self.user_role == "admin":
            try:
                self.send(b'RFID_CHECK')  # Arduino에 RFID 연계 요청
                self.rfidLabel.setText("RFID 연계: 활성화")
                self.statusbar.showMessage("RFID 연계 활성화")
            except Exception as e:
                self.statusbar.showMessage(f"RFID 연계 실패: {e}")

    def send(self, command):
        req_data = struct.pack('<2s', command) + b'\n'
        self.conn.write(req_data)

    def is_mobile_connected(self):
        # 모의 함수: 실제로는 WebSocket 상태 확인
        return False

    def is_rfid_linked(self):
        # 모의 함수: 실제로는 Arduino 응답 확인
        return False

    def closeEvent(self, event):
        self.conn.close()
        event.accept()