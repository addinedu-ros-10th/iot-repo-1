// DHT-11 온습도센서 + 3색 LED

#include "DHT.h"

#define DHTPIN 2       // DHT 센서가 연결된 핀 번호
#define DHTTYPE DHT11  // 사용 중인 DHT 센서의 종류 (DHT11)

DHT dht(DHTPIN, DHTTYPE); // DHT 센서 객체 생성

const int R_LED = 3;
const int G_LED = 5;
const int B_LED = 6;

void setup() {
  // put your setup code here, to run once:
  Serial.begin(9600);    // 시리얼 통신
  dht.begin();           // DHT 센서 초기화
  pinMode(R_LED, OUTPUT);  // 히터 
  pinMode(G_LED, OUTPUT);  // 사용 X
  pinMode(B_LED, OUTPUT);  // 에어컨 
}

void loop() {
  // put your main code here, to run repeatedly:
  float humidity = dht.readHumidity();        // 습도 값 읽기
  float temperature = dht.readTemperature(); // 온도 값 읽기

  if (isnan(humidity) || isnan(temperature)) 
  {
    Serial.println("Failed to read from DHT sensor !"); //읽기 실패 -> error
    return;
  }

  if (temperature >= 28)
  {
    digitalWrite(R_LED, LOW);
    digitalWrite(G_LED, LOW);
    digitalWrite(B_LED, HIGH);
  }

  else if (temperature <= 27)
  {
    digitalWrite(R_LED, HIGH);
    digitalWrite(G_LED, LOW);
    digitalWrite(B_LED, LOW);
  }

  else
  {
    // 15 < temperature < 26
    digitalWrite(R_LED, LOW);
    digitalWrite(G_LED, HIGH);
    digitalWrite(B_LED, LOW);
  }

  // 온도와 습도 값을 시리얼 모니터에 출력하기
  Serial.print("Temperature : ");
  Serial.print(temperature, 1);
  Serial.print(" *C, ");
  Serial.print("Humidity: ");
  Serial.print(humidity, 1);
  Serial.println(" %");

  delay(2000);
}
