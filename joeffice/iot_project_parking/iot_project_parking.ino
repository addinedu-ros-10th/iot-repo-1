// Arduino Servo Gate Controller (pulse version)
#include <Servo.h>

Servo gate;
const int SERVO_PIN   = 9;     // 서보 핀
const int OPEN_ANGLE  = 90;    // 열린 각도
const int CLOSE_ANGLE = 0;     // 닫힌 각도

// 펄스 동작 시간(ms)
const unsigned long OPEN_HOLD_MS = 800;   // 얼마나 열어둘지
const unsigned long SETTLE_MS    = 200;   // 닫은 뒤 안정화 시간

void setup() {
  Serial.begin(9600);
  gate.attach(SERVO_PIN);
  gate.write(CLOSE_ANGLE); // 초기 닫힘
}

String buf;

void doPulse() {
  // 항상 '열고 → 닫기'로 확실한 동작
  gate.write(OPEN_ANGLE);
  delay(OPEN_HOLD_MS);
  gate.write(CLOSE_ANGLE);
  delay(SETTLE_MS);
}

void loop() {
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n' || c == '\r') {
      if (buf.length() > 0) {
        buf.trim();

        if (buf == "OPEN") {
          doPulse();
          Serial.println("OK OPEN");
        } else if (buf == "CLOSE") {
          gate.write(CLOSE_ANGLE);
          Serial.println("OK CLOSE");
        } else if (buf.startsWith("ANGLE ")) {
          int ang = buf.substring(6).toInt();
          ang = constrain(ang, 0, 180);
          gate.write(ang);
          Serial.println("OK ANGLE");
        } else if (buf.startsWith("PULSE ")) {
          // PULSE 1000 같이 쓰면 열림 유지 시간을 바꿀 수 있음
          int ms = buf.substring(6).toInt();
          if (ms < 100) ms = 100;
          gate.write(OPEN_ANGLE);
          delay(ms);
          gate.write(CLOSE_ANGLE);
          delay(SETTLE_MS);
          Serial.println("OK PULSE");
        } else {
          Serial.println("ERR");
        }

        buf = "";
      }
    } else {
      buf += c;
    }
  }
}
