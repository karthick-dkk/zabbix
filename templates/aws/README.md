# AWS VPN by HTTP — Zabbix Template

A custom-built Zabbix template for monitoring AWS Site-to-Site VPN Tunnels using the HTTP Agent.  
This template uses a simple HTTPS endpoint (AWS API) that returns VPN status in JSON format.

Supports Zabbix **6.4 / 7.0 / 8.0**.

---

## 🚀 Features

- Monitors AWS VPN connection state  
- Checks Tunnel 1 and Tunnel 2 states (UP/DOWN)  
- Supports Access Key authentication or IAM Role (STS AssumeRole)
- API-based monitoring — no agents required
- Discover VPNs Automatically
- Trigger-based alerts for:
  - Tunnel 1 DOWN  
  - Tunnel 2 DOWN  
  - Both tunnels DOWN
  - VPN not available   

---

## 📦 Template Contents

| Component | Purpose |
|----------|---------|
| **HTTP Agent Item** | Fetches VPN JSON payload |
| **Dependent Items** | Tunnel1, Tunnel2, State, ID, Region, Name |
| **Preprocessing** | JSONPath extraction |
| **Value Maps** | UP/DOWN mapping |
| **Triggers** | Tunnel & VPN alerts |
| **Tags** | AWS, VPN, Network |

---

## 📝 Expected API JSON Format

Your API must return JSON like:

```
[
  {
    "vpnId": "vpn-0963aec172bca9aa3",
    "vpnName": "My-VPN",
    "vpnState": "available",
    "vpnRegion": "ap-south-1",
    "tunnel1": "UP",
    "tunnel2": "DOWN"
  }
]
```
