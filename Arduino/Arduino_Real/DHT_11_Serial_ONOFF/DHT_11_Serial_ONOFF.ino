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
bool hvac_enable = false;  // 기본: 차단(=LAST OUT 가정)

// 히스테리시스 임계값 (원하면 Serial로 바꾸게 확장 가능)
float COOL_ON  = 26.0;  // 이 이상이면 냉방 켜기
float COOL_OFF = 25.5;  // 이 이하면 냉방 끄기
float HEAT_ON  = 15.0;  // 이 이하면 난방 켜기
float HEAT_OFF = 15.5;  // 이 이상이면 난방 끄기

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

void handleControl(float t) {
  if (!hvac_enable) {                 // LAST OUT 이후: 무조건 OFF
    applyState(DISABLED);
    return;
  }

  // enable=true일 때 온도 기반 제어(히스테리시스)
  switch (state) {
    case COOLING:
      if (t <= COOL_OFF) applyState(IDLE);
      else               applyState(COOLING);
      break;

    case HEATING:
      if (t >= HEAT_OFF) applyState(IDLE);
      else               applyState(HEATING);
      break;

    case IDLE:
    case DISABLED: // enable이 막 true로 바뀐 직후 진입 가능
      if (t >= COOL_ON)      applyState(COOLING);
      else if (t <= HEAT_ON) applyState(HEATING);
      else                   applyState(IDLE);
      break;
  }
}

void processLine(String line) {
  line.trim();
  if (line.length() == 0) return;

  if (line.startsWith("HE")) {
    // 형식: "HE 1" 또는 "HE 0"
    int sp = line.indexOf(' ');
    if (sp > 0) {
      String val = line.substring(sp + 1);
      val.trim();
      if (val == "1") {
        hvac_enable = true;
        // 방금 허용되었으니 상태는 온도 읽은 뒤 갱신됨
        Serial.println(F("[OK] HE 1 (enable=true)"));
      } else if (val == "0") {
        hvac_enable = false;
        applyState(DISABLED);
        Serial.println(F("[OK] HE 0 (enable=false)"));
      } else {
        Serial.println(F("[ERR] HE value must be 0 or 1"));
      }
    } else {
      Serial.println(F("[ERR] Usage: HE 0|1"));
    }
  }
  else if (line == "HR") {
    // 즉시 상태 리포트
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
  // 1) 직렬 명령 처리 (줄 단위)
  while (Serial.available()) {
    char c = (char)Serial.read();
    if (c == '\n' || c == '\r') {
      if (rxLine.length() > 0) {
        processLine(rxLine);
        rxLine = "";
      }
    } else {
      rxLine += c;
      // 과도한 입력 방지
      if (rxLine.length() > 64) rxLine = "";
    }
  }

  // 2) 주기 센서 읽기 + 제어
  static unsigned long lastMs = 0;
  unsigned long now = millis();
  if (now - lastMs >= 2000) {  // 2초 주기
    lastMs = now;

    float humidity = dht.readHumidity();
    float temperature = dht.readTemperature();

    if (isnan(humidity) || isnan(temperature)) {
      Serial.println(F("Failed to read from DHT sensor !"));
      return;
    }

    handleControl(temperature); // enable + 히스테리시스 반영

    // // 상태 로그(모니터링용)
    // Serial.print(F("Temperature: "));
    // Serial.print(temperature, 1);
    // Serial.print(F(" C, Humidity: "));
    // Serial.print(humidity, 1);
    // Serial.print(F(" %, ENABLE="));
    // Serial.print(hvac_enable ? "1" : "0");
    // Serial.print(F(", STATE="));
    // switch (state) {
    //   case DISABLED: Serial.println(F("DISABLED")); break;
    //   case IDLE:     Serial.println(F("IDLE"));     break;
    //   case COOLING:  Serial.println(F("COOLING"));  break;
    //   case HEATING:  Serial.println(F("HEATING"));  break;
    // }
  }
}
