// 전체 건물 냉난방시스템
// DHT-11 온습도센서 + 3색 LED + 점유 플래그(Serial 명령)
//   HE 1   -> FIRST IN 이후(허용)
//   HE 0   -> LAST OUT 이후(차단)
//   HR     -> 상태 요청

#include "DHT.h"

#define DHTPIN 2
#define DHTTYPE DHT11
DHT dht(DHTPIN, DHTTYPE);

// LED 핀: R=히터, G=중립(쾌적), B=에어컨
const int R_LED = 3;
const int G_LED = 5;
const int B_LED = 6;

// 점유 허용/차단 (PyQt/DB가 결정해서 내려줌)
bool hvac_enable = false;  // 기본: 차단

// === 히스테리시스 임계값 ===
// 냉방(에어컨): 온도 또는 습도 중 하나라도 "켜짐 조건"이면 켜고,
// 꺼질 때는 온도와 습도가 모두 "꺼짐 조건"을 만족해야 끔.
float COOL_ON   = 26.0;  // 이 이상이면 냉방 켜기
float COOL_OFF  = 25.5;  // 이 이하면 냉방 끄기 후보 (습도도 낮아야 최종 해제)
float HUM_ON    = 70.0;  // 이 이상이면 냉방 켜기(제습 목적)
float HUM_OFF   = 65.0;  // 이 이하면 냉방 끄기 후보 (온도도 낮아야 최종 해제)

float HEAT_ON   = 15.0;  // 이 이하면 난방 켜기
float HEAT_OFF  = 15.5;  // 이 이상이면 난방 끄기

// 상태 표현
enum HvacState { DISABLED, IDLE, COOLING, HEATING };
HvacState state = DISABLED;

// 직렬 입력 버퍼
String rxLine;

void setLeds(bool r, bool g, bool b) {
  digitalWrite(R_LED, r ? HIGH : LOW);
  digitalWrite(G_LED, g ? HIGH : LOW);
  digitalWrite(B_LED, b ? HIGH : LOW);
}

void applyState(HvacState s) {
  state = s;
  switch (s) {
    case DISABLED: setLeds(false, false, false); break; // 차단: 모두 OFF
    case IDLE:     setLeds(false, true,  false); break; // 쾌적: G ON
    case COOLING:  setLeds(false, false, true ); break; // 냉방: B ON
    case HEATING:  setLeds(true,  false, false); break; // 난방: R ON
  }
}

// ---- 핵심 제어 로직 (온도 + 습도) ----
void handleControl(float t, float h) {
  if (!hvac_enable) {                 // LAST OUT 이후: 무조건 OFF
    applyState(DISABLED);
    return;
  }

  // 냉방: (t >= COOL_ON)  OR (h >= HUM_ON)  이면 ON
  // 해제: (t <= COOL_OFF) AND (h <= HUM_OFF) 이면 OFF
  bool wantCoolOn  = (t >= COOL_ON) || (h >= HUM_ON);
  bool wantCoolOff = (t <= COOL_OFF) && (h <= HUM_OFF);

  // 난방: (t <= HEAT_ON) 이면 ON, (t >= HEAT_OFF) 이면 OFF
  bool wantHeatOn  = (t <= HEAT_ON);
  bool wantHeatOff = (t >= HEAT_OFF);

  switch (state) {
    case COOLING:
      if (wantCoolOff) applyState(IDLE);
      else             applyState(COOLING);
      break;

    case HEATING:
      if (wantHeatOff) {
        // 난방 해제 후 바로 냉방 조건이 강하면 냉방으로 전환
        if (wantCoolOn) applyState(COOLING);
        else            applyState(IDLE);
      } else {
        applyState(HEATING);
      }
      break;

    case IDLE:
    case DISABLED: // enable이 막 true로 바뀐 직후 진입 가능
      if (wantCoolOn)      applyState(COOLING);
      else if (wantHeatOn) applyState(HEATING);
      else                 applyState(IDLE);
      break;
  }
}

void processLine(String line) {
  line.trim();
  if (line.length() == 0) return;
  if (line.startsWith("HE")) {
    int sp = line.indexOf(' ');
    if (sp > 0) {
      String val = line.substring(sp + 1); val.trim();
      if (val == "1") {
        hvac_enable = true;
        setLight(true);   // ★ HVAC enable 시 조명도 ON
        Serial.println(F("[OK] HE 1 (hvac+light enable)"));
      } else if (val == "0") {
        hvac_enable = false;
        applyState(DISABLED);
        setLight(false);  // ★ HVAC disable 시 조명도 OFF
        Serial.println(F("[OK] HE 0 (hvac+light disable)"));
      }
    }
  }

  // if (line.startsWith("HE")) {
  //   int sp = line.indexOf(' ');
  //   if (sp > 0) {
  //     String val = line.substring(sp + 1);
  //     val.trim();
  //     if (val == "1") {
  //       hvac_enable = true;
  //       Serial.println(F("[OK] HE 1 (enable=true)"));
  //     } else if (val == "0") {
  //       hvac_enable = false;
  //       applyState(DISABLED);
  //       Serial.println(F("[OK] HE 0 (enable=false)"));
  //     } else {
  //       Serial.println(F("[ERR] HE value must be 0 or 1"));
  //     }
  //   } else {
  //     Serial.println(F("[ERR] Usage: HE 0|1"));
  //   }
  // }
  else if (line == "HR") {
    float h = dht.readHumidity();
    float t = dht.readTemperature();
    if (isnan(h) || isnan(t)) {
      Serial.println(F("[ERR] DHT read failed"));
      return;
    }
    Serial.print(F("TEMP:")); Serial.print(t, 1);
    Serial.print(F("C HUM:")); Serial.print(h, 1);
    Serial.print(F("% ENABLE:")); Serial.print(hvac_enable ? "1" : "0");
    Serial.print(F(" STATE:"));
    switch (state) {
      case DISABLED: Serial.println(F("DISABLED")); break;
      case IDLE:     Serial.println(F("IDLE"));     break;
      case COOLING:  Serial.println(F("COOLING"));  break;
      case HEATING:  Serial.println(F("HEATING"));  break;
    }
  }
  else {
    Serial.print(F("[ERR] Unknown cmd: "));
    Serial.println(line);
  }
}

void setup() {
  Serial.begin(9600);
  dht.begin();

  pinMode(R_LED, OUTPUT);
  pinMode(G_LED, OUTPUT);
  pinMode(B_LED, OUTPUT);

  applyState(DISABLED); // 시작 시 차단 상태
  Serial.println(F("HVAC LED demo ready. Commands: 'HE 1', 'HE 0', 'HR'"));
}

void loop() {
  // 1) 직렬 명령 처리
  while (Serial.available()) {
    char c = (char)Serial.read();
    if (c == '\n' || c == '\r') {
      if (rxLine.length() > 0) {
        processLine(rxLine);
        rxLine = "";
      }
    } else {
      rxLine += c;
      if (rxLine.length() > 64) rxLine = "";
    }
  }

  // 2) 주기 센서 읽기 + 제어
  static unsigned long lastMs = 0;
  unsigned long now = millis();
  if (now - lastMs >= 2000) {  // 2초 주기
    lastMs = now;

    float h = dht.readHumidity();
    float t = dht.readTemperature();

    if (isnan(h) || isnan(t)) {
      Serial.println(F("Failed to read from DHT sensor !"));
      return;
    }

    handleControl(t, h); // 온도+습도 반영

    // 상태 로그
    Serial.print(F("Temperature: "));
    Serial.print(t, 1);
    Serial.print(F(" C, Humidity: "));
    Serial.print(h, 1);
    Serial.print(F(" %, ENABLE="));
    Serial.print(hvac_enable ? "1" : "0");
    Serial.print(F(", STATE="));
    switch (state) {
      case DISABLED: Serial.println(F("DISABLED")); break;
      case IDLE:     Serial.println(F("IDLE"));     break;
      case COOLING:  Serial.println(F("COOLING"));  break;
      case HEATING:  Serial.println(F("HEATING"));  break;
    }
  }
}
