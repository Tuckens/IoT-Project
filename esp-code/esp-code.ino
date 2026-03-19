#include  <Adafruit_BMP280.h>
#include <ESP8266WiFi.h>
#include <ESP8266HTTPClient.h>
#include "creds.h"

#define DEBUG_MODE    //Comment out to supress debug info in Serial
//#define NOWIFI        //Comment out when using RaspberryPI

#define LED 2           //Status LED ->built-in
#define ERR 14          //Error LED -> D5
#define PIR 13          //HC-SR501 -> D7

String pi_hostname = "bpem.local";  



Adafruit_BMP280 bmp;

IPAddress serverIP;



void setup()
{
  Serial.begin(9600);
  pinMode(LED,OUTPUT);
  pinMode(ERR,OUTPUT);
  pinMode(PIR,INPUT);

/*---------------------------WIFI SETUP---------------------------*/
  WiFi.begin(ssid, password);

#ifdef DEBUG_MODE
  Serial.print("Connecting to ");
  Serial.print(ssid);
#endif
#ifndef NOWIFI
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
#endif
  Serial.println("\nConnected!");
  Serial.print("IP Address: ");
  Serial.println(WiFi.localIP());
/*-----------------------END OF WIFI SETUP------------------------*/


/*---------------------------BMP280 SETUP---------------------------*/

  if(bmp.begin(BMP280_ADDRESS_ALT))
  {
    Serial.print("\nBMP CONNECTED\n");

    bmp.setSampling(Adafruit_BMP280::MODE_NORMAL,       // Operating Mode
                    Adafruit_BMP280::SAMPLING_X2,       // Temp. oversampling
                    Adafruit_BMP280::SAMPLING_NONE,     // Pressure oversampling
                    Adafruit_BMP280::FILTER_X16,        // Filtering
                    Adafruit_BMP280::STANDBY_MS_500);   // Standby time
  }
  else
      digitalWrite(ERR,HIGH);


/*-----------------------END OF BMP280 SETUP------------------------*/


}



unsigned int count=0;   //mssg ID

WiFiClient wifi;
HTTPClient http;

void loop()
{

#ifdef DEBUG_MODE
  Serial.print("Temperature: ");
  Serial.print(bmp.readTemperature());
  Serial.print(" Motion: ");
  Serial.println(digitalRead(PIR));
#endif
  /*---------------------------mDNS RESOLUTION---------------------------*/
  
  
  while(!WiFi.hostByName(pi_hostname.c_str(),serverIP)||serverIP.toString() == "0.0.0.0")
  {
    Serial.println("DNS failed, retrying...");
    delay(1000);
  }

  #ifdef DEBUG_MODE
  Serial.print("Resolved Raspberry Pi IP: ");
  Serial.println(serverIP.toString());
  #endif
/*-----------------------END OF mDNS RESOLUTION------------------------*/

#ifndef NOWIFI
  char buff[128]="";

  snprintf(buff, sizeof(buff), "http://%s/api/blog/sensor", serverIP.toString().c_str());
  
  #ifdef DEBUG_MODE
  Serial.print("Connecting to ");
  Serial.println(buff);
  #endif
  
  http.begin(wifi,buff);
  http.addHeader("Content-Type","application/json");

  // Build JSON payload in a separate buffer so we don't overwrite the URL
  char payload[128]="";
  snprintf(payload,sizeof(payload),"{\"id\":%d,\"temp\":%.2f,\"pir\":%d,\"user\":\"esp2866\",\"token\":\"secretpass\"}",
                                count,bmp.readTemperature(),digitalRead(PIR));
  #ifdef DEBUG_MODE
  Serial.println(payload);
  #endif

  int httpResponseCode = http.POST((const uint8_t*)payload,strlen(payload));
  Serial.print("POST: ");
  Serial.println(httpResponseCode);

  http.end();
#endif
/*-----------------------END OF HTTP CONNECTION------------------------*/


  count++;

  digitalWrite(LED,HIGH);
  delay(250);
  digitalWrite(LED,LOW);

}