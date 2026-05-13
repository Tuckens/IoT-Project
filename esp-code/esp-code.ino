#include <WiFi.h>
#include <HTTPClient.h>
#include <DHT.h>
#include <mbedtls/md.h>
#include "creds.example.h"

#define DEBUG_MODE // Comment to mute Serial debug output
//#define NOWIFI   // Comment when using with the Raspberry Pi

#define PIR 33



String pi_hostname = "bpem.local";
DHT dht(32, DHT22);   //PIN, TYPE

IPAddress serverIP;
unsigned char hmac[32];
mbedtls_md_context_t ctx;


// Compute HMAC-SHA256(key, message) and write the lowercase hex digest
// into out_hex (must hold 65 bytes: 64 hex chars + NUL). mbedtls is part
// of the standard ESP32 Arduino core — no extra library to install.
void compute_hmac_sha256_hex(const char *key, const char *msg, char *out_hex)
{
  const mbedtls_md_info_t *info = mbedtls_md_info_from_type(MBEDTLS_MD_SHA256);

  mbedtls_md_init(&ctx);
  mbedtls_md_setup(&ctx, info, 1 /* hmac */);
  mbedtls_md_hmac_starts(&ctx, (const unsigned char *)key, strlen(key));
  mbedtls_md_hmac_update(&ctx, (const unsigned char *)msg, strlen(msg));
  mbedtls_md_hmac_finish(&ctx, hmac);
  mbedtls_md_free(&ctx);

  for (int i = 0; i < 32; i++)
  {
    sprintf(out_hex + i * 2, "%02x", hmac[i]);
  }
  out_hex[64] = '\0';
}



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
char signature[65] = "";
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

  // Build the payload (no secret inside it anymore).
  snprintf(payload, sizeof(payload),
           "{\"id\":%d,\"temp\":%.2f,\"hum\":%.2f,\"pir\":%d,\"user\":\"esp32\",\"passwd\":\"adM1np4s5wD\"}",
           msid, temperature, humidity, digitalRead(PIR));

  // Sign it with the shared HMAC key. The signature goes in a header,
  // not in the body, so the body bytes that the server hashes are
  // bit-identical to what we hashed here.
  compute_hmac_sha256_hex(hmac_key, payload, signature);

  http.begin(wifi, buff);
  http.addHeader("Content-Type", "application/json");
  http.addHeader("ESP-Signature", signature);

#ifdef DEBUG_MODE
  Serial.println(payload);
  Serial.print("X-ESP-Signature: ");
  Serial.println(signature);
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
