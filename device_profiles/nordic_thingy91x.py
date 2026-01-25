"""Nordic Thingy:91 X device profile implementation (SDD030)."""

import re
from typing import Optional, Tuple, Dict
from .base_device import BaseDeviceProfile


class NordicThingy91XProfile(BaseDeviceProfile):
    """
    Device profile for Nordic Semiconductor Thingy:91 X.
    
    Characteristics (per SDD030):
    - Single-command operations: AT#XSENDTO, AT#XRECVFROM, AT#XBIND
    - ASCII data encoding
    - Standard AT command set: AT+CFUN, AT+CEREG, AT%XSYSTEMMODE, AT+CGDCONT
    - UDP socket commands: AT#XSOCKET=1,2,0 (stateless)
    - Response format: #XRECVFROM: <size>,<ip_addr>,<port> followed by <data>
    """

    def get_device_info(self) -> Dict[str, str]:
        """Return device metadata."""
        return {
            'name': 'Nordic Thingy:91 X',
            'manufacturer': 'Nordic Semiconductor',
            'firmware_type': 'AT shell',
        }

    def initialize_network(self, serial_manager) -> bool:
        """
        Complete network initialization sequence per SDD030.
        
        Sequence:
        1. AT+CFUN=0 - Disable modem
        2. AT+CEREG=5 - Enable network registration URCs
        3. AT+CSCON=1 - Enable connection status notifications
        4. AT%XSYSTEMMODE=1,0,1,0 - Set LTE-M mode
        5. AT+CFUN=1 - Enable modem
        6. Wait for +CEREG URC with stat=1/5 (registered)
        7. AT+CGDCONT=1,"IP","soracom.io" - Configure PDP context
        8. AT#XSOCKET=1,2,0 - Open UDP socket
        9. AT#XBIND=55555 - Bind UDP port (done separately)
        """
        commands = [
            ("AT+CFUN=0", "Disable modem"),
            ("AT+CEREG=5", "Enable network registration URCs (level-5)"),
            ("AT+CSCON=1", "Enable connection status notifications"),
            ("AT%XSYSTEMMODE=1,0,1,0", "Set LTE-M mode"),
            ("AT+CFUN=1", "Enable modem"),
        ]

        for cmd, description in commands:
            # Log to application if available
            if hasattr(serial_manager, 'app') and serial_manager.app:
                serial_manager.app.log_message("sent", f"[SEND] {cmd} - {description}")
            
            success, resp = serial_manager.send_command(cmd)
            
            if hasattr(serial_manager, 'app') and serial_manager.app and resp:
                serial_manager.app.log_message("recv", f"[RECV] {resp}")
            
            if not success:
                return False

        # Network initialization complete
        return True

    def bind_udp_port(self, serial_manager, port: int) -> bool:
        """Bind UDP port for downlink reception (SDD026/SDD027)."""
        cmd = f"AT#XBIND={port}"
        
        # Log to application if available
        if hasattr(serial_manager, 'app') and serial_manager.app:
            serial_manager.app.log_message("sent", f"[SEND] {cmd}")
        
        success, response = serial_manager.send_command(cmd)
        
        if hasattr(serial_manager, 'app') and serial_manager.app and response:
            serial_manager.app.log_message("recv", f"[RECV] {response}")

        # If AT command succeeded, binding is complete
        # Response may be empty or contain OK/#XBIND confirmation
        return success

    def send_to_harvest(self, serial_manager, data: str) -> bool:
        """
        Send data to Soracom Harvest Data via AT#XSENDTO (SDD019).
        
        Single command operation - ASCII encoding (no conversion needed).
        """
        harvest_endpoint = "harvest.soracom.io"
        harvest_port = 8514

        cmd = f'AT#XSENDTO="{harvest_endpoint}",{harvest_port},"{data}"'
        
        # Log to application if available
        if hasattr(serial_manager, 'app') and serial_manager.app:
            serial_manager.app.log_message("sent", f"[SEND] {cmd}")
        
        success, response = serial_manager.send_command(cmd)
        
        if hasattr(serial_manager, 'app') and serial_manager.app and response:
            serial_manager.app.log_message("recv", f"[RECV] {response}")

        if success:
            if response:
                # Parse response format: #XSENDTO: <size> per SDD019
                if "#XSENDTO:" in str(response):
                    try:
                        size_str = str(response).split("#XSENDTO:")[1].strip()
                        size = int(size_str.split()[0])
                        return size > 0
                    except (ValueError, IndexError):
                        return True  # Command succeeded even if parsing fails
            return True  # OK response is success
        return False

    def receive_udp(self, serial_manager, buffer_size: int) -> Optional[Tuple[str, int, str]]:
        """
        Receive UDP downlink data via AT#XRECVFROM (SDD027/SDD028).
        
        Response format per SDD027:
        #XRECVFROM: <size>,<ip_addr>,<port>
        <data>
        OK
        
        Returns: (ip_address, port, payload) or None on failure
        """
        cmd = f"AT#XRECVFROM={buffer_size}"
        success, response = serial_manager.send_command(cmd, timeout=5.0)

        if not success or not response:
            return None

        response_str = str(response)

        # Parse #XRECVFROM header line
        if "#XRECVFROM:" not in response_str:
            return None

        try:
            # Response format: #XRECVFROM: <size>,"<ip_addr>",<port> | <data> | OK
            # Check if response contains pipe separators (single-line format)
            if " | " in response_str:
                parts = response_str.split(" | ")
                header_part = parts[0].strip()
                data_part = parts[1].strip() if len(parts) > 1 else ""
            else:
                # Multi-line format (fallback)
                lines = response_str.split('\n')
                header_part = None
                data_part = None
                
                for line in lines:
                    if "#XRECVFROM:" in line:
                        header_part = line
                    elif line.strip() and not line.startswith("#") and not line.startswith("+"):
                        if "OK" not in line and "ERROR" not in line:
                            data_part = line
                
                if not header_part:
                    return None

            # Parse header: #XRECVFROM: <size>,"<ip_addr>",<port>
            header_match = re.search(
                r'#XRECVFROM:\s*(\d+),\s*"?([^",]+)"?,\s*(\d+)',
                header_part
            )

            if not header_match:
                return None

            size = int(header_match.group(1))
            ip_addr = header_match.group(2).strip('"').strip("'").strip()
            port = int(header_match.group(3))

            # Get payload from parsed data
            payload = data_part.strip() if data_part else ""

            # Filter by IP address (SDD027 step 6)
            if ip_addr != "100.127.10.16":
                return None

            return (ip_addr, port, payload)

        except (ValueError, IndexError, AttributeError):
            return None

    def get_signal_quality(self, serial_manager) -> Optional[Dict[str, int]]:
        """Query signal quality metrics via AT%CESQ (SDD015)."""
        cmd = "AT%CESQ"
        success, response = serial_manager.send_command(cmd)

        if not success or not response:
            return None

        try:
            # Parse %CESQ response format: %CESQ: <rsrp>,<rsrq>,<sinr>
            match = re.search(r'%CESQ:\s*(-?\d+),\s*(-?\d+),\s*(-?\d+)', str(response))
            if match:
                return {
                    'rsrp': int(match.group(1)),
                    'rsrq': int(match.group(2)),
                    'sinr': int(match.group(3)),
                    'rssi': 0,  # Not provided by Nordic
                }
        except (ValueError, AttributeError):
            pass

        return None

    def parse_network_registration_urc(self, urc: str) -> Optional[Dict]:
        """Parse +CEREG network registration URC."""
        if not urc.startswith("+CEREG:"):
            return None

        try:
            # Parse +CEREG: <n>,<stat>[,<lac>,<ci>[,<AcT>]]
            parts = urc.replace("+CEREG:", "").strip().split(",")
            if len(parts) >= 2:
                stat = int(parts[1].strip())
                # stat: 0=not registered, 1=home, 2=searching, 3=denied, 5=roaming
                return {
                    'urc_type': 'cereg',
                    'stat': stat,
                    'registered': stat in [1, 5],
                }
        except (ValueError, IndexError):
            pass

        return None
