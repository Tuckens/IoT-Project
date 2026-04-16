#include <WiFi.h>            
#include <HTTPClient.h>      
#include <DHT.h>
#include "creds.h"

#define DEBUG_MODE    // Commenter pour supprimer les infos de débogage dans le Serial
// #define NOWIFI        // Commenter lors de l'utilisation avec le Raspberry PI

#define PIR 33          

#define DHTPIN  32         
#define DHTTYPE DHT22       

#define DHT_RETRY_DELAY    2500
#define DHT_REINIT_AFTER   5

String pi_hostname = "bpem.local";
DHT dht(DHTPIN, DHTTYPE);

IPAddress serverIP;

void readDHTBlocking(float &temperature, float &humidity)
{
  unsigned int failCount = 0;

  while (true) {
    temperature = dht.readTemperature();
    humidity    = dht.readHumidity();

    if (!isnan(temperature) && !isnan(humidity)) {
      if (failCount > 0) {
        #ifdef DEBUG_MODE
        Serial.print("AM2302 recovered after ");
        Serial.print(failCount);
        Serial.println(" failed attempt(s)");
        #endif
      }
      return;
    }

    failCount++;
    #ifdef DEBUG_MODE
    Serial.print("Failed to read from AM2302! (attempt ");
    Serial.print(failCount);
    Serial.println(")");
    #endif

    if (failCount % DHT_REINIT_AFTER == 0) {
      #ifdef DEBUG_MODE
      Serial.println("Re-initializing AM2302...");
      #endif
      dht.begin();
    }

    delay(DHT_RETRY_DELAY);
  }
}

void setup()
{
  Serial.begin(115200);
  pinMode(PIR, INPUT);

/*---------------------------WIFI SETUP---------------------------*/
#ifdef DEBUG_MODE
  Serial.print("Connecting to ");
  Serial.print(ssid);
#endif

#ifndef NOWIFI
  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) {
    #ifdef DEBUG_MODE
      Serial.print(".");
    #endif
    delay(500);
  }
#endif

#ifdef DEBUG_MODE
  Serial.println("\nConnected!");
  Serial.print("IP Address: ");
  Serial.println(WiFi.localIP());
#endif
/*-----------------------END OF WIFI SETUP------------------------*/

/*---------------------------AM2302 SETUP---------------------------*/
  dht.begin();
  delay(2000);
#ifdef DEBUG_MODE
  Serial.println("AM2302 (DHT22) initialized");
#endif
/*-----------------------END OF AM2302 SETUP-----------------------*/
}

unsigned int count = 0;

WiFiClient wifi;
HTTPClient http;
char buff[200] = "";
char payload[200] = "";

void loop()
{
  float temperature, humidity;
  readDHTBlocking(temperature, humidity);

#ifdef DEBUG_MODE
  Serial.print("Temperature: ");
  Serial.print(temperature);
  Serial.print(" C  Humidity: ");
  Serial.print(humidity);
  Serial.print(" %  Motion: ");
  Serial.println(digitalRead(PIR));
#endif

/*---------------------------mDNS RESOLUTION---------------------------*/
#ifndef NOWIFI
  while(!WiFi.hostByName(pi_hostname.c_str(), serverIP) || serverIP.toString() == "0.0.0.0")
  {
    #ifdef DEBUG_MODE
    Serial.println("DNS failed, retrying...");
    #endif
    delay(1000);
  }

  #ifdef DEBUG_MODE
  Serial.print("Resolved Raspberry Pi IP: ");
  Serial.println(serverIP.toString());
  #endif
#endif
/*-----------------------END OF mDNS RESOLUTION------------------------*/

/*---------------------------HTTP CONNECTION---------------------------*/
#ifndef NOWIFI
  snprintf(buff, sizeof(buff), "http://%s/api/blog/sensor", serverIP.toString().c_str());

#ifdef DEBUG_MODE
  Serial.print("Connecting to ");
  Serial.println(buff);
#endif

  http.begin(wifi, buff);
  http.addHeader("Content-Type", "application/json");

  snprintf(payload, sizeof(payload),
           "{\"id\":%d,\"temp\":%.2f,\"hum\":%.2f,\"pir\":%d,\"user\":\"esp32\",\"token\":\"REDACTED-TOKEN\"}",
           count, temperature, humidity, digitalRead(PIR));

#ifdef DEBUG_MODE
  Serial.println(payload);
#endif

  int httpResponseCode = http.POST((uint8_t*)payload, strlen(payload));
#ifdef DEBUG_MODE
  Serial.print("POST: ");
  Serial.println(httpResponseCode);
#endif
  http.end();
#endif
/*-----------------------END OF HTTP CONNECTION------------------------*/

  count++;
  
  delay(5000); 
}