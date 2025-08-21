import mysql.connector
from mysql.connector import Error

def connect_to_joeffice_db():
    """
    joeffice_user 계정으로 joeffice 데이터베이스에 접속하는 예시입니다.
    """
    conn = None
    try:
        # 이전에 생성한 'joeffice_user'로 MySQL에 접속합니다.
        # 비밀번호는 '12345678'로 설정되어 있습니다.
        conn = mysql.connector.connect(
            host="database-1.c1kkeqig4j9x.ap-northeast-2.rds.amazonaws.com",
            port=3306,
            user="joeffice_user",
            password="12345678",
            database="joeffice"
        )
        if conn.is_connected():
            print("Successfully connected to 'joeffice' database as 'joeffice_user'.")
            cursor = conn.cursor()

            # 테이블이 존재하지 않으면 생성
            create_table_query = """
            CREATE TABLE IF NOT EXISTS users (
                user_id VARCHAR(50) PRIMARY KEY,
                username VARCHAR(100) NOT NULL,
                role ENUM('user', 'admin') DEFAULT 'user',
                rfid_uid BINARY(4)
            )
            """
            cursor.execute(create_table_query)
            print("Table 'users' created or already exists.")

            # users 테이블에 데이터 삽입 (예시)
            add_user_query = """
            INSERT INTO users (user_id, username, role)
            VALUES (%s, %s, %s)
            """
            user_data = ('new_user', 'Jane Doe', 'user')
            cursor.execute(add_user_query, user_data)
            conn.commit()
            print("User 'Jane Doe' added successfully.")
            
            # 데이터 조회 예시
            cursor.execute("SELECT * FROM users")
            users = cursor.fetchall()
            print("\nAll users:")
            for user in users:
                print(user)

    except Error as e:
        print(f"Error: {e}")

    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()
            print("MySQL connection closed.")

if __name__ == "__main__":
    connect_to_joeffice_db()
