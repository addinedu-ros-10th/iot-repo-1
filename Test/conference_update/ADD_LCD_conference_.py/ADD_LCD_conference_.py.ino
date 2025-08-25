// LCD 디스플레이 모듈 추가까지

// 회의실 냉난방시스템 + 조명 (회의실 전용 프로토콜)
//   EN 1  -> 인증 성공(체크인) 시 제어 허용 + 표시LED ON
//   EN 0  -> 관리자/수동 OFF 시 제어 차단 + 표시LED OFF
//   HR    -> 상태 리포트
//
// 조건: (t >= COOL_ON) 또는 (h >= HUM_ON) 이면 냉방 ON
//       (t <= COOL_OFF) AND (h <= HUM_OFF) 이면 냉방 OFF
//       (t <= HEAT_ON) 이면 난방 ON, (t >= HEAT_OFF) 이면 난방 OFF

#include "DHT.h"
#define DHTPIN 2
#define DHTTYPE DHT11
DHT dht(DHTPIN, DHTTYPE);

#include <Wire.h>
#include <LiquidCrystal_I2C.h>
LiquidCrystal_I2C lcd(0x27, 16, 2);

// 상태 표시 LED: R=히터, G=쾌적, B=에어컨
const int R_LED = 3, G_LED = 5, B_LED = 6;
// 회의실 점유 표시(체크인 성공 시 ON)
const int HVAC_POWER_LED = 7;

bool hvac_enable = false;  // 기본 차단

// === 히스테리시스 임계값 ===
float COOL_ON   = 26.0;  // 이 이상이면 냉방 켜기
float COOL_OFF  = 25.5;  // 이 이하면 냉방 끄기 후보(습도도 HUM_OFF 이하일 때 최종 OFF)
float HUM_ON    = 70.0;  // 이 이상이면 냉방 켜기(제습 목적)
float HUM_OFF   = 65.0;  // 이 이하면 냉방 끄기 후보(온도도 COOL_OFF 이하일 때 최종 OFF)

float HEAT_ON   = 15.0;  // 이 이하면 난방 켜기
float HEAT_OFF  = 15.5;  // 이 이상이면 난방 끄기

enum HvacState { DISABLED, IDLE, COOLING, HEATING };
HvacState state = DISABLED;

String rxLine;

void setLeds(bool r, bool g, bool b){
  digitalWrite(R_LED, r?HIGH:LOW);
  digitalWrite(G_LED, g?HIGH:LOW);
  digitalWrite(B_LED, b?HIGH:LOW);
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
void handleControl(float t, float h){
  if(!hvac_enable){ applyState(DISABLED); return; }

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

void processLine(String line){
  line.trim(); if(line.length()==0) return;

  if(line.startsWith("EN")){
    int sp=line.indexOf(' ');
    if(sp>0){
      String val=line.substring(sp+1); val.trim();
      if(val=="1"){
        hvac_enable=true;
        digitalWrite(HVAC_POWER_LED, HIGH);
        Serial.println(F("[OK] EN 1 (enable=true)"));
      }else if(val=="0"){
        hvac_enable=false;
        digitalWrite(HVAC_POWER_LED, LOW);
        applyState(DISABLED);
        Serial.println(F("[OK] EN 0 (enable=false)"));
      }else{
        Serial.println(F("[ERR] EN value must be 0 or 1"));
      }
    }else{
      Serial.println(F("[ERR] Usage: EN 0|1"));
    }
  }
  else if(line=="HR"){
    float h=dht.readHumidity(), t=dht.readTemperature();
    if(isnan(h)||isnan(t)){ Serial.println(F("[ERR] DHT read failed")); return; }

    Serial.print(F("TEMP:"));Serial.print(t,1); Serial.print(F("C "));
    Serial.print(F("HUM:")); Serial.print(h,1);  Serial.print(F("% "));
    Serial.print(F("ENABLE:"));Serial.print(hvac_enable?"1":"0");
    Serial.print(F(" STATE:"));
    switch(state){
      case DISABLED: Serial.println(F("DISABLED")); break;
      case IDLE:     Serial.println(F("IDLE"));     break;
      case COOLING:  Serial.println(F("COOLING"));  break;
      case HEATING:  Serial.println(F("HEATING"));  break;
    }
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
  digitalWrite(HVAC_POWER_LED,LOW);

  // LCD
  lcd.init();
  lcd.backlight();
  lcd.clear();
  lcd.setCursor(0,0);
  lcd.print("Room HVAC Ready");
  lcd.setCursor(0,1);
  lcd.print("Waiting...");

  applyState(DISABLED);
  Serial.println(F("Room HVAC ready. Commands: 'EN 1', 'EN 0', 'HR'"));
  Serial.println(F("Cooling: t>=COOL_ON OR h>=HUM_ON; Off when t<=COOL_OFF AND h<=HUM_OFF"));
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
    if(isnan(h)||isnan(t)){ Serial.println(F("Failed to read from DHT !")); return; }
    handleControl(t, h);

    // ======================= LCD 표시 =====================
    lcd.setCursor(0,0); // 1행
    char line1[17];
    snprintf(line1, sizeof(line1), "Temp:%5.1fc      ", t);
    lcd.print(line1);

    lcd.setCursor(0,1); // 2행
    char line2[17];
    snprintf(line2, sizeof(line2). "Hum :%5.1f%%      ", h);
    lcd.print(line2);
    // ============================================

    // 상태 로그(원하면 주석처리)
    Serial.print(F("T:")); Serial.print(t,1); Serial.print(F("C "));
    Serial.print(F("H:")); Serial.print(h,1); Serial.print(F("% "));
    Serial.print(F("EN=")); Serial.print(hvac_enable?"1":"0");
    Serial.print(F(" STATE="));
    switch(state){
      case DISABLED: Serial.println(F("DISABLED")); break;
      case IDLE:     Serial.println(F("IDLE"));     break;
      case COOLING:  Serial.println(F("COOLING"));  break;
      case HEATING:  Serial.println(F("HEATING"));  break;
    }
  }
}
