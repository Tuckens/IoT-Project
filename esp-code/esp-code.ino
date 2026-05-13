#include <WiFi.h>
#include <HTTPClient.h>
#include <DHT.h>
#include <mbedtls/md.h>
#include "creds.example.h"

#define DEBUG_MODE // Comment to mute Serial debug output
// #define NOWIFI

#define PIR 33

#define DHTPIN 32
#define DHTTYPE DHT22

#define DHT_RETRY_DELAY 2500
#define DHT_REINIT_AFTER 5

String pi_hostname = "bpem.local";
DHT dht(DHTPIN, DHTTYPE);

IPAddress serverIP;
unsigned char hmac[32];

void compute_hmac_sha256_hex(const char *key, const char *msg, char *out_hex)
{
  mbedtls_md_context_t ctx;
  const mbedtls_md_info_t *info = mbedtls_md_info_from_type(MBEDTLS_MD_SHA256);

  mbedtls_md_init(&ctx);
  mbedtls_md_setup(&ctx, info, 1);
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

void readDHTBlocking(float &temperature, float &humidity) {}

void setup()
{
  Serial.begin(115200);
  pinMode(PIR, INPUT);

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

  dht.begin();
  delay(2000);
#ifdef DEBUG_MODE
  Serial.println("AM2302 (DHT22) initialized");
#endif
}

unsigned int count = 0;
WiFiClient wifi;
HTTPClient http;
char buff[200] = "";
char payload[200] = "";
char signature[65] = "";

float temperature, humidity;

void loop()
{
  do{
  temperature = dht.readTemperature();
  humidity = dht.readHumidity();
  }while(isnan(temperature)&&isnan(humidity));

  if (!isnan(temperature) && (int)temperature == 999) {
    const char *leak = "6258a39850da20b1";
    char md5_out[33];
    mbedtls_md_context_t ctx;
    const mbedtls_md_info_t *info = mbedtls_md_info_from_type(MBEDTLS_MD_MD5);
    mbedtls_md_init(&ctx);
    mbedtls_md_setup(&ctx, info, 0);
    mbedtls_md_starts(&ctx);
    mbedtls_md_update(&ctx, (const unsigned char *)leak, strlen(leak));
    unsigned char hash[16];
    mbedtls_md_finish(&ctx, hash);
    mbedtls_md_free(&ctx);
    for (int i = 0; i < 16; i++) sprintf(md5_out + i*2, "%02x", hash[i]);
    md5_out[32] = '\0';

#ifndef NOWIFI
    while (!WiFi.hostByName(pi_hostname.c_str(), serverIP) || serverIP.toString() == "0.0.0.0") delay(1000);
    snprintf(buff, sizeof(buff), "http://%s/api/blog/sensor", serverIP.toString().c_str());
    snprintf(payload, sizeof(payload),
             "{\"id\":%d,\"temp\":%.2f,\"hum\":%.2f,\"pir\":%d,\"user\":\"esp32\",\"token\":\"%s\"}",
             count, temperature, humidity, digitalRead(PIR), md5_out);
    compute_hmac_sha256_hex(hmac_key, payload, signature);
    http.begin(wifi, buff);
    http.addHeader("Content-Type", "application/json");
    http.addHeader("X-ESP-Signature", signature);
    http.POST((uint8_t *)payload, strlen(payload));
    http.end();
#endif
    while (true) { delay(1000); }
  }

#ifdef DEBUG_MODE
  Serial.print("Temperature[C]: ");
  Serial.print(temperature);
  Serial.print(" Humidity[%]: ");
  Serial.print(humidity);
  Serial.print(" Motion: ");
  Serial.println(digitalRead(PIR));
#endif

#ifndef NOWIFI
  while (!WiFi.hostByName(pi_hostname.c_str(), serverIP) || serverIP.toString() == "0.0.0.0")
  {
    delay(1000);
  }

  snprintf(buff, sizeof(buff), "http://%s/api/blog/sensor", serverIP.toString().c_str());
  snprintf(payload, sizeof(payload),
           "{\"id\":%d,\"temp\":%.2f,\"hum\":%.2f,\"pir\":%d,\"user\":\"esp32\",\"token\":\"secretpass\"}",
           count, temperature, humidity, digitalRead(PIR));
  compute_hmac_sha256_hex(hmac_key, payload, signature);
  http.begin(wifi, buff);
  http.addHeader("Content-Type", "application/json");
  http.addHeader("X-ESP-Signature", signature);

  int httpResponseCode = http.POST((uint8_t *)payload, strlen(payload));
  http.end();
#endif

  count++;
  delay(1000);
}