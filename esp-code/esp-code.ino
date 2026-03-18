#include  <Adafruit_BMP280.h>

Adafruit_BMP280 bmp;

#define DEBUG_MODE    //Comment out to supress debug info in Serial

#define LED 2     //Status LED
#define ERR 14    //Error LED

void setup()
{
  Serial.begin(9600);
  pinMode(LED,OUTPUT);
  pinMode(ERR,OUTPUT);


/*---------------------------BMP280---------------------------*/

  if(bmp.begin(BMP280_ADDRESS_ALT))
  {
    Serial.print("BMP CONNECTED\n");
  }
  else
      digitalWrite(ERR,HIGH);

  bmp.setSampling(Adafruit_BMP280::MODE_NORMAL,       // Operating Mode
                  Adafruit_BMP280::SAMPLING_X2,       // Temp. oversampling
                  Adafruit_BMP280::SAMPLING_X16,      // Pressure oversampling
                  Adafruit_BMP280::FILTER_X16,        // Filtering
                  Adafruit_BMP280::STANDBY_MS_500);   // Standby time
                  

/*-----------------------END OF BMP280-------------------------*/


}


void loop()
{
#ifdef DEBUG_MODE
  Serial.print(bmp.readTemperature());
  Serial.print("\n");
#endif

  digitalWrite(LED,HIGH);
  delay(400);
  digitalWrite(LED,LOW);


}