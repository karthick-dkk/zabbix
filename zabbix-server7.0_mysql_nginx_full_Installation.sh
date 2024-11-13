#################
# Tested On Ubuntu 24 AMD 
# Install Zabbix-Server, Frontend, Agent, Nginx 
# Inital Setup of Zabbix Server for Enterprise Monitoring
##################
#Wownload the repo from zabbix.com
#amd64
#wget https://repo.zabbix.com/zabbix/7.0/ubuntu/pool/main/z/zabbix-release/zabbix-release_7.0-2+ubuntu24.04_all.deb
#wget https://repo.zabbix.com/zabbix/7.0/ubuntu/pool/main/z/zabbix-release/zabbix-release_7.0-2+ubuntu24.04_all.deb \
#arm

 install_zabbix_repo() {
     wget https://repo.zabbix.com/zabbix/7.0/ubuntu/pool/main/z/zabbix-release/zabbix-release_7.0-2+ubuntu24.04_all.deb \
     && echo ">>>> Downloaded Zabbix repo" && dpkg -i zabbix-release_7.0-2+ubuntu24.04_all.deb && \
     sleep 2 && [ $? -eq 0 ] && echo "*****Repo installation success ****" || { echo -e "\n >>>> Repo installation failed#######" ; exit 1; \
  }
}

update_system() {
# Update packages
    echo ">>>>>update system packages"
    apt update -y
    sleep 5
  [ $? -eq 0 ] && echo "****Zabbix installed successfully ****" || echo -e "\n #####Zabbix installation failed######"
}
install_zabbix() {
#install zabbix
 [ $? -eq 0 ] && echo "######Installing Zabbix now########" && \
  apt install -y zabbix-server-mysql zabbix-frontend-php zabbix-nginx-conf zabbix-sql-scripts zabbix-agent \
  && echo -e "*****Zabbix installed successfully**** \n " || { echo -e " \n >>>>> Zabbix installation Failed or facing issue.  \n "; exit 1; \
}

}
install_mysql() {
#Install MySQL Database
  echo ">>>>>Installing MySQL Packages"
  apt install mysql-server -y \
  && echo -e "******MySQL installed Successfully***** \n " || { echo -e " \n >>>> MySQL Installation Failed###### \n "; exit 1; \
  }
  mysql_config

}

mysql_config() {
IS_FRESH_INSTALL=$(mysql -u root -e "SELECT COUNT(*) FROM mysql.user WHERE User != 'root' AND User != '';" | tail -n 1)
HAS_EXTRA_DATABASES=$(mysql -u root -e "SHOW DATABASES LIKE 'test';" )

if [[ "$IS_FRESH_INSTALL" -ne 0 || "$HAS_EXTRA_DATABASES" -ne 0 ]]; then
    # Define your MySQL root password here
    MYSQL_ROOT_PASSWORD="test"

    # Run secure installation commands
    mysql -u root <<EOF
    ALTER USER 'root'@'localhost' IDENTIFIED WITH 'mysql_native_password' BY '$MYSQL_ROOT_PASSWORD';
    DELETE FROM mysql.user WHERE User='';
    DELETE FROM mysql.user WHERE User='root' AND Host NOT IN ('localhost');
    DROP DATABASE IF EXISTS test;
    DELETE FROM mysql.db WHERE Db='test' OR Db='test\\_%';
    FLUSH PRIVILEGES;
EOF
[ $? -eq 0 ] && echo "...Config-MySQL- Success !" || echo -e " \n >>> MySQL Config - FAILED !!!!"

    else
     echo  -e " \n >>>>  Warning: MySQL is not a fresh installation. Aborting MSQL Config. \n "
     exit 1

fi
systemctl status MySQL
}

# Function to configure MySQL for Zabbix
configure_mysql_zabbix(){
    # Log into MySQL as root (prompt for password)
    echo "Logging into MySQL as root..."
    mysql -uroot -p <<EOF
password

# Create the Zabbix database with UTF8MB4 character set and collation
create database zabbix character set utf8mb4 collate utf8mb4_bin;

# Create the Zabbix user and set a password
create user zabbix@localhost identified by 'password';

# Grant all privileges to the Zabbix user for the Zabbix database
grant all privileges on zabbix.* to zabbix@localhost;

# Allow the creation of functions in binary logging
set global log_bin_trust_function_creators = 1;

# Exit MySQL
quit;
EOF

    # Import Zabbix database schema and data into the Zabbix database
    echo "Importing Zabbix schema into MySQL..."
    zcat /usr/share/zabbix-sql-scripts/mysql/server.sql.gz | mysql --default-character-set=utf8mb4 -uzabbix -p zabbix

    # Log back into MySQL to disable the function creators in binary logging
    echo "Reconnecting to MySQL to adjust log_bin_trust_function_creators..."
    mysql -uroot -p <<EOF
password

# Set global setting to disable the creation of functions in binary logging
set global log_bin_trust_function_creators = 0;

# Exit MySQL
quit;
EOF
}

# Function to configure the Zabbix server
configure_zabbix_server(){
    # Set the database password in the Zabbix server config
    echo "Configuring Zabbix server to connect to MySQL..."
    sed -i "s/^#DBPassword=.*/DBPassword=password/" /etc/zabbix/zabbix_server.conf

    # Modify the nginx.conf file to uncomment and set the 'listen' and 'server_name' directives
    echo "Configuring nginx for Zabbix..."
    sed -i 's/^#listen 8080;/listen 8080;/' /etc/zabbix/nginx.conf
    sed -i 's/^#server_name example.com;/server_name example.com;/' /etc/zabbix/nginx.conf

    # Restart the necessary services for the changes to take effect
    echo "Restarting Zabbix server, agent, nginx, and PHP-FPM..."
    systemctl restart zabbix-server zabbix-agent nginx php8.3-fpm

    # Enable services to start on boot
    echo "Enabling Zabbix server, agent, nginx, and PHP-FPM to start on boot..."
    systemctl enable zabbix-server zabbix-agent nginx php8.3-fpm
}

install_zabbix_repo
update_system 
install_mysql
install_zabbix
# Execute the functions
configure_mysql_zabbix
configure_zabbix_server

