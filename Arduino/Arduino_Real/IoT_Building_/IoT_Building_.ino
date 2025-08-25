// 건물 전체 냉난방시스템 + 조명시스템 (LCD 표시 포함)
//
// Serial Commands:
//   HE 1 -> FIRST IN 이후 (HVAC 허용 + LIGHT ON)
//   HE 0 -> LAST OUT 이후  (HVAC 차단 + LIGHT OFF)
//   HR   -> 상태 요청 (온습도, ENABLE, STATE, LIGHT, MODE)
//

#include "DHT.h"
#include <Wire.h>
#include <LiquidCrystal_I2C.h>
#include <string.h>
#include <math.h>

#define DHTPIN 2
#define DHTTYPE DHT11
DHT dht(DHTPIN, DHTTYPE);

LiquidCrystal_I2C lcd(0x27, 16, 2);

// HVAC 상태 LED: R=HEATING, G=IDLE, B=COOLING
const int R_LED = 3;
const int G_LED = 5;
const int B_LED = 6;

// 조명 LED 핀
const int LIGHT_PIN = 7;

// 임계값
float COOL_ON  = 26.0;
float COOL_OFF = 25.5;
float HUM_ON   = 70.0;
float HUM_OFF  = 65.0;
float HEAT_ON  = 15.0;
float HEAT_OFF = 15.5;

enum HvacState { DISABLED, IDLE, COOLING, HEATING };
HvacState state = DISABLED;

enum Mode2 { MODE_ON, MODE_OFF };
Mode2 hvac_mode = MODE_OFF;    // 기본: OFF
bool  light_enable = false;    // 현재 조명 상태

String rxLine;


void setLeds(bool r, bool g, bool b) {
  digitalWrite(R_LED, r ? HIGH : LOW);
  digitalWrite(G_LED, g ? HIGH : LOW);
  digitalWrite(B_LED, b ? HIGH : LOW);
}

void setLight(bool on) {
  light_enable = on;
  digitalWrite(LIGHT_PIN, on ? HIGH : LOW);
}

const char* modeToChar(Mode2 m){
  switch(m)
  {
    case MODE_ON:  return "1";
    case MODE_OFF: return "0";
  }
  return "?";
}

const char* hvacLabel(HvacState s) {
  switch (s) 
  {
    case DISABLED: return "DISA";
    case IDLE:     return "IDLE";
    case COOLING:  return "COOL";
    case HEATING:  return "HEAT";
  }
  return "????";
}

void applyState(HvacState s) {
  state = s;
  switch (s) 
  {
    case DISABLED: setLeds(false, false, false); break;
    case IDLE:     setLeds(false, true,  false); break;
    case COOLING:  setLeds(false, false, true ); break;
    case HEATING:  setLeds(true,  false, false); break;
  }
}

// ---------- 제어 로직 ----------
void handleHvac(float t, float h) {
  if (hvac_mode == MODE_OFF) 
  { 
    applyState(DISABLED); return; 
  }

  bool wantCoolOn  = (t >= COOL_ON) || (h >= HUM_ON);
  bool wantCoolOff = (t <= COOL_OFF) && (h <= HUM_OFF);
  bool wantHeatOn  = (t <= HEAT_ON);
  bool wantHeatOff = (t >= HEAT_OFF);

  switch (state) 
  {
    case COOLING:
      if (wantCoolOff) applyState(IDLE);
      else             applyState(COOLING);
      break;
    case HEATING:
      if (wantHeatOff) 
      {
        if (wantCoolOn) applyState(COOLING);
        else            applyState(IDLE);
      } 
      else 
      {
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

// ---------- LCD ----------
void drawLCD(float t, float h) {
  // 1행: T:25.3°C H:55%
  lcd.setCursor(0, 0);
  lcd.print("T:");
  if (!isnan(t)) 
  {
    lcd.print(t, 1);
    lcd.write((uint8_t)223);  // °
    lcd.print("C ");
  } 
  else 
  {
    lcd.print("--.-"); lcd.write((uint8_t)223); lcd.print("C ");
  }

  lcd.print("H:");
  if (!isnan(h)) 
  {
    lcd.print((int)round(h));
    lcd.print("%");
  } 
  else 
  {
    lcd.print("---%");
  }
  lcd.print("   "); // 잔상 지움

  // 2행: HVAC:COOL L:ON
  lcd.setCursor(0, 1);
  lcd.print("HVAC:");
  lcd.print(hvacLabel(state));
  lcd.print(" L:");
  lcd.print(light_enable ? "ON " : "OFF");
  lcd.print("   ");
}

// ---------- 시리얼 출력 ----------
void printStatus(float t, float h) {
  Serial.print(F("TEMP:")); Serial.print(t, 1);
  Serial.print(F("C HUM:")); Serial.print(h, 1);
  Serial.print(F("% ENABLE:")); Serial.print((hvac_mode == MODE_ON) ? "1" : "0");
  Serial.print(F(" STATE:"));
  switch (state) 
  {
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

  if (line.startsWith("HE")) 
  {
    int sp = line.indexOf(' ');
    if (sp > 0) 
    {
      String val = line.substring(sp + 1); val.trim();
      if (val == "1") 
      {
        hvac_mode = MODE_ON;
        setLight(true);                // 조명 ON
        Serial.println(F("[OK] HE 1 (HVAC=ON, light=ON)"));
      } 
      else if (val == "0") 
      {
        hvac_mode = MODE_OFF;
        applyState(DISABLED);          // HVAC 차단
        setLight(false);               // 조명 OFF
        Serial.println(F("[OK] HE 0 (HVAC=OFF, light=OFF)"));
      } 
      else 
      {
        Serial.println(F("[ERR] HE value must be 1|0"));
      }
    } 
    else 
    {
      Serial.println(F("[ERR] Usage: HE 1|0"));
    }
  }
  else if (line == "HR") 
  {
    float h = dht.readHumidity();
    float t = dht.readTemperature();
    if (isnan(h) || isnan(t)) { Serial.println(F("[ERR] DHT read failed")); return; }
    printStatus(t, h);
    drawLCD(t, h);
  }
  else 
  {
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

  lcd.init();
  lcd.backlight();
  lcd.clear();
  lcd.setCursor(0,0); lcd.print("HVAC+LIGHT Ready");
  lcd.setCursor(0,1); lcd.print("Use HE 1/0, HR");

  applyState(DISABLED);
  hvac_mode = MODE_OFF;
  setLight(false);

  Serial.println(F("HVAC+LIGHT ready. Cmd: 'HE 1|0', 'HR'"));
}

void loop() {
  // 1) 직렬 명령 처리
  while (Serial.available()) 
  {
    char c = (char)Serial.read();
    if (c == '\n' || c == '\r') 
    {
      if (rxLine.length() > 0) { processLine(rxLine); rxLine = ""; }
    } 
    else 
    {
      rxLine += c;
      if (rxLine.length() > 64) rxLine = "";
    }
  }

  // 2) 2초마다 센서 읽고 HVAC 상태 결정 (ON일 때만 동작)
  static unsigned long lastMs = 0;
  unsigned long now = millis();
  if (now - lastMs >= 2000) 
  {
    lastMs = now;

    float h = dht.readHumidity();
    float t = dht.readTemperature();
    if (isnan(h) || isnan(t)) 
    {
      Serial.println(F("Failed to read from DHT sensor !"));
      return;
    }

    handleHvac(t, h);  // MODE_OFF면 내부에서 DISABLED로 정리

    // 조명은 명령 시점에 이미 ON/OFF 확정 (HE 1/0)
    drawLCD(t, h);
  }
}
