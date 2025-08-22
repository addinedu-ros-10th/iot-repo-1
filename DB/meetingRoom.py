from mysql.connector import Error

def create_reservation_tables():
    """
    데이터베이스에 'rooms', 'users', 'rservationRooms' 테이블이 없으면 생성하는 함수입니다.
    """
    conn = None
    try:
        # DB 연결 정보 (사용자가 제공한 정보에 기반)
        conn = mysql.connector.connect(
            host="database-1.c1kkeqig4j9x.ap-northeast-2.rds.amazonaws.com",
            port=3306,
            user="root",  # 테이블 생성을 위해 root 계정 사용
            password="12345678", # RDS 비밀번호
            database="joeffice"
        )
        if conn.is_connected():
            print("Successfully connected to 'joeffice' database as 'root'.")
            cursor = conn.cursor()

            # 1. 'rooms' 테이블 생성
            create_rooms_table_query = """
            CREATE TABLE IF NOT EXISTS rooms (
                room_id INT AUTO_INCREMENT PRIMARY KEY,
                room_name VARCHAR(255) NOT NULL UNIQUE,
                capacity INT NOT NULL,
                location VARCHAR(255),
                equipment VARCHAR(255)
            );
            """
            cursor.execute(create_rooms_table_query)
            print("Table 'rooms' created or already exists.")

            # 2. 'users' 테이블 생성 (만약 없다면)
            create_users_table_query = """
            CREATE TABLE IF NOT EXISTS users (
                user_id VARCHAR(50) PRIMARY KEY,
                username VARCHAR(100) NOT NULL,
                role ENUM('user', 'admin') DEFAULT 'user'
            );
            """
            cursor.execute(create_users_table_query)
            print("Table 'users' created or already exists.")

            # 3. 'rservationRooms' 테이블 생성 (날짜와 시간을 분리하여 저장)
            create_rservation_rooms_table_query = """
            CREATE TABLE IF NOT EXISTS rservationRooms (
                reservation_id INT AUTO_INCREMENT PRIMARY KEY,
                user_ID VARCHAR(50) NOT NULL,
                user_name VARCHAR(100) NOT NULL,
                room_name VARCHAR(255) NOT NULL,
                starting_date DATE NOT NULL,
                starting_time TIME NOT NULL,
                ending_date DATE NOT NULL,
                ending_time TIME NOT NULL
            );
            """
            cursor.execute(create_rservation_rooms_table_query)
            print("Table 'rservationRooms' created or already exists.")

            # (선택) rooms 테이블에 샘플 데이터 삽입
            try:
                insert_rooms_data_query = """
                INSERT INTO rooms (room_name, capacity, location, equipment) VALUES
                ('회의실 A', 10, '1층', '빔프로젝터, 화이트보드'),
                ('회의실 B', 5, '2층', '화이트보드'),
                ('회의실 C', 20, '1층', '빔프로젝터, 화상회의 시스템')
                ON DUPLICATE KEY UPDATE room_name = room_name;
                """
                cursor.execute(insert_rooms_data_query)
                conn.commit()
                print("Sample data inserted into 'rooms' table.")
            except Error as insert_err:
                print(f"Error inserting sample data: {insert_err}")
                conn.rollback()

    except Error as e:
        print(f"Error: {e}")
        print("Please check your database connection details and user permissions.")
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()
            print("MySQL connection closed.")

if __name__ == "__main__":
    create_reservation_tables()
