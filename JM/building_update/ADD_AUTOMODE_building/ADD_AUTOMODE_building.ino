// LCD 추가 + AUTO 모드 지원 버전
// 건물 전체 냉난방시스템 + 조명시스템 (LCD 표시 포함)
//
// Serial Commands:
//   HE A -> AUTO (enable HVAC auto control; light auto = state!=DISABLED)
//   HE 1 -> FIRST IN 이후 (enable HVAC & light ON)
//   HE 0 -> LAST OUT 이후  (disable HVAC & light OFF)
//   HR   -> 상태 요청 (온습도, ENABLE, STATE, LIGHT, MODE)
//
// HVAC 로직은 온습도 히스테리시스로 자동 결정됩니다.

#include "DHT.h"
#include <Wire.h>
#include <LiquidCrystal_I2C.h>
#include <string.h>

#define DHTPIN 2
#define DHTTYPE DHT11
DHT dht(DHTPIN, DHTTYPE);

// LCD: I2C 주소 0x27(일반적). 보드에 따라 0x3F일 수도 있음.
LiquidCrystal_I2C lcd(0x27, 16, 2);

// HVAC 상태 LED: R=HEATING, G=IDLE, B=COOLING
const int R_LED = 3;
const int G_LED = 5;
const int B_LED = 6;

// 조명 릴레이/LED 핀
const int LIGHT_PIN = 7;

// 히스테리시스 임계값
float COOL_ON  = 26.0;
float COOL_OFF = 25.5;
float HUM_ON   = 70.0;
float HUM_OFF  = 65.0;
float HEAT_ON  = 15.0;
float HEAT_OFF = 15.5;

enum HvacState { DISABLED, IDLE, COOLING, HEATING };
HvacState state = DISABLED;

enum Mode3 { MODE_AUTO, MODE_ON, MODE_OFF };
Mode3 hvac_mode = MODE_OFF;    // 기본: OFF
bool  light_enable = false;    // 현재 물리 조명 상태

String rxLine;

// ---------- 유틸 ----------
void setLeds(bool r, bool g, bool b) {
  digitalWrite(R_LED, r ? HIGH : LOW);
  digitalWrite(G_LED, g ? HIGH : LOW);
  digitalWrite(B_LED, b ? HIGH : LOW);
}

void setLight(bool on) {
  light_enable = on;
  // 릴레이가 LOW=ON 타입이면 아래 한 줄 반대로 바꾸세요.
  digitalWrite(LIGHT_PIN, on ? HIGH : LOW);
}

const char* modeToChar(Mode3 m){
  switch(m){
    case MODE_AUTO: return "A";
    case MODE_ON:   return "1";
    case MODE_OFF:  return "0";
  }
  return "?";
}

const char* hvacLabel(HvacState s) {
  switch (s) {
    case DISABLED: return "DISA";
    case IDLE:     return "IDLE";
    case COOLING:  return "COOL";
    case HEATING:  return "HEAT";
  }
  return "????";
}

void applyState(HvacState s) {
  state = s;
  switch (s) {
    case DISABLED: setLeds(false, false, false); break;
    case IDLE:     setLeds(false, true,  false); break;
    case COOLING:  setLeds(false, false, true ); break;
    case HEATING:  setLeds(true,  false, false); break;
  }
}

// ---------- 제어 로직 ----------
void handleHvac(float t, float h) {
  if (hvac_mode == MODE_OFF) { applyState(DISABLED); return; }

  bool wantCoolOn  = (t >= COOL_ON) || (h >= HUM_ON);
  bool wantCoolOff = (t <= COOL_OFF) && (h <= HUM_OFF);
  bool wantHeatOn  = (t <= HEAT_ON);
  bool wantHeatOff = (t >= HEAT_OFF);

  switch (state) {
    case COOLING:
      if (wantCoolOff) applyState(IDLE);
      else             applyState(COOLING);
      break;
    case HEATING:
      if (wantHeatOff) {
        if (wantCoolOn) applyState(COOLING);
        else            applyState(IDLE);
      } else {
        applyState(HEATING);
      }
      break;
    case IDLE:
    case DISABLED:
      if (wantCoolOn)      applyState(COOLING);
      else if (wantHeatOn) applyState(HEATING);
      else                 applyState(IDLE);
      break;
  }
}

void handleLightAuto(){
  // AUTO 규칙: state가 DISABLED가 아니면 ON, 아니면 OFF
  bool on = (state != DISABLED);
  setLight(on);
}

// ---------- LCD ----------
void drawLCD(float t, float h) {
  // 1행: "T:25.3C H:55%"
  char line1[17];
  snprintf(line1, sizeof(line1), "T:%5.1fC H:%-3.0f%%", t, h); // 16자 맞춤
  lcd.setCursor(0,0); lcd.print(line1);
  int len1 = strlen(line1); for (int i=len1; i<16; ++i) lcd.print(' ');

  // 2행: "HVAC:COOL L:ON"
  char line2[17];
  snprintf(line2, sizeof(line2), "HVAC:%-4s L:%s", hvacLabel(state), light_enable ? "ON " : "OFF");
  lcd.setCursor(0,1); lcd.print(line2);
  int len2 = strlen(line2); for (int i=len2; i<16; ++i) lcd.print(' ');
}

// ---------- 시리얼 출력 ----------
void printStatus(float t, float h) {
  Serial.print(F("TEMP:")); Serial.print(t, 1);
  Serial.print(F("C HUM:")); Serial.print(h, 1);
  Serial.print(F("% ENABLE:")); Serial.print((hvac_mode != MODE_OFF) ? "1" : "0");
  Serial.print(F(" STATE:"));
  switch (state) {
    case DISABLED: Serial.print(F("DISABLED")); break;
    case IDLE:     Serial.print(F("IDLE"));     break;
    case COOLING:  Serial.print(F("COOLING"));  break;
    case HEATING:  Serial.print(F("HEATING"));  break;
  }
  Serial.print(F(" LIGHT:")); Serial.print(light_enable ? F("ON") : F("OFF"));
  Serial.print(F(" MODE:"));  Serial.println(modeToChar(hvac_mode));
}

// ---------- 명령 처리 ----------
void processLine(String line) {
  line.trim();
  if (line.length() == 0) return;

  if (line.startsWith("HE")) {
    int sp = line.indexOf(' ');
    if (sp > 0) {
      String val = line.substring(sp + 1); val.trim();
      if (val == "A" || val == "a") {
        hvac_mode = MODE_AUTO;
        // AUTO: HVAC 허용 + 조명 자동
        Serial.println(F("[OK] HE A (HVAC=AUTO, light=auto)"));
      } else if (val == "1") {
        hvac_mode = MODE_ON;
        // ON: HVAC 허용 + 조명 ON
        setLight(true);
        Serial.println(F("[OK] HE 1 (HVAC=ON, light=ON)"));
      } else if (val == "0") {
        hvac_mode = MODE_OFF;
        // OFF: HVAC 차단 + 조명 OFF
        applyState(DISABLED);
        setLight(false);
        Serial.println(F("[OK] HE 0 (HVAC=OFF, light=OFF)"));
      } else {
        Serial.println(F("[ERR] HE value must be A|1|0"));
      }
    } else {
      Serial.println(F("[ERR] Usage: HE A|1|0"));
    }
  }
  else if (line == "HR") {
    float h = dht.readHumidity();
    float t = dht.readTemperature();
    if (isnan(h) || isnan(t)) { Serial.println(F("[ERR] DHT read failed")); return; }
    printStatus(t, h);
    // HR 요청 시 LCD도 최신값으로 갱신
    drawLCD(t, h);
  }
  else {
    Serial.print(F("[ERR] Unknown cmd: ")); Serial.println(line);
  }
}

// ---------- 기본 루프 ----------
void setup() {
  Serial.begin(9600);
  dht.begin();

  pinMode(R_LED, OUTPUT);
  pinMode(G_LED, OUTPUT);
  pinMode(B_LED, OUTPUT);
  pinMode(LIGHT_PIN, OUTPUT);

  // LCD 초기화
  lcd.init();
  lcd.backlight();
  lcd.clear();
  lcd.setCursor(0,0); lcd.print("HVAC+LIGHT Ready");
  lcd.setCursor(0,1); lcd.print("Waiting...");

  applyState(DISABLED);
  hvac_mode = MODE_OFF;
  setLight(false);

  Serial.println(F("HVAC+LIGHT ready. Cmd: 'HE A|1|0', 'HR'"));
}

void loop() {
  // 1) 직렬 명령 처리
  while (Serial.available()) {
    char c = (char)Serial.read();
    if (c == '\n' || c == '\r') {
      if (rxLine.length() > 0) { processLine(rxLine); rxLine = ""; }
    } else {
      rxLine += c;
      if (rxLine.length() > 64) rxLine = "";
    }
  }

  // 2) 주기 센서 읽기 + 제어 + LCD 표시
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

    // HVAC 제어
    handleHvac(t, h);

    // LIGHT 제어
    if (hvac_mode == MODE_AUTO) {
      handleLightAuto();
    }
    // MODE_ON은 setLight(true)가 명령 시점에 이미 적용됨
    // MODE_OFF는 setLight(false) 적용됨

    // LCD 갱신
    drawLCD(t, h);
  }
}
