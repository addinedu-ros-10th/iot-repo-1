import mysql.connector
from mysql.connector import Error

def create_mysql_user():
    """
    MySQL에 joeffice_user를 생성하고, joeffice 데이터베이스에 대한 권한을 부여합니다.
    이 스크립트는 MySQL 관리자(root) 계정으로 실행되어야 합니다.
    """
    conn = None
    try:
        # MySQL 관리자(root) 계정으로 연결합니다.
        conn = mysql.connector.connect(
            host="database-1.c1kkeqig4j9x.ap-northeast-2.rds.amazonaws.com",
            port=3306,
            user="root",
            password="12345678"
        )
        cursor = conn.cursor()

        # 새로운 사용자를 생성합니다. 비밀번호는 'your_strong_password'로 변경하세요.
        # IF NOT EXISTS를 사용하여 이미 사용자가 존재해도 오류가 발생하지 않도록 합니다.
        create_user_query = "CREATE USER IF NOT EXISTS 'joeffice_user'@'%' IDENTIFIED BY '12345678'"
        cursor.execute(create_user_query)
        print("User 'joeffice_user' created successfully or already exists.")
        
        # 'joeffice' 데이터베이스의 모든 테이블에 대한 모든 권한을 부여합니다.
        grant_privileges_query = "GRANT ALL PRIVILEGES ON joeffice.* TO 'joeffice_user'@'%'"
        cursor.execute(grant_privileges_query)
        print("Privileges granted to 'joeffice_user' on 'joeffice' database.")

        # 변경된 권한을 즉시 적용합니다.
        cursor.execute("FLUSH PRIVILEGES")
        print("Privileges refreshed.")
        
    except Error as e:
        print(f"Error: {e}")
        
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()
            print("MySQL connection closed.")

if __name__ == "__main__":
    create_mysql_user()