int red = 5;   // 회의실 조명LED (인증 + 상태)
int blue = 4;  // 회의실 사용 여부 LED

String authCode = "";      // 마지막으로 사용한 인증번호
bool roomInUse = false;    // 회의실 사용 상태

void setup() {
  Serial.begin(9600);

  pinMode(red, OUTPUT);
  pinMode(blue, OUTPUT);
  digitalWrite(red, LOW);
  digitalWrite(blue, LOW);

  Serial.println("회의실 제어 시스템 준비 완료");
}

void loop() {
  if (Serial.available()) {
    String msg = Serial.readStringUntil('\n');
    msg.trim();

    Serial.print("수신된 명령: [");
    Serial.print(msg);
    Serial.println("]");

    // 숫자 4자리만 인증번호로 처리
    if (msg.length() == 4 && isDigit(msg[0]) && isDigit(msg[1]) && isDigit(msg[2]) && isDigit(msg[3])) {
        Serial.print("입력 인증번호: ");
        Serial.println(msg);

        if (!roomInUse) {
          // 회의실 비사용 → 인증 성공, 사용 시작
          authCode = msg;           // 인증번호 저장
          roomInUse = true;
          digitalWrite(red, HIGH);
          digitalWrite(blue, HIGH);
          Serial.println("인증 성공 회의실 사용 시작");
        } else {
          // 회의실 사용 중 → 같은 번호 입력 시 종료
          if (msg == authCode) {
            roomInUse = false;
            digitalWrite(red, LOW);
            digitalWrite(blue, LOW);
            Serial.println("인증 성공 회의실 사용 종료");
          } else {
            Serial.println("인증 실패");
          }
        }
    }

    else {
      Serial.print("비밀번호 다시 확인 바람. ");
      Serial.println(msg);
    }
  }
}