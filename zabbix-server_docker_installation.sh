#/bin/bash
#ENV_Variables

MYSQL_DATABASE='zabbix'
MYSQL_USER='user'
MYSQL_PASSWORD='PASS'
MYSQL_ROOT_PASSWORD='DB@ROOT'
DB_SERVER_HOST='mysql-server'
ZBX_JAVAGATEWAY='zabbix-java-gateway'
ZBX_SERVER_HOST='zabbix-server-mysql'

if [[ $1 == "remove" ]];then	
	docker rm mysql-server zabbix-java-gateway zabbix-server-mysql zabbix-web-nginx-mysql -f
echo -e "\nContainers deleted"
else
    echo "info: no input"
#fi
#create Docker network
docker network create --subnet 172.20.0.0/16 --ip-range 172.20.240.0/20 zabbix-net
#cerate MySQL Instance 
sleep 2s
docker run --name $DB_SERVER_HOST -t \
             -e MYSQL_DATABASE="$MYSQL_DATABASE" \
             -e MYSQL_USER="$MYSQL_USER" \
             -e MYSQL_PASSWORD="$MYSQL_PASSWORD" \
             -e MYSQL_ROOT_PASSWORD="$MYSQL_ROOT_PASSWORD" \
             --network=zabbix-net \
             --restart unless-stopped \
             -d mysql:8.0-oracle \
             --character-set-server=utf8 --collation-server=utf8_bin \
             --default-authentication-plugin=mysql_native_password 
#Create zabbix JAVA gateway 
docker run --name $ZBX_JAVAGATEWAY -t \
             --network=zabbix-net \
             --restart unless-stopped \
             -d zabbix/zabbix-java-gateway:alpine-6.4-latest
#Zabbix server instance and link the instance with created MySQL 
docker run --name zabbix-server-mysql -t \
      -e DB_SERVER_HOST="$DB_SERVER_HOST" \
      -e MYSQL_DATABASE="$MYSQL_DATABASE" \
      -e MYSQL_USER="$MYSQL_USER" \
      -e MYSQL_PASSWORD="$MYSQL_PASSWORD" \
      -e MYSQL_ROOT_PASSWORD="$MYSQL_ROOT_PASSWORD" \
      -e ZBX_JAVAGATEWAY="$ZBX_JAVAGATEWAY" \
      --network=zabbix-net \
      -p 10051:10051 \
      --restart unless-stopped \
      -d zabbix/zabbix-server-mysql:alpine-6.4-latest
#Zabbix web interface and link the instance with created MySQL
docker run --name zabbix-web-nginx-mysql -t \
      -e ZBX_SERVER_HOST="$ZBX_SERVER_HOST" \
      -e DB_SERVER_HOST="$DB_SERVER_HOST" \
      -e MYSQL_DATABASE="$MYSQL_DATABASE" \
      -e MYSQL_USER="$MYSQL_USER" \
      -e MYSQL_PASSWORD="$MYSQL_PASSWORD" \
      -e MYSQL_ROOT_PASSWORD="$MYSQL_ROOT_PASSWORD" \
      --network=zabbix-net \
      -p 8080:8080 \
      --restart unless-stopped \
      -d zabbix/zabbix-web-nginx-mysql:alpine-6.4-latest

fi
