import mysql.connector
from mysql.connector import Error

def create_database():
    try:
        # MySQL 연결 (기본 데이터베이스 사용, 아직 joeffice가 없으므로)
        conn = mysql.connector.connect(
            host="database-1.c1kkeqig4j9x.ap-northeast-2.rds.amazonaws.com",
            port=3306,
            user="root",
            password="12345678",
            database="amrbase"  # 초기 연결용 데이터베이스
        )
        cursor = conn.cursor()

        # joeffice 데이터베이스 생성
        cursor.execute("CREATE DATABASE IF NOT EXISTS joeffice")
        print("Database 'joeffice' created successfully.")

        # joeffice 데이터베이스로 전환
        cursor.execute("USE joeffice")

        # 테이블 생성 쿼리
        create_tables_queries = [
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id VARCHAR(50) PRIMARY KEY,
                username VARCHAR(100) NOT NULL,
                role ENUM('user', 'admin') DEFAULT 'user',
                rfid_uid BINARY(4)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS rooms (
                room_id INT AUTO_INCREMENT PRIMARY KEY,
                room_name VARCHAR(100) NOT NULL,
                capacity INT NOT NULL,
                location VARCHAR(100),
                equipment VARCHAR(255)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS reservations (
                reservation_id INT AUTO_INCREMENT PRIMARY KEY,
                room_id INT NOT NULL,
                user_id VARCHAR(50) NOT NULL,
                reservation_date DATE NOT NULL,
                start_time TIME NOT NULL,
                end_time TIME NOT NULL,
                topic VARCHAR(255),
                status ENUM('pending', 'confirmed', 'canceled', 'in_use') DEFAULT 'pending',
                FOREIGN KEY (room_id) REFERENCES rooms(room_id),
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS env_status (
                id INT AUTO_INCREMENT PRIMARY KEY,
                room_id INT NOT NULL,
                pm_value FLOAT DEFAULT 0.0,
                temperature FLOAT DEFAULT 0.0,
                light_level FLOAT DEFAULT 0.0,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (room_id) REFERENCES rooms(room_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS system_status (
                id INT PRIMARY KEY,
                status VARCHAR(50) DEFAULT '대기'
            )
            """
        ]

        # 테이블 생성 실행
        for query in create_tables_queries:
            cursor.execute(query)
            print("Table created successfully.")

        # 초기 데이터 삽입 (예시)
        cursor.execute("INSERT IGNORE INTO system_status (id, status) VALUES (1, '대기')")
        conn.commit()
        print("Initial data inserted.")

    except Error as e:
        print(f"Error: {e}")

    finally:
        if conn.is_connected():
            cursor.close()
            conn.close()
            print("MySQL connection closed.")

if __name__ == "__main__":
    create_database()