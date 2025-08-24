// AUTO 모드 추가한거 작동 되나 ? 확인 필요

// 회의실 냉난방시스템 + 조명 + LCD + AUTO 모드 지원
// 명령어
//   EN A|1|0  -> HVAC 모드(AUTO/ON/OFF)
//   EL A|1|0  -> LIGHT 모드(AUTO/ON/OFF)
//   HR        -> 상태 리포트
//
// 냉난방 로직(히스테리시스):
//   (t >= COOL_ON) OR (h >= HUM_ON)        -> 냉방 ON 후보
//   (t <= COOL_OFF) AND (h <= HUM_OFF)     -> 냉방 OFF 후보
//   (t <= HEAT_ON)                         -> 난방 ON 후보
//   (t >= HEAT_OFF)                        -> 난방 OFF 후보

#include "DHT.h"
#define DHTPIN 2
#define DHTTYPE DHT11
DHT dht(DHTPIN, DHTTYPE);

#include <Wire.h>
#include <LiquidCrystal_I2C.h>
LiquidCrystal_I2C lcd(0x27, 16, 2);

// 상태 표시 LED: R=히터, G=쾌적, B=에어컨
const int R_LED = 3, G_LED = 5, B_LED = 6;
// 회의실 점유/허용 표시 LED
const int HVAC_POWER_LED = 7;
// 조명 릴레이(또는 표시 LED) 핀
const int LIGHT_PIN = 8;

// === 히스테리시스 임계값 ===
float COOL_ON   = 26.0;
float COOL_OFF  = 25.5;
float HUM_ON    = 70.0;
float HUM_OFF   = 65.0;
float HEAT_ON   = 15.0;
float HEAT_OFF  = 15.5;

enum HvacState { DISABLED, IDLE, COOLING, HEATING };
HvacState state = DISABLED;

enum Mode3 { MODE_AUTO, MODE_ON, MODE_OFF };
Mode3 hvac_mode = MODE_OFF;   // 기본 OFF (체크인 전)
Mode3 light_mode = MODE_OFF;  // 기본 OFF

String rxLine;

// 유틸
void setLeds(bool r, bool g, bool b){
  digitalWrite(R_LED, r?HIGH:LOW);
  digitalWrite(G_LED, g?HIGH:LOW);
  digitalWrite(B_LED, b?HIGH:LOW);
}

void setLight(bool on){
  digitalWrite(LIGHT_PIN, on?HIGH:LOW);
}

const char* modeToChar(Mode3 m){
  switch(m){
    case MODE_AUTO: return "A";
    case MODE_ON:   return "1";
    case MODE_OFF:  return "0";
  }
  return "?";
}

void applyState(HvacState s){
  state = s;
  switch(s){
    case DISABLED: setLeds(false,false,false); break;
    case IDLE:     setLeds(false,true ,false); break;
    case COOLING:  setLeds(false,false,true ); break;
    case HEATING:  setLeds(true ,false,false); break;
  }
}

// ---- 핵심 제어 로직 (온도 + 습도, OR-ON / AND-OFF) ----
void handleHvacControl(float t, float h){
  if(hvac_mode == MODE_OFF){
    applyState(DISABLED);
    return;
  }

  // MODE_ON은 난방/냉방 강제 작동이 아니라 "HVAC 허용"으로 해석.
  // 실제 COOL/HEAT 선택은 환경 조건으로 결정 (기존 정책 유지).
  bool wantCoolOn  = (t >= COOL_ON) || (h >= HUM_ON);
  bool wantCoolOff = (t <= COOL_OFF) && (h <= HUM_OFF);
  bool wantHeatOn  = (t <= HEAT_ON);
  bool wantHeatOff = (t >= HEAT_OFF);

  switch(state){
    case COOLING:
      if (wantCoolOff) applyState(IDLE);
      else             applyState(COOLING);
      break;
    case HEATING:
      if (wantHeatOff){
        if (wantCoolOn) applyState(COOLING);
        else            applyState(IDLE);
      }else{
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

void handleLightControl(){
  // AUTO 규칙(예시): hvac_mode != OFF (즉 체크인 상태)이면 조명 ON, 아니면 OFF
  if(light_mode == MODE_ON){
    setLight(true);
  }else if(light_mode == MODE_OFF){
    setLight(false);
  }else{ // MODE_AUTO
    bool occupied = (hvac_mode != MODE_OFF);
    setLight(occupied);
  }
}

// ---- 명령 처리 ----
void processLine(String line){
  line.trim(); if(line.length()==0) return;

  if(line.startsWith("EN")){ // HVAC 모드
    int sp=line.indexOf(' ');
    if(sp>0){
      String val=line.substring(sp+1); val.trim();
      if(val=="A" || val=="a"){
        hvac_mode = MODE_AUTO;
        digitalWrite(HVAC_POWER_LED, HIGH);
        Serial.println(F("[OK] EN A (HVAC=AUTO)"));
      }else if(val=="1"){
        hvac_mode = MODE_ON;
        digitalWrite(HVAC_POWER_LED, HIGH);
        Serial.println(F("[OK] EN 1 (HVAC=ON)"));
      }else if(val=="0"){
        hvac_mode = MODE_OFF;
        digitalWrite(HVAC_POWER_LED, LOW);
        applyState(DISABLED);
        Serial.println(F("[OK] EN 0 (HVAC=OFF)"));
      }else{
        Serial.println(F("[ERR] EN value must be A|1|0"));
      }
    }else{
      Serial.println(F("[ERR] Usage: EN A|1|0"));
    }
  }
  else if(line.startsWith("EL")){ // LIGHT 모드
    int sp=line.indexOf(' ');
    if(sp>0){
      String val=line.substring(sp+1); val.trim();
      if(val=="A" || val=="a"){
        light_mode = MODE_AUTO;
        Serial.println(F("[OK] EL A (LIGHT=AUTO)"));
      }else if(val=="1"){
        light_mode = MODE_ON;
        Serial.println(F("[OK] EL 1 (LIGHT=ON)"));
      }else if(val=="0"){
        light_mode = MODE_OFF;
        Serial.println(F("[OK] EL 0 (LIGHT=OFF)"));
      }else{
        Serial.println(F("[ERR] EL value must be A|1|0"));
      }
    }else{
      Serial.println(F("[ERR] Usage: EL A|1|0"));
    }
  }
  else if(line=="HR"){
    float h=dht.readHumidity(), t=dht.readTemperature();
    if(isnan(h)||isnan(t)){ Serial.println(F("[ERR] DHT read failed")); return; }

    // 현재 조명 상태 읽기
    bool light_on = digitalRead(LIGHT_PIN)==HIGH;

    Serial.print(F("TEMP:"));Serial.print(t,1); Serial.print(F("C "));
    Serial.print(F("HUM:")); Serial.print(h,1);  Serial.print(F("% "));
    // ENABLE: HVAC가 OFF가 아니면 1 (GUI 호환)
    Serial.print(F("ENABLE:"));Serial.print((hvac_mode!=MODE_OFF) ? "1":"0");
    Serial.print(F(" STATE:"));
    switch(state){
      case DISABLED: Serial.print(F("DISABLED")); break;
      case IDLE:     Serial.print(F("IDLE"));     break;
      case COOLING:  Serial.print(F("COOLING"));  break;
      case HEATING:  Serial.print(F("HEATING"));  break;
    }
    Serial.print(F(" LIGHT:")); Serial.print(light_on ? F("ON") : F("OFF"));
    Serial.print(F(" MODE:"));  Serial.print(modeToChar(hvac_mode));
    Serial.print(F(" LMODE:")); Serial.println(modeToChar(light_mode));
  }
  else{
    Serial.print(F("[ERR] Unknown cmd: ")); Serial.println(line);
  }
}

void setup(){
  Serial.begin(9600);
  dht.begin();

  pinMode(R_LED,OUTPUT); pinMode(G_LED,OUTPUT); pinMode(B_LED,OUTPUT);
  pinMode(HVAC_POWER_LED,OUTPUT);
  pinMode(LIGHT_PIN,OUTPUT);

  digitalWrite(HVAC_POWER_LED,LOW);
  setLight(false);

  // LCD
  lcd.init();
  lcd.backlight();
  lcd.clear();
  lcd.setCursor(0,0); lcd.print("Room HVAC Ready");
  lcd.setCursor(0,1); lcd.print("Waiting...");

  applyState(DISABLED);
  hvac_mode = MODE_OFF;
  light_mode = MODE_OFF;

  Serial.println(F("Room HVAC ready. Commands: 'EN A|1|0', 'EL A|1|0', 'HR'"));
}

void loop(){
  // 시리얼 수신
  while(Serial.available()){
    char c=(char)Serial.read();
    if(c=='\n'||c=='\r'){
      if(rxLine.length()>0){ processLine(rxLine); rxLine=""; }
    }else{
      rxLine+=c;
      if(rxLine.length()>64) rxLine="";
    }
  }

  // 2초 주기 제어
  static unsigned long lastMs=0;
  unsigned long now=millis();
  if(now-lastMs>=2000){
    lastMs=now;

    float h=dht.readHumidity(), t=dht.readTemperature();
    if(isnan(h)||isnan(t)){
      Serial.println(F("Failed to read from DHT !"));
      return;
    }

    // HVAC / LIGHT 제어
    handleHvacControl(t, h);
    handleLightControl();

    // ======================= LCD 표시 =====================
    lcd.setCursor(0,0); // 1행
    char line1[17];
    snprintf(line1, sizeof(line1), "Temp:%5.1fC   ", t);
    lcd.print(line1);

    lcd.setCursor(0,1); // 2행
    char line2[17];
    snprintf(line2, sizeof(line2), "Hum :%5.1f%%  ", h);
    lcd.print(line2);
    // =====================================================

    // 상태 로그(원하면 주석처리)
    Serial.print(F("T:")); Serial.print(t,1); Serial.print(F("C "));
    Serial.print(F("H:")); Serial.print(h,1); Serial.print(F("% "));
    Serial.print(F("EN=")); Serial.print((hvac_mode!=MODE_OFF)?"1":"0");
    Serial.print(F(" STATE="));
    switch(state){
      case DISABLED: Serial.print(F("DISABLED")); break;
      case IDLE:     Serial.print(F("IDLE"));     break;
      case COOLING:  Serial.print(F("COOLING"));  break;
      case HEATING:  Serial.print(F("HEATING"));  break;
    }
    Serial.print(F(" LIGHT=")); Serial.print(digitalRead(LIGHT_PIN)==HIGH ? F("ON") : F("OFF"));
    Serial.print(F(" MODE="));  Serial.print(modeToChar(hvac_mode));
    Serial.print(F(" LMODE=")); Serial.println(modeToChar(light_mode));
  }
}
