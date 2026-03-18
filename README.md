# Best Project Ever Made


## Hardware

- Raspberry PI 4B
- Raspberry PI Camera Rev 1.3
- ESP 
- BMP280



## Software

- Raspberry PI OS Lite 64 Bit
- PosgreSQL
- html
- css
- javascript
- python3
  

## Description
The raspi is connected to the raspi camera. The ESP is connected to a temperature sensor. When the sensor is triggered (detects too high temperature) 
the ESP sends information to the raspbi to record with the camera for a few seconds.

### ArduinoIDE
Go to File > Preferences > Add the link *https://arduino.esp8266.com/stable/package_esp8266com_index.json* in **Additional boards manager URL**.
In Board Manager choose **NodeMCU 1.0 (ESP12-E)**. Then also import BMP280 library and run the code

