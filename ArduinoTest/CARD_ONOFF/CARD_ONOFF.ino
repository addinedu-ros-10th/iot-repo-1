// 빨간 LED 핀
int red = 5;

void setup() {
  Serial.begin(9600);       // 시리얼 통신 시작
  pinMode(red, OUTPUT);     // 빨간 LED
  digitalWrite(red, LOW);
}

void loop() {
  // 시리얼로 들어온 데이터가 있으면
  if (Serial.available() > 0) {
    String data = Serial.readStringUntil('\n'); // 줄 끝까지 읽기

    // FIRST_IN 또는 IN → LED 켜기
    if (data == "FIRST_IN" || data == "IN") {
      digitalWrite(red, HIGH);
      Serial.println("빨간 LED ON (" + data + " 수신)");
    } 
    // LAST_OUT → LED 끄기
    else if (data == "LAST_OUT") {
      digitalWrite(red, LOW);
      Serial.println("빨간 LED OFF (LAST_OUT 수신)");
    } 
    // 그 외의 데이터 → 알 수 없는 명령
    else {
      Serial.print("알 수 없는 명령: ");
      Serial.println(data);
    }
  }
}
