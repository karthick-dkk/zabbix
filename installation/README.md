# Install Zabbix on CentOS Linux machine with in 2 minutes!

**Install Zabbix Server ,Frontend , Database & Java Gateway**

**Requirements:** ❓

1️⃣ Docker - installation instructions --> https://docs.docker.com/engine/install/centos/

2️⃣ Git

**Download:** ⬇️
```
git clone https://github.com/karthick-dkk/zabbix-karthick_dk.git
```

**Allow Permission:** ☑️
```
chmod u+x  zabbix-karthick_dk/zabbix_installation.sh
```

**Run:**🏃‍♂️
```
zabbix-karthick_dk/zabbix_installation.sh
```

**Delete Existing Containers and Re-run:** 🚮
```
./zabbix_installation remove
```
**Default Login Details:**

URL: http://localhost:8080         (or)          http://IP-Address:8080

User: Admin
  
Password: zabbix

**Note:** 📝

  Make sure your are allowed port 8080 on your Machine or Firewall

**Install Zabbix Agent 2 on CentOS:** 🖥️

**Add Repo:**
```
sudo rpm -Uvh https://repo.zabbix.com/zabbix/6.4/rhel/8/x86_64/zabbix-release-6.4-1.el8.noarch.rpm
```
```
dnf clean all
```

**Download Zabbix Agent2:**  ⬇️
```
dnf install zabbix-agent2 zabbix-agent2-plugin-*
```
**Start and Enable on boot :** ✅
```
 systemctl restart zabbix-agent2 &&  systemctl enable zabbix-agent2
```

