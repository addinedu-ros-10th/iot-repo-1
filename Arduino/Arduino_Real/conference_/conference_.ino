// 회의실 냉난방시스템 + 조명 + LCD  (AUTO 제거 + 조명=HVAC 동기화판)
// 명령어
//   EN 1|0  -> HVAC 허용 ON/OFF  (조명도 함께 ON/OFF)
//   HR      -> 상태 리포트
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
// 조명 릴레이(또는 표시 LED) 핀
const int LIGHT_PIN = 7;

// === 임계값 ===
float COOL_ON   = 26.0;
float COOL_OFF  = 25.5;
float HUM_ON    = 70.0;
float HUM_OFF   = 65.0;
float HEAT_ON   = 15.0;
float HEAT_OFF  = 15.5;

enum HvacState { DISABLED, IDLE, COOLING, HEATING };
HvacState state = DISABLED;

enum Mode2 { MODE_ON, MODE_OFF };
Mode2 hvac_mode  = MODE_OFF;   // 기본 OFF (체크인 전)

String rxLine;

// 유틸
void setLeds(bool r, bool g, bool b){
  digitalWrite(R_LED, r?HIGH:LOW);
  digitalWrite(G_LED, g?HIGH:LOW);
  digitalWrite(B_LED, b?HIGH:LOW);
}

// 릴레이가 Active-LOW면 HIGH/LOW를 반대로 바꾸세요.
void setLight(bool on){
  digitalWrite(LIGHT_PIN, on?HIGH:LOW);
}

char modeToChar(Mode2 m){
  return (m == MODE_ON) ? '1' : '0';
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

// ---- HVAC 제어 (온도+습도 히스테리시스) ----
void handleHvacControl(float t, float h){
  if(hvac_mode == MODE_OFF){
    applyState(DISABLED);
    return;
  }

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

// ---- 조명 = HVAC와 항상 동기화 ----
void handleLightFollowHvac(){
  setLight(hvac_mode == MODE_ON);
}

// ---- 명령 처리 ----
void processLine(String line){
  line.trim(); if(line.length()==0) return;

  if(line.startsWith("EN")){ // HVAC 허용 ON/OFF (+ 조명 동기)
    int sp=line.indexOf(' ');
    if(sp>0){
      String val=line.substring(sp+1); val.trim();
      if(val=="1"){
        hvac_mode = MODE_ON;
        Serial.println(F("[OK] EN 1 (HVAC=ON, LIGHT=ON)"));
      }else if(val=="0"){
        hvac_mode = MODE_OFF;
        applyState(DISABLED);
        Serial.println(F("[OK] EN 0 (HVAC=OFF, LIGHT=OFF)"));
      }else{
        Serial.println(F("[ERR] EN value must be 1|0"));
      }
    }else{
      Serial.println(F("[ERR] Usage: EN 1|0"));
    }
  }
  else if(line=="HR"){
    float h=dht.readHumidity(), t=dht.readTemperature();
    if(isnan(h)||isnan(t)){ Serial.println(F("[ERR] DHT read failed")); return; }

    bool light_on = (digitalRead(LIGHT_PIN)==HIGH);

    Serial.print(F("TEMP:"));Serial.print(t,1); Serial.print(F("C "));
    Serial.print(F("HUM:")); Serial.print(h,1);  Serial.print(F("% "));
    Serial.print(F("ENABLE:"));Serial.print((hvac_mode!=MODE_OFF) ? "1":"0");
    Serial.print(F(" STATE:"));
    switch(state){
      case DISABLED: Serial.print(F("DISABLED")); break;
      case IDLE:     Serial.print(F("IDLE"));     break;
      case COOLING:  Serial.print(F("COOLING"));  break;
      case HEATING:  Serial.print(F("HEATING"));  break;
    }
    Serial.print(F(" LIGHT:")); Serial.print(light_on ? F("ON") : F("OFF"));
    Serial.print(F(" MODE:"));  Serial.println(modeToChar(hvac_mode));
  }
  else{
    Serial.print(F("[ERR] Unknown cmd: ")); Serial.println(line);
  }
}

void setup(){
  Serial.begin(9600);
  dht.begin();

  pinMode(R_LED,OUTPUT); pinMode(G_LED,OUTPUT); pinMode(B_LED,OUTPUT);
  pinMode(LIGHT_PIN,OUTPUT);
  setLight(false);

  // LCD
  lcd.init();
  lcd.backlight();
  lcd.clear();
  lcd.setCursor(0,0); lcd.print("Room HVAC Ready");
  lcd.setCursor(0,1); lcd.print("Waiting...");

  applyState(DISABLED);
  hvac_mode  = MODE_OFF;

  Serial.println(F("Room HVAC ready. Commands: 'EN 1|0', 'HR'"));
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
    handleLightFollowHvac();

    // LCD 표시
    lcd.setCursor(0, 0);
    lcd.print("Temp:");
    if (!isnan(t)) {
      lcd.print(t, 1);
      lcd.write((uint8_t)223);  // '°'
      lcd.print("C   ");
    } else {
      lcd.print("----      ");
    }

    lcd.setCursor(0, 1);
    lcd.print("Hum :");
    if (!isnan(h)) {
      lcd.print(h, 1);
      lcd.print("%   ");
    } else {
      lcd.print("----      ");
    }

    // // 상태 로그
    // Serial.print(F("T:")); Serial.print(t,1); Serial.print(F("C "));
    // Serial.print(F("H:")); Serial.print(h,1); Serial.print(F("% "));
    // Serial.print(F("EN=")); Serial.print((hvac_mode!=MODE_OFF)?"1":"0");
    // Serial.print(F(" STATE="));
    // switch(state){
    //   case DISABLED: Serial.print(F("DISABLED")); break;
    //   case IDLE:     Serial.print(F("IDLE"));     break;
    //   case COOLING:  Serial.print(F("COOLING"));  break;
    //   case HEATING:  Serial.print(F("HEATING"));  break;
    // }
    // Serial.print(F(" LIGHT=")); Serial.print(digitalWrite,  // dummy to split lines
    //   0); // (No-op to avoid line too long warning in some IDEs)
    // Serial.print(digitalRead(LIGHT_PIN)==HIGH ? F("ON") : F("OFF"));
    // Serial.print(F(" MODE="));  Serial.println(modeToChar(hvac_mode));
  }
}
