#include  <Adafruit_BMP280.h>
#include <ESP8266WiFi.h>
#include <ESP8266HTTPClient.h>

#define DEBUG_MODE    //Comment out to supress debug info in Serial

#define LED 2     //Status LED
#define ERR 14    //Error LED

Adafruit_BMP280 bmp;
const char* ssid = "Antenne";
const char* password = "bulldograt25";
const char* target_ip="10.92.161.212:8000/data.php";
String serverName;
char buff[64]="";

void setup()
{
  Serial.begin(9600);
  pinMode(LED,OUTPUT);
  pinMode(ERR,OUTPUT);

/*---------------------------WIFI SETUP---------------------------*/
#ifdef DEBUG_MODE
  WiFi.begin(ssid, password);
  delay(50);
  Serial.print("Connecting to ");
  Serial.print(ssid);
#endif
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }

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
  Serial.print(bmp.readTemperature());
  Serial.print("\n");
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
  
  // CORRECTION : Bon Content-Type pour le format URL-encoded
  http.addHeader("Content-Type","application/x-www-form-urlencoded");

  #ifdef DEBUG_MODE
  Serial.println("Connected to HTTP server");
  #endif

  snprintf(buff,sizeof(buff),"t=%.2f&count=%d",bmp.readTemperature(),count);
  strcat(buff,"&admin");
  String post_req=String(buff);
  
  #ifdef DEBUG_MODE
  Serial.println(post_req);
  #endif

  // CORRECTION : Uniquement un POST (le GET a été supprimé)
  int httpResponseCode = http.POST(post_req);

  #ifdef DEBUG_MODE
  Serial.print("HTTP Response code: ");
  Serial.println(httpResponseCode);
  #endif

  // CORRECTION : On ferme la connexion quoi qu'il arrive
  http.end();

/*-----------------------END OF HTTP CONNECTION------------------------*/

  count++;

  digitalWrite(LED,HIGH);
  delay(400);
  digitalWrite(LED,LOW);

  // Pause ajoutée pour éviter de saturer le serveur Raspberry Pi
  delay(1600); 

}