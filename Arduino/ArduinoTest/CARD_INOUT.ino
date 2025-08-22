// RFID 태그 읽어오기
#include <SPI.h>
#include <MFRC522.h>

// SS(Slave Selector)핀 및 reset 핀 번호 정의
#define SS_PIN 10
#define RST_PIN 9

// MFRC522 클래스로 rfid 객체 선언
MFRC522 rfid(SS_PIN, RST_PIN);

// 등록 할 태그 ID 배열
int tagId[4] = {62, 235, 67, 6};

// LED 연결 핀 번호
int red = 5, blue = 6;

void setup() {
  // 시리얼 통신 및 SPI 초기화
  Serial.begin(9600);
  SPI.begin();

  // MFRC522 초기화
  rfid.PCD_Init();

  // LED 핀 모드
  pinMode(red, OUTPUT);
  pinMode(blue, OUTPUT);
}

void loop() {
  // 태그가 접촉 되지 않았거니 ID가 읽혀지지 않을 때
  if(!rfid.PICC_IsNewCardPresent() || !rfid.PICC_ReadCardSerial()) {
    digitalWrite(blue, LOW);
    digitalWrite(red, LOW);
    
    delay(300);
    return;
  }
  int same = 0;
  // 태그의 ID 출력하기(rfid.uid.uidByte[0] ~ frid.uid.uidByte[3] 출력)
  Serial.print("Card Tag ID: ");
  for(byte i=0; i<4; i++){
    Serial.print(rfid.uid.uidByte[i]);
    Serial.print(" ");

    // 인식된 태그와 등록된 태그 번호 일치 여부
    if(rfid.uid.uidByte[i] == tagId[i]) {
      same++; //모두 맞다면 same  변수가 4가 됌
    }
  }
  Serial.println();
  if(same == 4) {
    Serial.println("태그 ID가 일치합니다.(파란LED ON)");
    digitalWrite(blue, HIGH);
    digitalWrite(red, LOW);
    delay(1000);
  } else {
  Serial.println("등록된 태그 ID가 아닙니다.(빨간LED ON)");
  digitalWrite(blue, LOW);
  digitalWrite(red, HIGH);
  delay(1000);
}
}
