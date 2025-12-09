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

## Installation
### 1. Import Template
```
Zabbix UI → Configuration → Templates → Import
```
Select: AWS VPN by HTTP.yaml
download from here. 👆

### 2. Create a Host

You don’t need any interfaces.
Just create a host with:

Hostname: AWS-VPN-Monitor

Group: Cloud / AWS

### 3. Add the macros shown below.

---
| Macro	| Description |
|-------|-------------|
| **{$AWS.ACCESS.KEY}**	| IAM Access Key ID |
| **{$AWS.SECRET.KEY}** |	IAM Secret Access Key |
| **{$AWS.REGION}**	| AWS Region |

---

### 📝 Expected API JSON Format

API must return JSON:

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
