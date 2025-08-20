#include <SPI.h>
#include <MFRC522.h>

const int RST_PIN = 9;
const int SS_PIN  = 10;
MFRC522 rc522(SS_PIN, RST_PIN);

byte lastUID[4] = {0};
unsigned long lastSentMs = 0;
const unsigned long RESEND_INTERVAL_MS = 2000; // 같은 카드 재전송 최소 간격

void setup() {
  Serial.begin(9600);
  SPI.begin();
  rc522.PCD_Init();
}

bool readCardOnce(byte outUID[4]) {
  if (!rc522.PICC_IsNewCardPresent()) return false;
  if (!rc522.PICC_ReadCardSerial())   return false;

  // UID 복사
  for (byte i = 0; i < rc522.uid.size && i < 4; i++) outUID[i] = rc522.uid.uidByte[i];

  // 카드 통신 종료 (안정화)
  rc522.PICC_HaltA();
  rc522.PCD_StopCrypto1();
  return true;
}

void printUIDLine(const byte uid[4]) {
  // "UID a20df603" 형태로 한 줄 전송
  char hexbuf[9]; // 8자리 + null
  for (int i = 0; i < 4; i++) {
    sprintf(&hexbuf[i*2], "%02x", uid[i]);
  }
  Serial.print("UID ");
  Serial.println(hexbuf);
}

bool isSameUID(const byte a[4], const byte b[4]) {
  for (int i = 0; i < 4; i++) if (a[i] != b[i]) return false;
  return true;
}

void loop() {
  byte uid[4] = {0};

  if (readCardOnce(uid)) {
    unsigned long now = millis();

    // 같은 UID가 연속으로 찍힐 때, 최소 간격을 두고 재전송
    if (!isSameUID(uid, lastUID) || (now - lastSentMs) >= RESEND_INTERVAL_MS) {
      printUIDLine(uid);
      memcpy(lastUID, uid, 4);
      lastSentMs = now;
    }
  }

  // 과도한 폴링 방지
  delay(10);
}

