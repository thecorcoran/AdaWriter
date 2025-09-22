# wifi_manager.py (Version 2.0)
# Stable Wi-Fi manager for AdaWriter using nmcli.

import subprocess
import time

def _run_system_command(command, timeout=10, check=True):
    """A centralized helper to run shell commands for this module."""
    try:
        result = subprocess.run(
            command, check=check, capture_output=True, text=True, timeout=timeout
        )
        return True, result.stdout.strip()
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        error_output = e.stderr.strip() if e.stderr else "No stderr output"
        return False, error_output
    except FileNotFoundError:
        return False, "Command not found"

def scan_for_networks():
    """Scans for available Wi-Fi networks using nmcli."""
    print("DEBUG: Scanning for Wi-Fi networks...")
    _run_system_command(['sudo', 'nmcli', 'dev', 'wifi', 'rescan'], check=False)
    time.sleep(4)

    command = [
        'sudo', 'nmcli', '--terse', '--fields', 'SSID,SIGNAL,SECURITY',
        'dev', 'wifi', 'list', '--rescan', 'no'
    ]
    success, output = _run_system_command(command)
    
    if not success:
        return []

    networks, seen_ssids = [], set()
    for line in output.strip().split('\n'):
        parts = line.split(':')
        if len(parts) >= 3:
            ssid = parts[0]
            if ssid and ssid not in seen_ssids:
                networks.append({'ssid': ssid, 'signal': parts[1], 'security': parts[2]})
                seen_ssids.add(ssid)
    
    return sorted(networks, key=lambda x: int(x['signal']), reverse=True)

def connect_to_network(ssid, password):
    """Connects to a specified Wi-Fi network using nmcli."""
    print(f"DEBUG: Attempting to connect to '{ssid}'...")
    
    _run_system_command(['sudo', 'nmcli', 'dev', 'disconnect', 'wlan0'], check=False, timeout=5)
    time.sleep(2)
    
    command = ['sudo', 'nmcli', 'dev', 'wifi', 'connect', ssid]
    if password:
        command.extend(['password', password])

    success, output = _run_system_command(command, timeout=30)
    
    if success and "successfully activated" in output:
        msg = f"Successfully connected to '{ssid}'!"
        return True, msg
    else:
        if "secrets were required" in output:
            msg = "Connection Failed:\nIncorrect Password."
        elif not success:
            msg = f"Connection Failed:\n{output}"
        else:
            msg = "Connection Failed:\nUnknown Error."
        return False, msg

def get_connection_status():
    """Checks the current network connection status."""
    command = ['nmcli', '-t', '--fields', 'NAME,TYPE', 'con', 'show', '--active']
    success, output = _run_system_command(command, check=False)
    
    if success and output:
        for conn in output.strip().split('\n'):
            if ':wifi' in conn or ':ethernet' in conn:
                return conn.split(':')[0]
    return "Disconnected"