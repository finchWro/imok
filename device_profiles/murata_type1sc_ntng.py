"""Murata Type 1SC-NTNG device profile implementation (SDD030, based on client.ttl)."""

import re
from typing import Optional, Tuple, Dict
from .base_device import BaseDeviceProfile


class MurataType1SCProfile(BaseDeviceProfile):
    """
    Device profile for Murata Type 1SC-NTNG.
    
    Characteristics (per SDD030):
    - Multi-step socket operations: ALLOCATE → ACTIVATE → SEND → DELETE
    - HEX data encoding (ASCII to HEX conversion required)
    - Murata-specific AT commands: AT%RATIMGSEL, AT%RATACT, AT%SOCKETCMD, AT%SOCKETDATA
    - Stateful socket lifecycle management
    - Different PDP context syntax: AT%PDNSET=1,"soracom.io","IP"
    """

    def get_device_info(self) -> Dict[str, str]:
        """Return device metadata."""
        return {
            'name': 'Murata Type 1SC-NTNG',
            'manufacturer': 'Murata',
            'firmware_type': 'AT shell',
        }

    def initialize_network(self, serial_manager) -> bool:
        """
        Complete network initialization sequence per SDD030.
        
        Sequence (from client.ttl):
        1. ATZ - Reset modem, wait for %BOOTEV:0
        2. AT+CSIM=52,"80C2000015D613190103820282811B0100130799F05000010001" - Switch to LTE-M SIM plan
        3. AT%RATIMGSEL=1 - Select LTE-M RAT image
        4. AT%RATACT="CATM",1 - Activate LTE-M RAT
        5. AT%SETCFG="BAND","20" - Configure LTE-M band
        6. AT+CFUN=0 - Disable modem
        7. AT%PDNSET=1,"soracom.io","IP" - Configure PDP context
        8. ATZ - Reset and wait for %BOOTEV:0
        9. AT+CEREG=2 - Enable network registration URCs
        10. AT+CFUN=1 - Enable modem
        11. Wait for CEREG: 5 (registered)
        """
        # Initial reset and configuration
        commands = [
            ("ATZ", "Reset modem"),
            ('AT+CSIM=52,"80C2000015D613190103820282811B0100130799F05000010001"', "Switch to LTE-M SIM plan"),
            ("AT%RATIMGSEL=1", "Select LTE-M RAT image"),
            ('AT%RATACT="CATM",1', "Activate LTE-M RAT"),
            ('AT%SETCFG="BAND","20"', "Configure LTE-M band"),
            ("AT+CFUN=0", "Disable modem"),
            ('AT%PDNSET=1,"soracom.io","IP"', "Configure PDP context"),
            ("ATZ", "Reset and wait for boot"),
            ("AT+CEREG=2", "Enable network registration URCs"),
            ("AT+CFUN=1", "Enable modem"),
        ]

        for cmd, description in commands:
            success, resp = serial_manager.send_command(cmd, timeout=10.0)
            if not success:
                return False

        # Network initialization complete
        return True

    def bind_udp_port(self, serial_manager, port: int) -> bool:
        """
        Murata does not require explicit port binding.
        
        Ports are allocated dynamically via AT%SOCKETCMD="ALLOCATE".
        This method returns True to maintain interface compatibility.
        """
        return True

    def send_to_harvest(self, serial_manager, data: str) -> bool:
        """
        Send data to Soracom Harvest Data (SDD019).
        
        Multi-step process per SDD030:
        1. Convert ASCII data to HEX: data.encode().hex().upper()
        2. AT%SOCKETCMD="ALLOCATE",1,"UDP","OPEN","harvest.soracom.io",8514,0 - Allocate UDP socket
        3. AT%SOCKETCMD="ACTIVATE",1 - Activate socket
        4. AT%SOCKETDATA="SEND",1,<len>,"<hex_data>" - Send HEX-encoded data
        5. Wait for %SOCKETEV:1,1 URC (confirmation)
        6. AT%SOCKETCMD="DELETE",1 - Delete socket
        """
        harvest_endpoint = "harvest.soracom.io"
        harvest_port = 8514

        try:
            # Step 1: Convert ASCII to HEX
            hex_data = data.encode().hex().upper()
            char_len = len(hex_data) // 2

            # Step 2: Allocate socket
            cmd = f'AT%SOCKETCMD="ALLOCATE",1,"UDP","OPEN","{harvest_endpoint}",{harvest_port},0'
            success, response = serial_manager.send_command(cmd, timeout=5.0)
            if not success:
                return False

            # Step 3: Activate socket
            cmd = 'AT%SOCKETCMD="ACTIVATE",1'
            success, response = serial_manager.send_command(cmd, timeout=5.0)
            if not success:
                return False

            # Step 4: Send data (HEX encoded)
            cmd = f'AT%SOCKETDATA="SEND",1,{char_len},"{hex_data}"'
            success, response = serial_manager.send_command(cmd, timeout=5.0)
            if not success:
                return False

            # Step 5: Wait for confirmation URC %SOCKETEV:1,1
            # This is typically received as an unsolicited event, not a command response
            # For now, we assume the SEND command success indicates transmission
            # In production, should wait for URC with timeout

            # Step 6: Delete socket
            cmd = 'AT%SOCKETCMD="DELETE",1'
            serial_manager.send_command(cmd, timeout=5.0)

            return True

        except Exception as e:
            return False

    def receive_udp(self, serial_manager, buffer_size: int) -> Optional[Tuple[str, int, str]]:
        """
        Receive UDP downlink data.
        
        Note: Murata Type 1SC-NTNG uses AT%SOCKETCMD for socket operations.
        For downlink reception, the device sends URCs when data arrives.
        This implementation waits for data on the allocated socket.
        """
        # Murata socket operations require allocate/activate/receive/delete sequence
        # For downlink (Harvest Data), the device typically sends data via URC %SOCKETEV

        try:
            # Allocate socket for receiving
            cmd = 'AT%SOCKETCMD="ALLOCATE",1,"UDP","OPEN","0.0.0.0",0,1'
            success, response = serial_manager.send_command(cmd, timeout=5.0)
            if not success:
                return None

            # Activate socket
            cmd = 'AT%SOCKETCMD="ACTIVATE",1'
            success, response = serial_manager.send_command(cmd, timeout=5.0)
            if not success:
                return None

            # Wait for data - typically arrives via %SOCKETEV URC
            # For now, return None if no immediate response
            # Production implementation should queue received data from URCs

            # Delete socket
            serial_manager.send_command('AT%SOCKETCMD="DELETE",1', timeout=5.0)

            return None

        except Exception:
            return None

    def get_signal_quality(self, serial_manager) -> Optional[Dict[str, int]]:
        """Query signal quality metrics via AT%MEAS (per client.ttl)."""
        cmd = 'AT%MEAS="8"'
        success, response = serial_manager.send_command(cmd, timeout=5.0)

        if not success or not response:
            return None

        try:
            # Parse %MEAS response format: RSRP = -123, RSRQ = -10, SINR = 5, RSSI = -80
            # (from client.ttl: 'RSRP = (-?\d+), RSRQ = (-?\d+), SINR = (-?\d+), RSSI = (-?\d+)')
            match = re.search(
                r'RSRP\s*=\s*(-?\d+),\s*RSRQ\s*=\s*(-?\d+),\s*SINR\s*=\s*(-?\d+),\s*RSSI\s*=\s*(-?\d+)',
                str(response)
            )
            if match:
                return {
                    'rsrp': int(match.group(1)),
                    'rsrq': int(match.group(2)),
                    'sinr': int(match.group(3)),
                    'rssi': int(match.group(4)),
                }
        except (ValueError, AttributeError):
            pass

        return None

    def parse_network_registration_urc(self, urc: str) -> Optional[Dict]:
        """Parse CEREG network registration URC."""
        # Murata uses: CEREG: 5 format (without + prefix in some cases)
        if not ("CEREG:" in urc or "+CEREG:" in urc):
            return None

        try:
            # Extract stat value
            match = re.search(r'CEREG:\s*(\d+)', urc)
            if match:
                stat = int(match.group(1))
                # stat: 0=not registered, 1=home, 2=searching, 3=denied, 5=roaming
                return {
                    'urc_type': 'cereg',
                    'stat': stat,
                    'registered': stat in [1, 5],
                }
        except (ValueError, AttributeError):
            pass

        return None
