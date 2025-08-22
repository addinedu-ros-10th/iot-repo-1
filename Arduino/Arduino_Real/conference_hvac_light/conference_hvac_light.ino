// 회의실 냉난방시스템 + 조명 (회의실 전용 프로토콜)
//   EN 1  -> 인증 성공(체크인) 시 제어 허용 + 표시LED ON
//   EN 0  -> 관리자/수동 OFF 시 제어 차단 + 표시LED OFF
//   HR    -> 상태 리포트

#include "DHT.h"
#define DHTPIN 2
#define DHTTYPE DHT11
DHT dht(DHTPIN, DHTTYPE);

// 상태 표시 LED: R=히터, G=쾌적, B=에어컨
const int R_LED = 3, G_LED = 5, B_LED = 6;
// 회의실 점유 표시(체크인 성공 시 ON)
const int HVAC_POWER_LED = 7;

bool hvac_enable = false;  // 기본 차단

// 임계값
float COOL_ON=26.0;
float COOL_OFF=25.5;
float HEAT_ON=15.0;
float HEAT_OFF=15.5;

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

void handleControl(float t){
  if(!hvac_enable){ applyState(DISABLED); return; }

  switch(state){
    case COOLING: if(t<=COOL_OFF) applyState(IDLE); else applyState(COOLING); break;
    case HEATING: if(t>=HEAT_OFF) applyState(IDLE); else applyState(HEATING); break;
    case IDLE:
    case DISABLED:
      if(t>=COOL_ON)      applyState(COOLING);
      else if(t<=HEAT_ON) applyState(HEATING);
      else                applyState(IDLE);
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
        digitalWrite(HVAC_POWER_LED, HIGH); // 체크인 성공 → ON
        Serial.println(F("[OK] EN 1 (enable=true)"));
      }else if(val=="0"){
        hvac_enable=false;
        digitalWrite(HVAC_POWER_LED, LOW);  // 수동 OFF → OFF
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
    Serial.print(F("TEMP:"));Serial.print(t,1);
    Serial.print(F("C HUM:"));Serial.print(h,1);
    Serial.print(F("% ENABLE:"));Serial.print(hvac_enable?"1":"0");
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
  applyState(DISABLED);
  Serial.println(F("Room HVAC ready. Commands: 'EN 1', 'EN 0', 'HR'"));
}

void loop(){
  while(Serial.available()){
    char c=(char)Serial.read();
    if(c=='\n'||c=='\r'){
      if(rxLine.length()>0){ processLine(rxLine); rxLine=""; }
    }else{
      rxLine+=c;
      if(rxLine.length()>64) rxLine="";
    }
  }

  static unsigned long lastMs=0;
  unsigned long now=millis();
  if(now-lastMs>=2000){
    lastMs=now;
    float h=dht.readHumidity(), t=dht.readTemperature();
    if(isnan(h)||isnan(t)){ Serial.println(F("Failed to read from DHT !")); return; }
    handleControl(t);
  }
}
