import subprocess
import time
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs
import logging

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')


def run_command(cmd, shell=False):
    try:
        logging.debug(f"Running command: {' '.join(cmd) if isinstance(cmd, list) else cmd}")
        subprocess.run(cmd, shell=shell, check=True, capture_output=True, text=True)
        logging.info(f"Command succeeded: {' '.join(cmd) if isinstance(cmd, list) else cmd}")
        return True
    except subprocess.CalledProcessError as e:
        logging.error(f"Command failed: {' '.join(cmd) if isinstance(cmd, list) else cmd}, Error: {e}")
        return False


def reboot_system():
    logging.info("Rebooting system")
    subprocess.run(['sudo', 'reboot'])


def configure_wifi(ssid, password):
    logging.debug(f"Configuring WiFi for SSID: {ssid}")
    config = f"""country=US
    ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev
    update_config=1
    network={{
        ssid="{ssid}"
        psk="{password}"
        key_mgmt=WPA-PSK
    }}"""

    try:
        with open('/tmp/wpa_supplicant.conf', 'w') as f:
            f.write(config)
        logging.info(f"Temporary wpa_supplicant.conf created for SSID: {ssid}")
    except IOError as e:
        logging.error(f"Error writing wpa_supplicant.conf: {e}")
        return False

    success = run_command(['sudo', 'cp', '/tmp/wpa_supplicant.conf', '/etc/wpa_supplicant/wpa_supplicant.conf'])
    if not success:
        logging.error("Failed to copy wpa_supplicant configuration")
        return False

    run_command(['sudo', 'wpa_cli', '-i', 'wlan0', 'reconfigure'])
    time.sleep(10)

    try:
        result = subprocess.run(['iwgetid'], capture_output=True, text=True)
        if ssid in result.stdout:
            logging.info(f"Successfully connected to {ssid}")
            return True
        else:
            logging.warning(f"Failed to connect to {ssid}. Check credentials.")
            return False
    except Exception as e:
        logging.error(f"Error checking WiFi connection: {e}")
        return False


def scan_wifi_networks():
    try:
        result = subprocess.run(['sudo', 'iwlist', 'wlan0', 'scan'], capture_output=True, text=True)
        networks = set()
        for line in result.stdout.split('\n'):
            if 'ESSID:' in line:
                ssid = line.split('ESSID:"')[1].split('"')[0]
                if ssid:
                    networks.add(ssid)
        return sorted(list(networks))
    except Exception as e:
        logging.error(f"Error scanning for networks: {e}")
        return []


class WiFiSetupHandler(BaseHTTPRequestHandler):
    html_form = """<!DOCTYPE html>
    <html>
    <head>
        <title>Raspberry Pi WiFi Setup</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
    </head>
    <body>
        <h2>Connect to WiFi</h2>
        <form method="POST" action="/connect">
            <div>
                <label>Select WiFi Network:</label>
                <select name="ssid" required>{network_options}</select>
                <button type="button" onclick="location.reload()">Refresh Networks</button>
            </div>
            <div>
                <label>Password:</label>
                <input type="password" name="password" required>
            </div>
            <button type="submit">Connect</button>
        </form>
    </body>
    </html>"""

    def do_GET(self):
        logging.debug("Handling GET request")
        if self.path == '/':
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            networks = scan_wifi_networks()
            network_options = ''.join(f'<option value="{ssid}">{ssid}</option>' for ssid in networks)
            self.wfile.write(self.html_form.format(network_options=network_options).encode())

    def do_POST(self):
        logging.debug("Handling POST request")
        if self.path == '/connect':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length).decode()
            params = parse_qs(post_data)
            ssid = params['ssid'][0]
            password = params['password'][0]
            logging.info(f"Received connection request for SSID: {ssid}")

            if configure_wifi(ssid, password):
                self.send_response(200)
                self.wfile.write(b"<html><body><h2>Successfully connected to WiFi!</h2></body></html>")
                threading.Timer(5, reboot_system).start()
            else:
                self.send_response(200)
                self.wfile.write(b"<html><body><h2>Connection failed</h2></body></html>")


def main():
    logging.info("Starting WiFi setup script")
    server = HTTPServer(('0.0.0.0', 80), WiFiSetupHandler)
    logging.info("Web server started at http://<your-pi-ip>")
    server.serve_forever()


if __name__ == "__main__":
    main()
