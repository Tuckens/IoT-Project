#include  <Adafruit_BMP280.h>
#include <ESP8266WiFi.h>
#include <ESP8266HTTPClient.h>

#define DEBUG_MODE    //Comment out to supress debug info in Serial
#define NOWIFI        //Comment out when using RaspberryPI

#define LED 2         //Status LED ->built-in
#define ERR 14        //Error LED -> D5
#define PIR 13        //HC-SR501 -> D7



Adafruit_BMP280 bmp;
const char* ssid = "Antenne";
const char* password = "bulldograt25";
const char* target_ip="10.92.161.212:8000";
String serverName;
char buff[64]="";







void setup()
{
  Serial.begin(9600);
  pinMode(LED,OUTPUT);
  pinMode(ERR,OUTPUT);
  pinMode(PIR,INPUT);

/*---------------------------WIFI SETUP---------------------------*/
#ifdef DEBUG_MODE
  WiFi.begin(ssid, password);
  delay(50);
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



unsigned int count=0;

void loop()
{

#ifdef DEBUG_MODE
  Serial.print("Temperature: ");
  Serial.print(bmp.readTemperature());
  Serial.print(" Motion: ");
  Serial.println(digitalRead(PIR));

#endif
  WiFiClient wifi;

/*---------------------------HTTP CONNECTION---------------------------*/
  HTTPClient http;
  snprintf(buff,sizeof(buff),"http://%s",target_ip);
  String path2server=String(buff);
  
  #ifdef DEBUG_MODE
  Serial.print("Connecting to ");
  Serial.println(path2server);
  #endif
  
  http.begin(wifi,path2server);
  http.addHeader("Content-type","application/json");

  
  #ifdef DEBUG_MODE
  Serial.println("Connected to HTTP server");
  #endif

  snprintf(buff,sizeof(buff),"t=%.2f&pir=%d&count=%d",bmp.readTemperature(),digitalRead(PIR),count);
  strcat(buff,"&admin");
  String post_req=String(buff);
  Serial.println(post_req);

  http.GET();
  int httpResponseCode = http.POST(post_req);


  if(httpResponseCode<0)
    http.end();

/*-----------------------END OF HTTP CONNECTION------------------------*/


  count++;

  digitalWrite(LED,HIGH);
  delay(400);
  digitalWrite(LED,LOW);


}