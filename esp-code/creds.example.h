#ifndef _CREDS_H_
#define _CREDS_H_

// Copy this file to creds.h and fill in your own values.
// creds.h is ignored by git — never commit real credentials.

const char *ssid     = "YOUR_WIFI_SSID";
const char *password = "YOUR_WIFI_PASSWORD";

// Shared HMAC key used to sign every POST to /api/blog/sensor. Must match
// ESP_HMAC_KEY in the server's flask/flaskr/.env.
// Generate once with:
//   python -c "import secrets; print(secrets.token_hex(32))"
const char *hmac_key = "PUT_64_HEX_CHARS_HERE";

#endif
