import mysql.connector
import serial
import time

# 아두이노 시리얼 포트 연결
arduino = serial.Serial(port="/dev/ttyACM1", baudrate=9600, timeout=1)

# DB 연결
db = mysql.connector.connect(
            host="database-1.c1kkeqig4j9x.ap-northeast-2.rds.amazonaws.com",
            port=3306,
            user="joeffice_user",
            password="12345678",
            database="joeffice"
)
cursor = db.cursor(dictionary=True)

last_status = None  # 이전 상태 기억

while True:
    # DB에서 최근 예약 상태 가져오기
    cursor.execute("SELECT reservation_status FROM reservations ORDER BY updated_at DESC LIMIT 1;")
    row = cursor.fetchone()

    if row:
        status = row["reservation_status"]

        if status != last_status:  # 상태가 바뀌었을 때만 아두이노로 전송
            if status == "FIRST_IN":
                arduino.write(b"FIRST_IN\n")
                print(">>> 아두이노로 FIRST_IN 전송")
            elif status == "IN":
                arduino.write(b"IN\n")
                print(">>> 아두이노로 IN 전송")
            elif status == "LAST_OUT":
                arduino.write(b"LAST_OUT\n")
                print(">>> 아두이노로 LAST_OUT 전송")

            last_status = status

    time.sleep(2)  # 2초마다 확인