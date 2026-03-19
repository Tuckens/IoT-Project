#include  <Adafruit_BMP280.h>
#include <Arduino_JSON.h>
#include <ESP8266WiFi.h>
#include <ESP8266HTTPClient.h>

#define DEBUG_MODE    //Comment out to supress debug info in Serial
//#define NOWIFI        //Comment out when using RaspberryPI

#define LED 2         //Status LED ->built-in
#define ERR 14        //Error LED -> D5
#define PIR 13        //HC-SR501 -> D7



Adafruit_BMP280 bmp;
const char* ssid = "Antenne";
const char* password = "REDACTED";
const char* target_ip="10.92.161.212:8000";
String serverName;
char buff[64]="";

JSONVar json;




void setup()
{
  Serial.begin(9600);
  pinMode(LED,OUTPUT);
  pinMode(ERR,OUTPUT);
  pinMode(PIR,INPUT);

/*---------------------------WIFI SETUP---------------------------*/
#ifdef DEBUG_MODE
  WiFi.begin(ssid, password);
  delay(1000);
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
                    Adafruit_BMP280::SAMPLING_X16,      // Pressure oversampling
                    Adafruit_BMP280::FILTER_X16,        // Filtering
                    Adafruit_BMP280::STANDBY_MS_500);   // Standby time
  }
  else
      digitalWrite(ERR,HIGH);


/*-----------------------END OF BMP280 SETUP------------------------*/


}



unsigned int count=0;   //mssg ID

void loop()
{

#ifdef DEBUG_MODE
  Serial.print("Temperature: ");
  Serial.print(bmp.readTemperature());
  Serial.print(" Motion: ");
  Serial.println(digitalRead(PIR));

#endif

#ifndef NOWIFI
/*---------------------------HTTP CONNECTION---------------------------*/
  WiFiClient wifi;
  HTTPClient http;
  snprintf(buff,sizeof(buff),"http://%s",target_ip);
  String path2server=String(buff);
  
  #ifdef DEBUG_MODE
  Serial.print("Connecting to ");
  Serial.println(path2server);
  #endif
  
  http.begin(wifi,path2server);
  http.addHeader("Content-type","application/json");

#endif



json["temp"]=bmp.readTemperature();
json["pir"]=digitalRead(PIR);
json["pass"]="REDACTED-TOKEN";
json["id"]=count;
json["user"]="admin";


#ifndef NOWIFI
  int httpResponseCode = http.POST(JSON.stringify(json));
    Serial.println(JSON.stringify(json));

  Serial.print("POST: ");
  Serial.println(httpResponseCode);

  http.end();
#endif
/*-----------------------END OF HTTP CONNECTION------------------------*/


  count++;

  digitalWrite(LED,HIGH);
  delay(500);
  digitalWrite(LED,LOW);


}