from flask import Flask, jsonify, request
from pyzabbix import ZabbixAPI
import time
import threading
import logging
import requests
import urllib3

# Suppress SSL warnings when verify=False is used
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Zabbix connection settings
ZABBIX_SERVER = 'http://10.0.2.15/zabbix'  # Change to https:// if using HTTPS
ZABBIX_USER = 'Admin'
ZABBIX_PASSWORD = 'zabbix'

# Set to False to skip SSL verification for HTTPS connections
SSL_VERIFY = False

# Cache settings
last_service_edges_data = None
last_fetch_time = 0
cache_lock = threading.Lock()

def connect_to_zabbix():
    try:
        is_https = ZABBIX_SERVER.startswith('https://')
        
        if is_https:
            session = requests.Session()
            session.verify = SSL_VERIFY
            zapi = ZabbixAPI(ZABBIX_SERVER, session=session)
        else:
            zapi = ZabbixAPI(ZABBIX_SERVER)
        
        zapi.login(ZABBIX_USER, ZABBIX_PASSWORD)
        logger.info(f"Connected to Zabbix API v{zapi.api_version()}")
        return zapi
    except Exception as e:
        logger.error(f"Zabbix connection failed: {str(e)}")
        raise Exception(f"Zabbix connection failed: {str(e)}")

def calculate_error_rate(service_triggers):
    """
    Calculate error rate based on service triggers.
    
    Args:
        service_triggers (list): List of service-related triggers
    
    Returns:
        dict: Error statistics
    """
    total_count = len(service_triggers)
    error_triggers = [t for t in service_triggers if t['value'] == '1']  # Assuming '1' indicates an error
    error_count = len(error_triggers)
    
    error_rate = (error_count / total_count * 100) if total_count > 0 else 0
    
    # Determine color based on error rate
    if error_rate == 0:
        color = 'green'
    elif error_rate < 10:
        color = 'yellow'
    else:
        color = 'red'
    
    return {
        'total_count': total_count,
        'error_count': error_count,
        'error_rate': round(error_rate, 2),
        'color_based_error_rate': color
    }

def fetch_service_dependency_graph():
    """
    Fetch service dependency graph data from Zabbix.
    
    Returns:
        dict: Service dependency graph data
    """
    global last_service_edges_data, last_fetch_time
    
    try:
        logger.info("Fetching service dependency graph data from Zabbix...")
        zapi = connect_to_zabbix()
        
        # Fetch hosts and their service relationships
        hosts = zapi.host.get(output=['hostid', 'name'])
        
        service_edges = []
        for i in range(len(hosts)):
            for j in range(i+1, len(hosts)):
                source_host = hosts[i]
                target_host = hosts[j]
                
                # Fetch triggers for both hosts to determine service relationship
                source_triggers = zapi.trigger.get(hostids=source_host['hostid'])
                target_triggers = zapi.trigger.get(hostids=target_host['hostid'])
                
                # Calculate error rates and status
                source_error_stats = calculate_error_rate(source_triggers)
                target_error_stats = calculate_error_rate(target_triggers)
                
                # Simulating request metrics (you might want to replace with actual metrics)
                request_rate = round(abs(hash(source_host['name'] + target_host['name']) % 100), 2)
                avg_duration_ms = round(abs(hash(source_host['name']) % 500), 2)
                
                # Determine connection status and color
                status = "Active Connection" if source_error_stats['error_rate'] < 10 and target_error_stats['error_rate'] < 10 else "Inactive Connection"
                color = 'red' if status == "Inactive Connection" else 'green'
                
                service_edge = {
                    "id": f"{source_host['hostid']}-{target_host['hostid']}",
                    "source": source_host['hostid'],
                    "target": target_host['hostid'],
                    "color": color,
                    "status": status,
                    "error_count": source_error_stats['error_count'] + target_error_stats['error_count'],
                    "total_count": source_error_stats['total_count'] + target_error_stats['total_count'],
                    "error_rate": round((source_error_stats['error_rate'] + target_error_stats['error_rate']) / 2, 2),
                    "request_rate": request_rate,
                    "avg_duration_ms": avg_duration_ms,
                    "source_service": source_host['name'],
                    "target_service": target_host['name'],
                    "color_based_error_rate": source_error_stats['color_based_error_rate']
                }
                
                service_edges.append(service_edge)
        
        with cache_lock:
            last_service_edges_data = service_edges
            last_fetch_time = time.time()
        
        return {"edges": service_edges}
    
    except Exception as e:
        logger.error(f"Error fetching service dependency graph: {str(e)}")
        return None

@app.route('/api/service-dependency/edges', methods=['GET'])
def get_service_edges():
    """
    API endpoint to retrieve service dependency edges with optional filtering.
    """
    try:
        with cache_lock:
            if last_service_edges_data is None:
                data = fetch_service_dependency_graph()
                if data is None:
                    return jsonify({"error": "Failed to fetch service dependency graph"}), 500
            
            filtered_edges = last_service_edges_data.copy()
        
        # Filtering options
        source_filter = request.args.get('source')
        if source_filter:
            filtered_edges = [edge for edge in filtered_edges 
                               if edge.get('source') == source_filter]
        
        target_filter = request.args.get('target')
        if target_filter:
            filtered_edges = [edge for edge in filtered_edges 
                               if edge.get('target') == target_filter]
        
        status_filter = request.args.get('status')
        if status_filter:
            filtered_edges = [edge for edge in filtered_edges 
                               if edge.get('status') == status_filter]
        
        return jsonify({"edges": filtered_edges})
    
    except Exception as e:
        logger.error(f"Error in get_service_edges endpoint: {str(e)}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    try:
        fetch_service_dependency_graph()
    except Exception as e:
        logger.error(f"Initial service dependency graph fetch failed: {str(e)}")
    
    logger.info("Starting Flask server...")
    app.run(host='0.0.0.0', port=5025, debug=True)