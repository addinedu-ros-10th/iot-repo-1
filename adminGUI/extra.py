from PyQt6 import uic
from PyQt6.QtWidgets import QMainWindow, QApplication
from PyQt6.QtCore import QTimer
import sys, mysql.connector

# === DB 접속정보 (네 RDS 그대로 예시) ===
DB_CFG = dict(
    host="database-1.c1kkeqig4j9x.ap-northeast-2.rds.amazonaws.com",
    port=3306,
    user="root",
    password="12345678",
    database="joeffice",
)

# 회의실 이름(rooms.room_name 기준)
ROOM_NAMES = ["회의실 A", "회의실 B", "회의실 C"]

UiClass, _ = uic.loadUiType("extra.ui")

class ExtraWindow(QMainWindow, UiClass):
    def __init__(self, user_role):
        super().__init__()
        self.setupUi(self)

        # DB 연결
        self.db = self._connect_db()

        # 버튼 시그널
        self.refreshBuildingBtn.clicked.connect(self.refresh_building)
        self.refreshRoomsBtn.clicked.connect(self.refresh_rooms)

        # 초기 표시
        self.set_building_status(hvac=False, temp=None, hum=None, light=False)
        self._set_room_card("A", hvac=False, temp=None, hum=None, light=False)
        self._set_room_card("B", hvac=False, temp=None, hum=None, light=False)
        self._set_room_card("C", hvac=False, temp=None, hum=None, light=False)

        # 주기 갱신(선택): 5초
        self.timer = QTimer(self)
        self.timer.setInterval(5000)
        self.timer.timeout.connect(self.refresh_all)
        self.timer.start()

        self.refresh_all()

    # ========== DB ==========
    def _connect_db(self):
        try:
            conn = mysql.connector.connect(**DB_CFG)
            self.statusbar.showMessage("DB 연결 성공")
            return conn
        except Exception as e:
            self.statusbar.showMessage(f"DB 연결 실패: {e}")
            return None

    def _sql_one(self, query, params=None, dictcur=False):
        if not (self.db and self.db.is_connected()): return None
        cur = self.db.cursor(dictionary=dictcur)
        cur.execute(query, params or ())
        row = cur.fetchone()
        cur.close()
        return row

    def _sql_all(self, query, params=None, dictcur=False):
        if not (self.db and self.db.is_connected()): return []
        cur = self.db.cursor(dictionary=dictcur)
        cur.execute(query, params or ())
        rows = cur.fetchall()
        cur.close()
        return rows

    # ========== UI 바인딩 ==========
    def set_building_status(self, hvac: bool, temp, hum, light: bool):
        self.buildingHvacLabel.setText("ON" if hvac else "OFF")
        self.buildingTempLabel.setText(f"{temp:.1f} °C" if temp is not None else "--.- °C")
        self.buildingHumLabel.setText(f"{hum:.0f} %" if hum is not None else "--- %")
        self.buildingLightLabel.setText("ON" if light else "OFF")

    def _set_room_card(self, key: str, hvac: bool, temp, hum, light: bool):
        # key: "A" | "B" | "C"
        hvac_lbl  = getattr(self, f"room{key}HvacLabel")
        temp_lbl  = getattr(self, f"room{key}TempLabel")
        hum_lbl   = getattr(self, f"room{key}HumLabel")
        light_lbl = getattr(self, f"room{key}LightLabel")

        hvac_lbl.setText("ON" if hvac else "OFF")
        temp_lbl.setText(f"{temp:.1f} °C" if temp is not None else "--.- °C")
        hum_lbl.setText(f"{hum:.0f} %" if hum is not None else "--- %")
        light_lbl.setText("ON" if light else "OFF")

    # ========== 새로고침 로직 ==========
    def refresh_all(self):
        self.refresh_building()
        self.refresh_rooms()

    def refresh_building(self):
        """ building_system_status 우선, 없으면 room_status 집계 """
        row = self._sql_one("""
            SELECT hvac_on, light_on, temp_c, hum_pct
            FROM building_system_status
            WHERE building_id=1
        """)
        if row is not None:
            hvac = bool(row[0]) if not isinstance(row, dict) else bool(row.get("hvac_on", 0))
            light = bool(row[1]) if not isinstance(row, dict) else bool(row.get("light_on", 0))
            temp = (row[2] if not isinstance(row, dict) else row.get("temp_c"))
            hum  = (row[3] if not isinstance(row, dict) else row.get("hum_pct"))
            self.set_building_status(hvac=hvac, temp=temp, hum=hum, light=light)
            return

        # 대체: room_status 집계
        row = self._sql_one("""
            SELECT
              CASE WHEN SUM(CASE WHEN hvac_on=1 THEN 1 ELSE 0 END) > 0 THEN 1 ELSE 0 END AS hvac_on,
              CASE WHEN SUM(CASE WHEN light_on=1 THEN 1 ELSE 0 END) > 0 THEN 1 ELSE 0 END AS light_on,
              ROUND(AVG(temp_c),1) AS avg_temp_c,
              ROUND(AVG(hum_pct),1) AS avg_hum_pct
            FROM room_status
        """, dictcur=True)
        if row:
            self.set_building_status(
                hvac=bool(row["hvac_on"]),
                temp=row["avg_temp_c"],
                hum=row["avg_hum_pct"],
                light=bool(row["light_on"])
            )

    def refresh_rooms(self):
        """ rooms + room_status 조인으로 A/B/C 읽기 """
        rows = self._sql_all(f"""
            SELECT r.room_name, s.temp_c, s.hum_pct, s.hvac_on, s.light_on
            FROM rooms r
            LEFT JOIN room_status s USING(room_id)
            WHERE r.room_name IN (%s, %s, %s)
            ORDER BY r.room_name
        """, ROOM_NAMES, dictcur=True)

        # 기본값
        data = {name: dict(temp=None, hum=None, hvac=False, light=False) for name in ROOM_NAMES}

        for r in rows:
            name = r["room_name"]
            data[name] = dict(
                temp=r.get("temp_c"),
                hum=r.get("hum_pct"),
                hvac=bool(r.get("hvac_on", 0)),
                light=bool(r.get("light_on", 0))
            )

        # 매핑: UI 카드 키
        map_key = {
            "회의실 A": "A",
            "회의실 B": "B",
            "회의실 C": "C",
        }
        for name, vals in data.items():
            key = map_key.get(name)
            if key:
                self._set_room_card(key, vals["hvac"], vals["temp"], vals["hum"], vals["light"])

if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = ExtraWindow()
    w.show()
    sys.exit(app.exec())
