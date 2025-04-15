import time
from zabbix_utils import ZabbixAPI

# Zabbix server details and Authentication
zabbix_url = "http://10.0.2.15/zabbix"
api_username = 'Admin'
api_password = 'zabbix'
api = ZabbixAPI(url=zabbix_url)

print(f"Connecting to Zabbix server at {zabbix_url}")
api.login(user=api_username, password=api_password)
print("Successfully logged in to Zabbix API")

# Link colors
COLOR_ACTIVE = "00CC00"    # Bright green for active
COLOR_INACTIVE = "CC0000"  # Bright red for inactive

# Mapping of device types to icon IDs
ICON_MAP = {
    "server": "96",     # Linux Server
    "router": "94",     # Router
    "switch": "128",    # Switch
    "zabbix_server": "100"  # Zabbix Server
}

def detect_device_type(ip):
    """Determine the device type based on IP."""
    if ip == "192.168.1.100":
        return "switch"
    elif ip == "192.168.1.1":
        return "router"
    return "server"

def check_host_status(host_id):
    """Check host status with comprehensive checking."""
    try:
        # Get host info with necessary fields
        host_info = api.host.get({
            "hostids": host_id,
            "output": ["host", "status"],
            "selectInterfaces": ["ip", "available"],
            "selectInventory": ["name"]
        })
        
        if not host_info:
            print(f"Host ID {host_id} not found")
            return False
            
        host = host_info[0]
        host_name = host["host"]
        ip = host["interfaces"][0]["ip"] if host["interfaces"] else "Unknown IP"
        is_enabled = host["status"] == "0"  # 0 = Enabled/Monitored
        
        # Check multiple indicators of status
        status_indicators = []
        
        # 1. Interface availability
        interface_available = False
        if host["interfaces"] and "available" in host["interfaces"][0]:
            interface_available = host["interfaces"][0]["available"] == "1"
        status_indicators.append(interface_available)
        
        # 2. ICMP ping status
        ping_items = api.item.get({
            "hostids": host_id,
            "search": {"key_": "icmpping"},
            "output": ["lastvalue", "lastclock"]
        })
        ping_ok = False
        if ping_items and "lastvalue" in ping_items[0]:
            ping_ok = ping_items[0]["lastvalue"] == "1"
            # Check if ping data is recent (within last 5 minutes)
            if "lastclock" in ping_items[0]:
                last_update = int(ping_items[0]["lastclock"])
                current_time = int(time.time())
                ping_ok = ping_ok and (current_time - last_update < 300)
        status_indicators.append(ping_ok)
        
        # Host is active if enabled and has at least one positive status indicator
        is_active = is_enabled and any(status_indicators)
        
        # Debug output
        print(f"Status check for {host_name} ({ip}):")
        print(f"  Enabled: {is_enabled}")
        print(f"  Interface Available: {interface_available}")
        print(f"  Ping OK: {ping_ok}")
        print(f"  Final Status: {'ACTIVE' if is_active else 'INACTIVE'}")
        
        return is_active
    except Exception as e:
        print(f"Error checking host status for ID {host_id}: {str(e)}")
        return False

def create_or_get_host(host_name, host_group_id, ip):
    """Create or get host with duplicate prevention."""
    # [Same as original implementation]
    try:
        existing = api.host.get({
            "filter": {"ip": ip},
            "output": ["hostid", "host"]
        })
        
        if existing:
            for host in existing:
                if host["host"] == host_name:
                    print(f"Host {host_name} ({ip}) already exists with ID {host['hostid']}")
                    return host['hostid']
            host_id = existing[0]["hostid"]
            api.host.update({
                "hostid": host_id,
                "host": host_name
            })
            print(f"Updated existing host to {host_name} ({ip}) with ID {host_id}")
            return host_id
            
        result = api.host.create({
            "host": host_name,
            "interfaces": [{
                "type": 1,  # Agent interface
                "main": 1,
                "useip": 1,
                "ip": ip,
                "dns": "",
                "port": "10050"
            }],
            "groups": [{"groupid": host_group_id}],
            "templates": [{"templateid": "10001"}]  # Assuming this is your template
        })
        
        print(f"Created host {host_name} ({ip}) with ID {result['hostids'][0]}")
        return result["hostids"][0]
    except Exception as e:
        print(f"Error creating/getting host {host_name}: {e}")
        return None

def update_map_links(map_id):
    """Update map links based on host status."""
    try:
        current_map = api.map.get({
            "sysmapids": map_id,
            "selectLinks": "extend",
            "selectSelements": "extend"
        })[0]

        updated_links = []
        host_status_cache = {}  # Cache host status to avoid repeated checks
        
        for link in current_map["links"]:
            link_status = None
            host_element = None
            
            # Find the host element connected to this link
            for selement in current_map["selements"]:
                if (selement["selementid"] == link["selementid2"] and 
                    selement["elementtype"] == "0" and 
                    "elements" in selement and 
                    selement["elements"] and 
                    "hostid" in selement["elements"][0]):
                    host_element = selement
                    break
            
            if host_element:
                host_id = host_element["elements"][0]["hostid"]
                if host_id not in host_status_cache:
                    host_status_cache[host_id] = check_host_status(host_id)
                is_active = host_status_cache[host_id]
                
                link["color"] = COLOR_ACTIVE if is_active else COLOR_INACTIVE
                link["label"] = f"{'ACTIVE' if is_active else 'DOWN'}\n{time.strftime('%H:%M:%S')}"
            
            updated_links.append(link)

        api.map.update({
            "sysmapid": map_id,
            "links": updated_links
        })
        print(f"Updated map links at {time.strftime('%H:%M:%S')}")
        
    except Exception as e:
        print(f"Error updating map links: {e}")

def create_network_map(map_name, elements, host_group_id):
    """Create network map with devices."""
    try:
        existing = api.map.get({"filter": {"name": map_name}})
        if existing:
            api.map.delete([existing[0]["sysmapid"]])
            print(f"Deleted existing map '{map_name}'")

        selements, links = [], []
        element_id = 1

        # Main Server
        main_server_element = {
            "selementid": element_id,
            "elements": [{"elementtype": 4}],
            "elementtype": 4,
            "iconid_off": ICON_MAP["zabbix_server"],
            "label": "Main Server\n192.168.1.85",
            "x": 600, "y": 100
        }
        selements.append(main_server_element)
        main_server_id = element_id
        element_id += 1

        # Switch
        switch_host_id = create_or_get_host("Core_Switch", host_group_id, "192.168.1.100")
        if not switch_host_id:
            return None
            
        switch_element = {
            "selementid": element_id,
            "elements": [{"hostid": switch_host_id}],
            "elementtype": 0,
            "iconid_off": ICON_MAP["switch"],
            "label": "Core Switch\n192.168.1.100",
            "x": 600, "y": 300
        }
        selements.append(switch_element)
        switch_id = element_id
        element_id += 1

        # Initial link between server and switch
        switch_active = check_host_status(switch_host_id)
        links.append({
            "selementid1": main_server_id,
            "selementid2": switch_id,
            "color": COLOR_ACTIVE if switch_active else COLOR_INACTIVE,
            "drawtype": 2,
            "label": f"{'ACTIVE' if switch_active else 'DOWN'}\n{time.strftime('%H:%M:%S')}"
        })

        # Devices with duplicate prevention
        unique_ips = set()
        for i, element in enumerate(elements):
            ip = element["ip"]
            if ip in unique_ips:
                print(f"Skipping duplicate IP: {ip}")
                continue
            unique_ips.add(ip)
            
            host_name = f"Host_{ip.replace('.', '_')}"
            host_id = create_or_get_host(host_name, host_group_id, ip)
            
            if not host_id:
                continue
                
            device_type = detect_device_type(ip)
            is_active = check_host_status(host_id)
            
            selement = {
                "selementid": element_id,
                "elements": [{"hostid": host_id}],
                "elementtype": 0,
                "iconid_off": ICON_MAP.get(device_type, ICON_MAP["server"]),
                "label": f"{host_name}\n{ip}",
                "x": 300 + (i % 5) * 300,
                "y": 500
            }
            selements.append(selement)

            links.append({
                "selementid1": switch_id,
                "selementid2": element_id,
                "color": COLOR_ACTIVE if is_active else COLOR_INACTIVE,
                "drawtype": 2,
                "label": f"{'ACTIVE' if is_active else 'DOWN'}\n{time.strftime('%H:%M:%S')}"
            })
            element_id += 1

        result = api.map.create({
            "name": map_name,
            "width": 1920,
            "height": 1080,
            "selements": selements,
            "links": links
        })

        print(f"Created network map '{map_name}' with ID {result['sysmapids'][0]}")
        return result["sysmapids"][0]
    except Exception as e:
        print(f"Error creating map: {str(e)}")
        return None

# Remaining functions (get_discovered_devices, create_or_get_host_group, monitor_network_status, main)
# remain unchanged from your original code

def get_discovered_devices(drule_name):
    """Retrieve discovered devices with duplicate removal."""
    try:
        result = api.drule.get({
            "output": ["druleid"],
            "filter": {"name": drule_name}
        })
        
        if not result:
            print(f"Discovery rule '{drule_name}' not found, using default IPs")
            return [{"ip": "192.168.1.85"}, {"ip": "192.168.1.95"}, {"ip": "192.168.1.100"}]
            
        drule_id = result[0]["druleid"]
        discovered = api.dhost.get({
            "druleids": [drule_id],
            "selectDServices": "extend",
            "output": ["dhostid"]
        })
        
        unique_ips = set()
        devices = []
        for dhost in discovered:
            if "dservices" in dhost and dhost["dservices"]:
                for service in dhost["dservices"]:
                    if "ip" in service and service["ip"] not in unique_ips:
                        unique_ips.add(service["ip"])
                        devices.append({"ip": service["ip"]})
        
        if not devices:
            print("No devices found, using default IPs")
            return [{"ip": "192.168.1.85"}, {"ip": "192.168.1.95"}, {"ip": "192.168.1.100"}]
            
        return devices
    except Exception as e:
        print(f"Error getting discovered devices: {str(e)}")
        return [{"ip": "192.168.1.85"}, {"ip": "192.168.1.95"}, {"ip": "192.168.1.100"}]

def create_or_get_host_group(host_group_name):
    """Create or retrieve a Zabbix host group."""
    try:
        result = api.hostgroup.get({
            "output": ["groupid"],
            "filter": {"name": host_group_name}
        })
        
        if result:
            print(f"Host group '{host_group_name}' already exists with ID {result[0]['groupid']}")
            return result[0]["groupid"]
            
        result = api.hostgroup.create({"name": host_group_name})
        print(f"Created host group '{host_group_name}' with ID {result['groupids'][0]}")
        return result["groupids"][0]
    except Exception as e:
        print(f"Error with host group: {str(e)}")
        return None

def monitor_network_status(map_id, check_interval=5):
    """Continuously monitor network status."""
    print(f"Starting monitoring with {check_interval}-second interval...")
    try:
        while True:
            update_map_links(map_id)
            time.sleep(check_interval)
    except KeyboardInterrupt:
        print("Monitoring stopped by user")
    except Exception as e:
        print(f"Error in monitoring loop: {e}")

def main():
    host_group_id = create_or_get_host_group("NetworkDevices")
    if not host_group_id:
        print("Failed to create or get host group. Exiting.")
        return
    
    devices = get_discovered_devices("Network Discovery")
    print(f"Found devices: {[d['ip'] for d in devices]}")
    
    map_id = create_network_map("Network Map", devices, host_group_id)
    if map_id:
        monitor_network_status(map_id, 5)
    else:
        print("Failed to create network map")

if __name__ == "__main__":
    main()