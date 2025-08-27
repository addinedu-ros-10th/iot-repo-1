#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
from PyQt6.QtWidgets import QMainWindow, QMessageBox, QApplication, QVBoxLayout, QLabel, QGroupBox, QFrame
from PyQt6 import uic
from PyQt6.QtCore import Qt
import mysql.connector
from datetime import datetime, timedelta

class ReservationCheckWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        try:
            uic.loadUi("reservation_check.ui", self)
        except FileNotFoundError:
            QMessageBox.critical(self, "오류", "reservation_check.ui 파일을 찾을 수 없습니다.")
            sys.exit(1)

        self.db_conn = None
        self.users = {}
        
        self.connect_db()
        self.handle_expired_reservations()
        # ▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼
        # 요청하신 기능: 시작 시 CHECKED_IN 상태인 지난 예약 업데이트
        self._update_overdue_checkins()
        # ▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲
        self.load_users()
        self.load_users_to_combobox()

        self.verifyBtn.clicked.connect(self.find_auth_code)

    def connect_db(self):
        try:
            self.db_conn = mysql.connector.connect(
                host="database-1.c1kkeqig4j9x.ap-northeast-2.rds.amazonaws.com",
                port=3306,
                user="root",
                password="12345678",
                database="joeffice"
            )
            print("DB 연결 성공")
        except mysql.connector.Error as err:
            QMessageBox.critical(self, "오류", f"데이터베이스 연결 실패: {err}")
            sys.exit(1)

    # ▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼
    # 추가된 메서드
    # ▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼
    def _update_overdue_checkins(self):
        """
        프로그램 시작 시, 예약 종료 시간이 지났지만 'CHECKED_IN' 상태인 예약을
        'CHECKED_OUT'으로 상태를 변경합니다.
        """
        if not self.db_conn or not self.db_conn.is_connected():
            return
            
        try:
            cursor = self.db_conn.cursor()
            now_kst = datetime.now()
            
            cursor.execute("""
                UPDATE reservations
                SET reservation_status = 'CHECKED_OUT', updated_at = %s
                WHERE end_time < %s AND reservation_status = 'CHECKED_IN'
            """, (now_kst, now_kst))
            
            # 실제로 변경된 행이 있는지 확인
            updated_rows = cursor.rowcount
            self.db_conn.commit()
            
            if updated_rows > 0:
                print(f"{updated_rows}개의 CHECKED_IN 상태의 만료된 예약이 CHECKED_OUT으로 변경되었습니다.")
                # 사용자에게 알림이 너무 많아지지 않도록 이 부분은 정보성 print로만 남겨둘 수 있습니다.
                # QMessageBox.information(self, "자동 업데이트", f"{updated_rows}개의 입실 상태였던 만료된 예약이 자동으로 처리되었습니다.")
        except Exception as e:
            print(f"CHECKED_IN 상태의 만료된 예약 처리 중 오류 발생: {e}")
        finally:
            cursor.close()
    # ▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲

    def handle_expired_reservations(self):
        """
        예약 시간이 지났고, 'BOOKED' 상태인 예약을 찾아 'CHECKED_OUT' 상태로 자동 변경합니다.
        (한국 시간 기준)
        """
        if not self.db_conn or not self.db_conn.is_connected():
            return
            
        try:
            cursor = self.db_conn.cursor()
            # ⬅️ **수정된 부분**: 현재 시간을 한국 시간 기준으로 가져옴
            now_kst = datetime.now()
            
            cursor.execute("""
                SELECT COUNT(*) FROM reservations
                WHERE end_time < %s AND reservation_status = 'BOOKED'
            """, (now_kst,))
            
            count = cursor.fetchone()[0]
            
            if count > 0:
                cursor.execute("""
                    UPDATE reservations
                    SET reservation_status = 'CHECKED_OUT', updated_at = %s
                    WHERE end_time < %s AND reservation_status = 'BOOKED'
                """, (now_kst, now_kst))
                self.db_conn.commit()
                print(f"{count}개의 만료된 예약이 CHECKED_OUT 상태로 변경되었습니다.")
                QMessageBox.information(self, "자동 업데이트", f"{count}개의 만료된 예약이 자동으로 처리되었습니다.")
        except Exception as e:
            print(f"만료된 예약 처리 중 오류 발생: {e}")
        finally:
            cursor.close()

    def load_users(self):
        """ users 테이블에서 사용자 정보를 캐시 딕셔너리로 로드합니다 """
        if self.db_conn and self.db_conn.is_connected():
            try:
                cursor = self.db_conn.cursor()
                cursor.execute("SELECT uid, name FROM users")
                for uid, name in cursor.fetchall():
                    self.users[uid] = name
            except Exception as e:
                print(f"사용자 정보 로드 실패: {e}")

    def load_users_to_combobox(self):
        """ users 테이블의 UID를 콤보박스에 로드합니다 """
        if hasattr(self, 'userIDComboBox'):
            self.userIDComboBox.clear()
            uids = sorted(self.users.keys())
            self.userIDComboBox.addItems(uids)
            self.userIDComboBox.currentIndexChanged.connect(self.update_user_name_input)
        else:
            print("UI에 userIDComboBox가 정의되지 않았습니다.")
            
    def update_user_name_input(self):
        """ 선택된 UID에 따라 이름 필드를 자동으로 채웁니다 """
        selected_uid = self.userIDComboBox.currentText()
        if selected_uid in self.users:
            self.userNameInput.setText(self.users[selected_uid])
        else:
            self.userNameInput.clear()

    def find_auth_code(self):
        """직원 코드와 이름으로 예약 인증번호를 조회하는 함수 (한국 시간 기준)"""
        uid = self.userIDComboBox.currentText().strip()
        user_name = self.userNameInput.text().strip()

        if not uid or not user_name:
            QMessageBox.warning(self, "경고", "직원 코드와 사용자 이름을 모두 선택하세요.")
            return

        self.clear_dynamic_widgets()

        try:
            cursor = self.db_conn.cursor()
            # ⬅️ **수정된 부분**: 현재 시간을 한국 시간 기준으로 가져와 쿼리에 사용
            now_kst = datetime.now()

            # ⬅️ **수정된 부분**: 시간대 변환 없이 유효한 예약을 찾음
            cursor.execute("""
                SELECT r.auth_code, r.room_name, r.start_time, r.end_time
                FROM reservations r
                LEFT JOIN users u ON r.uid = u.uid
                WHERE r.uid = %s AND u.name = %s
                AND r.end_time >= %s
                AND r.reservation_status IN ('BOOKED', 'CHECKED_IN')
                ORDER BY r.start_time ASC
            """, (uid, user_name, now_kst))

            results = cursor.fetchall()

            if results:
                self.statusLabel.setText("상태: <font color='blue'>예약 정보가 확인되었습니다.</font>")
                self.create_dynamic_widgets(results)
            else:
                self.statusLabel.setText("상태: <font color='red'>일치하는 예약 정보가 없습니다.</font>")

        except Exception as e:
            QMessageBox.critical(self, "오류", f"예약 정보 조회 중 오류 발생: {e}")
            self.statusLabel.setText("상태: <font color='red'>오류 발생</font>")
        finally:
            cursor.close()

    def create_dynamic_widgets(self, reservations):
        """ 여러 예약 정보를 동적으로 생성하여 표시 (시간 변환 없음) """
        group_box = self.reservationDetailsGroup
        self.clear_dynamic_widgets()
        layout = QVBoxLayout(group_box)
        
        # ⬅️ **수정된 부분**: KST 변환 로직 제거
        for auth_code, room_name, start_time, end_time in reservations:
            reservation_info_label = QLabel(
                f"<b>회의실:</b> {room_name}<br>"
                f"<b>시작:</b> {start_time.strftime('%Y-%m-%d %H:%M:%S')}<br>"
                f"<b>종료:</b> {end_time.strftime('%Y-%m-%d %H:%M:%S')}<br>"
                f"<b>인증 번호:</b> <font color='blue' size='5'><b>{auth_code}</b></font>"
            )
            reservation_info_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
            layout.addWidget(reservation_info_label)
            
            line = QFrame(group_box)
            line.setFrameShape(QFrame.Shape.HLine)
            line.setFrameShadow(QFrame.Shadow.Sunken)
            layout.addWidget(line)
        
        group_box.setLayout(layout)

    def clear_dynamic_widgets(self):
        """ 기존 동적 위젯을 제거합니다 """
        group_box = self.reservationDetailsGroup
        if group_box.layout():
            while group_box.layout().count():
                child = group_box.layout().takeAt(0)
                if child.widget():
                    child.widget().deleteLater()

    def closeEvent(self, event):
        if self.db_conn:
            self.db_conn.close()
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = ReservationCheckWindow()
    window.show()
    sys.exit(app.exec())
