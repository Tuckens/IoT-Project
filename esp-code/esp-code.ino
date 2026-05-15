#include <WiFi.h>
#include <HTTPClient.h>
#include <DHT.h>
#include "creds.example.h"

#define DEBUG_MODE // Comment to mute Serial debug output
//#define NOWIFI   // Comment when using with the Raspberry Pi

#define PIR 33



String pi_hostname = "bpem.local";
DHT dht(32, DHT22);   //PIN, TYPE

IPAddress serverIP;


/*----------------------------------------------------------------------*/
/*--------------------------------SETUP---------------------------------*/
/*----------------------------------------------------------------------*/


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
  while (WiFi.status() != WL_CONNECTED)
  {
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




/*----------------------------------------------------------------------*/
/*---------------------------------LOOP---------------------------------*/
/*----------------------------------------------------------------------*/

WiFiClient wifi;
HTTPClient http;
char buff[200] = "";
char payload[200] = "";
unsigned int msid=0;
float temperature, humidity;


void loop()
{

/*---------------------READ TEMPERATURE AND HUMIDITY---------------------*/
  
  do{
  temperature = dht.readTemperature();
  humidity = dht.readHumidity();
  }while(isnan(temperature)&&isnan(humidity));

#ifdef DEBUG_MODE
  Serial.print("Temperature[C]: ");
  Serial.print(temperature);
  Serial.print(" Humidity[%]: ");
  Serial.print(humidity);
  Serial.print(" Motion: ");
  Serial.println(digitalRead(PIR));
#endif

/*------------------------END OF TEMP READING---------------------------*/


/*---------------------------mDNS RESOLUTION---------------------------*/
#ifndef NOWIFI
  while (!WiFi.hostByName(pi_hostname.c_str(), serverIP) || serverIP.toString() == "0.0.0.0")
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

  // Build the payload and include the shared secret.
  snprintf(payload, sizeof(payload),
           "{\"id\":%d,\"temp\":%.2f,\"hum\":%.2f,\"pir\":%d,\"secret\":\"%s\"}",
           msid, temperature, humidity, digitalRead(PIR), esp_secret);

  http.begin(wifi, buff);
  http.addHeader("Content-Type", "application/json");

#ifdef DEBUG_MODE
  Serial.println(payload);
#endif
/*-----------------------END OF HTTP CONNECTION------------------------*/


/*----------------------------HTTP REQUEST----------------------------*/

  int httpResponseCode = http.POST((uint8_t *)payload, strlen(payload));
#ifdef DEBUG_MODE
  Serial.print("POST: ");
  Serial.println(httpResponseCode);
#endif
  http.end(); 
#endif

/*-------------------------END OF HTTP REQUEST-------------------------*/
  msid++;
  delay(1000);
}
