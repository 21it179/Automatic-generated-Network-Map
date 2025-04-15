# **Zabbix Auto Network Map Generator** 

This Python script automatically discovers devices via a Zabbix discovery rule, creates corresponding monitored hosts, and generates a live-updating network map in Zabbix. It visually shows the real-time status of devices and links — green for active and red for down.

# Features
Automatically fetches devices discovered by Zabbix

Creates or updates hosts based on IP address

Builds a Zabbix network map with appropriate icons (servers, switches, routers, etc.)

Continuously monitors device availability (agent availability, ping check)

Real-time visual map updates:

**Green links for active devices**

**Red links for unreachable devices**

# **Requirements**

Python 3.x

A running Zabbix server (tested on Zabbix 6+)

Zabbix API access (Admin user recommended)

zabbix_utils.py module (custom Zabbix API wrapper)

# **Project Structure**
 
├── zabbix_map.py           # Your main automation script

├── zabbix_utils.py          # Helper functions for API access

└── README.md                # Project documentation

# **Configuration**

Inside the script, update the following variables:

**zabbix_url = "http://<your-zabbix-host>/zabbix"**

**api_username = "Admin"**

**api_password = "zabbix"**

How to Use : 

Ensure Zabbix API access is enabled and a discovery rule is set up (e.g. named "Network Discovery").

Run the script:

python main_script.py

The script will:

Retrieve discovered devices

Create/update Zabbix hosts

Generate a live network map

Start monitoring the map in a loop (press Ctrl+C to stop)

# **Logic Overview**

Uses Zabbix API to interact with hosts, discovery rules, maps

Identifies device type based on IP (custom logic)

Monitors host status with:

Host enabled check

Interface availability

ICMP ping status + freshness (within 5 mins)

Refreshes the map every few seconds for up-to-date status display

**To-Do / Ideas**
Automatically position elements more dynamically

Add support for more device types and icons

Alert integration (email/Slack on link failure)
