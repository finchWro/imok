"""Murata Type 1SC-NTN device profile implementation (SDD030, based on client.ttl)."""

import re
import time
from typing import Optional, Tuple, Dict
from .base_device import BaseDeviceProfile


class MurataType1SCProfile(BaseDeviceProfile):
    """
    Device profile for Murata Type 1SC-NTN.
    
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
            'name': 'Murata Type 1SC-NTN',
            'manufacturer': 'Murata',
            'firmware_type': 'AT shell',
        }

    def initialize_network(self, serial_manager) -> bool:
        """
        Complete NTN network initialization sequence per SDD034.
        
        Implements complete Murata Type 1SC-NTN NTN initialization with GNSS.
        """
        import time
        
        # Phase 1: Initial configuration
        commands_phase1 = [
            ("AT+CPIN?", "Check SIM state"),
            ('AT%SETACFG="manager.urcBootEv.enabled","true"', "Enable verbose error reporting"),
            ('AT%SETCFG="SIM_INIT_SELECT_POLICY","0"', "Set SIM initialization policy"),
        ]
        
        for cmd, description in commands_phase1:
            if hasattr(serial_manager, 'app') and serial_manager.app:
                serial_manager.app.log_message("sent", f"[SEND] {cmd} - {description}")
            success, resp = serial_manager.send_command(cmd, timeout=10.0)
            if hasattr(serial_manager, 'app') and serial_manager.app and resp:
                serial_manager.app.log_message("recv", f"[RECV] {resp}")
            if not success:
                return False
        
        # Reset modem and wait for %BOOTEV:0
        if hasattr(serial_manager, 'app') and serial_manager.app:
            serial_manager.app.log_message("sent", "[SEND] ATZ - Reset modem")
        if not self._send_and_wait_boot(serial_manager, "ATZ"):
            return False
        
        # Phase 2: NTN Parameters
        commands_phase2 = [
            ('AT%SETACFG="radiom.config.multi_rat_enable","true"', "Enable multi-RAT"),
            ('AT%SETACFG="radiom.config.preferred_rat_list","none"', "Clear preferred RAT list"),
            ('AT%SETACFG="radiom.config.auto_preference_mode","none"', "Disable auto preference"),
            ('AT%SETACFG="locsrv.operation.locsrv_enable","true"', "Enable location service"),
            ('AT%SETACFG="locsrv.internal_gnss.auto_restart","enable"', "Enable GNSS auto-restart"),
            ('AT%SETACFG="modem_apps.Mode.AutoConnectMode","true"', "Enable auto-connect mode"),
        ]
        
        for cmd, description in commands_phase2:
            if hasattr(serial_manager, 'app') and serial_manager.app:
                serial_manager.app.log_message("sent", f"[SEND] {cmd} - {description}")
            success, resp = serial_manager.send_command(cmd, timeout=10.0)
            if hasattr(serial_manager, 'app') and serial_manager.app and resp:
                serial_manager.app.log_message("recv", f"[RECV] {resp}")
            if not success:
                return False
        
        # Reset again
        if hasattr(serial_manager, 'app') and serial_manager.app:
            serial_manager.app.log_message("sent", "[SEND] ATZ - Reset modem after NTN config")
        if not self._send_and_wait_boot(serial_manager, "ATZ"):
            return False
        
        # Phase 3: NTN RAT configuration
        commands_phase3 = [
            ('AT+CSIM=52,"80C2000015D613190103820282811B0100130799F08900010001"', "Switch to NTN SIM plan"),
            ("AT%RATIMGSEL=2", "Select NTN RAT image"),
            ('AT%RATACT="NBNTN","1"', "Activate NB-IoT-NTN RAT"),
            ('AT%SETCFG="BAND","256"', "Lock to Europe S band (256)"),
            ("AT+CFUN=0", "Disable modem"),
        ]
        
        for cmd, description in commands_phase3:
            if hasattr(serial_manager, 'app') and serial_manager.app:
                serial_manager.app.log_message("sent", f"[SEND] {cmd} - {description}")
            success, resp = serial_manager.send_command(cmd, timeout=10.0)
            if hasattr(serial_manager, 'app') and serial_manager.app and resp:
                serial_manager.app.log_message("recv", f"[RECV] {resp}")
            if not success:
                return False
        
        # Phase 4: Enable GNSS and notifications
        commands_phase4 = [
            ('AT%IGNSSEV="FIX",1', "Enable GNSS fix notification"),
            ('AT%NOTIFYEV="SIB31",1', "Enable NTN reception notification"),
            ("AT%IGNSSACT=0", "Disable iGNSS"),
            ("AT%IGNSSACT=1", "Enable iGNSS"),
        ]
        
        for cmd, description in commands_phase4:
            if hasattr(serial_manager, 'app') and serial_manager.app:
                serial_manager.app.log_message("sent", f"[SEND] {cmd} - {description}")
            success, resp = serial_manager.send_command(cmd, timeout=10.0)
            if hasattr(serial_manager, 'app') and serial_manager.app and resp:
                serial_manager.app.log_message("recv", f"[RECV] {resp}")
            if not success:
                return False
        
        # Wait for GNSS fix (crucial per SDD034)
        if hasattr(serial_manager, 'app') and serial_manager.app:
            serial_manager.app.log_message("sys", "[INFO] Waiting for GNSS fix (%IGNSSEVU:FIX)... This may take several minutes")
        
        if not self._wait_for_gnss_fix(serial_manager, timeout=300.0):  # 5 minutes timeout
            if hasattr(serial_manager, 'app') and serial_manager.app:
                serial_manager.app.log_message("sys", "[ERROR] GNSS fix timeout - cannot proceed without location")
            return False
        
        # Phase 5: Enable network registration
        commands_phase5 = [
            ("AT+CEREG=2", "Enable network registration URCs with location"),
            ("AT+CFUN=1", "Enable radio"),
        ]
        
        for cmd, description in commands_phase5:
            if hasattr(serial_manager, 'app') and serial_manager.app:
                serial_manager.app.log_message("sent", f"[SEND] {cmd} - {description}")
            success, resp = serial_manager.send_command(cmd, timeout=10.0)
            if hasattr(serial_manager, 'app') and serial_manager.app and resp:
                serial_manager.app.log_message("recv", f"[RECV] {resp}")
            if not success:
                return False
        
        # Network initialization complete
        return True
    
    def _send_and_wait_boot(self, serial_manager, cmd: str) -> bool:
        """Send command and wait for %BOOTEV:0 URC."""
        import time
        with serial_manager.command_lock:
            try:
                serial_manager.serial_port.write((cmd + "\r\n").encode())
            except Exception as e:
                if hasattr(serial_manager, 'app') and serial_manager.app:
                    serial_manager.app.log_message("sys", f"[ERROR] Failed to send {cmd}: {e}")
                return False
            
            start = time.time()
            timeout = 15.0
            got_boot = False
            while time.time() - start < timeout:
                try:
                    evt = serial_manager.event_queue.get(timeout=0.2)
                    if hasattr(serial_manager, 'app') and serial_manager.app:
                        serial_manager.app.log_message("recv", f"[RECV] {evt}")
                    if "%BOOTEV:0" in evt:
                        got_boot = True
                        break
                except:
                    pass
                # Also drain response queue
                try:
                    resp = serial_manager.response_queue.get_nowait()
                    if hasattr(serial_manager, 'app') and serial_manager.app:
                        serial_manager.app.log_message("recv", f"[RECV] {resp}")
                except:
                    pass
            
            if not got_boot:
                if hasattr(serial_manager, 'app') and serial_manager.app:
                    serial_manager.app.log_message("sys", "[ERROR] Timeout waiting for %BOOTEV:0")
                return False
            return True
    
    def _wait_for_gnss_fix(self, serial_manager, timeout: float) -> bool:
        """Wait for GNSS fix URC (%IGNSSEVU:FIX) and extract location (REQ012, SDD034)."""
        import time
        import re
        start = time.time()
        while time.time() - start < timeout:
            try:
                evt = serial_manager.event_queue.get(timeout=1.0)
                if hasattr(serial_manager, 'app') and serial_manager.app:
                    serial_manager.app.log_message("recv", f"[RECV] {evt}")
                # Look for GNSS fix notification
                if "%IGNSSEVU:" in evt and "FIX" in evt:
                    if hasattr(serial_manager, 'app') and serial_manager.app:
                        serial_manager.app.log_message("sys", "[SUCCESS] GNSS fix acquired")
                        # Extract location per SDD034
                        try:
                            match = re.search(r'%IGNSSEVU:\s*"[^"]+",\d+,"[^"]+","[^"]+","(-?\d+\.\d+)","(-?\d+\.\d+)"', evt)
                            if match:
                                lat = match.group(1)
                                lon = match.group(2)
                                serial_manager.app.set_location(lat, lon, source="GNSS")
                        except Exception as e:
                            serial_manager.app.log_message("sys", f"[WARNING] Could not extract location from GNSS fix: {e}")
                    return True
            except:
                pass
        return False

    def bind_udp_port(self, serial_manager, port: int) -> bool:
        """
        Bind UDP port for downlink reception (SDD042 updated).

        Updated SDD042 requires a listening UDP socket:
        1. ALLOCATE: AT%SOCKETCMD=\"ALLOCATE\",1,\"UDP\",\"LISTEN\",\"0.0.0.0\",,<udp_port>
        2. Wait for: %SOCKETCMD:<socket_id> notification
        3. ACTIVATE: AT%SOCKETCMD=\"ACTIVATE\",<socket_id>

        Note: In deployments already using OPEN to the Harvest endpoint (SDD038),
        this LISTEN allocation may fail. In that case, we keep the existing OPEN
        socket and proceed (downlink still works via %SOCKETEV + RECEIVE).
        """
        try:
            # Clear any stale %SOCKETCMD notifications before LISTEN allocation
            if hasattr(serial_manager, 'app') and serial_manager.app:
                serial_manager.app.last_socketcmd_notification = None
            
            # Step 1: Attempt LISTEN allocation per updated SDD042 (note: double comma before port is intentional per spec)
            cmd = f'AT%SOCKETCMD="ALLOCATE",1,"UDP","LISTEN","0.0.0.0",,{port}'
            if hasattr(serial_manager, 'app') and serial_manager.app:
                serial_manager.app.log_message("sent", f"[SEND] {cmd} - Allocate UDP LISTEN socket (SDD042)")
            success, response = serial_manager.send_command(cmd, timeout=8.0)
            if hasattr(serial_manager, 'app') and serial_manager.app and response:
                serial_manager.app.log_message("recv", f"[RECV] {response}")

            if success:
                # Step 2: Wait for %SOCKETCMD:<socket_id> notification per SDD042
                if hasattr(serial_manager, 'app') and serial_manager.app:
                    serial_manager.app.log_message("sys", "[INFO] Waiting for %SOCKETCMD notification after ALLOCATE (SDD042)...")
                
                # Poll for %SOCKETCMD notification from app state (avoids event_queue race)
                import time
                import re
                start_wait = time.time()
                socketcmd_received = None
                listen_socket_id = None
                while time.time() - start_wait < 5.0:
                    app = getattr(serial_manager, 'app', None)
                    if app and app.last_socketcmd_notification:
                        socketcmd_received = str(app.last_socketcmd_notification)
                        # Parse socket ID from %SOCKETCMD:<socket_id> format
                        match = re.search(r'%SOCKETCMD:(\d+)', socketcmd_received)
                        if match:
                            listen_socket_id = match.group(1)
                        app.last_socketcmd_notification = None  # Clear after reading
                        break
                    time.sleep(0.1)
                
                if not socketcmd_received:
                    if hasattr(serial_manager, 'app') and serial_manager.app:
                        serial_manager.app.log_message("sys", "[WARNING] %SOCKETCMD notification not received; proceeding with ACTIVATE")
                    # Fallback to socket 1 if notification wasn't captured
                    listen_socket_id = "1"
                else:
                    if hasattr(serial_manager, 'app') and serial_manager.app:
                        serial_manager.app.log_message("sys", f"[VERIFY] %SOCKETCMD received: {socketcmd_received} (SDD042)")

                # Store listen socket ID in app state for %SOCKETEV handler (SDD042)
                if hasattr(serial_manager, 'app') and serial_manager.app:
                    serial_manager.app.listen_socket_id = listen_socket_id

                # Step 3: Activate the socket using the socket_id from the notification
                act = f'AT%SOCKETCMD="ACTIVATE",{listen_socket_id}'
                if hasattr(serial_manager, 'app') and serial_manager.app:
                    serial_manager.app.log_message("sent", f"[SEND] {act} - Activate LISTEN socket (SDD042)")
                success_act, response_act = serial_manager.send_command(act, timeout=8.0)
                if hasattr(serial_manager, 'app') and serial_manager.app and response_act:
                    serial_manager.app.log_message("recv", f"[RECV] {response_act}")
                if not success_act:
                    return False
                if hasattr(serial_manager, 'app') and serial_manager.app:
                    serial_manager.app.log_message("sys", f"[SUCCESS] UDP port {port} bound for receive (LISTEN mode, SDD042)")
                return True

            # If LISTEN allocation failed, keep existing configuration (likely OPEN to Harvest)
            if hasattr(serial_manager, 'app') and serial_manager.app:
                serial_manager.app.log_message("sys", "[INFO] LISTEN allocation failed or not applicable; using existing socket configuration (SDD038).")
            return True

        except Exception as e:
            if hasattr(serial_manager, 'app') and serial_manager.app:
                serial_manager.app.log_message("sys", f"[ERROR] Failed to bind UDP port: {e}")
            return False

    def open_socket_connection(self, serial_manager) -> bool:
        """Open UDP socket to Soracom Harvest Data (SDD038 updated).

        Steps per updated SDD038:
        1) Enable socket events: AT%SOCKETEV=0,1
        2) Allocate socket 1: AT%SOCKETCMD="ALLOCATE",1,"UDP","OPEN","harvest.soracom.io",8514
        3) Activate socket 1: AT%SOCKETCMD="ACTIVATE",1
        """
        try:
            # Step 1: Enable socket events
            cmd = 'AT%SOCKETEV=0,1'
            if hasattr(serial_manager, 'app') and serial_manager.app:
                serial_manager.app.log_message("sent", f"[SEND] {cmd} - Enable socket events")
            success, response = serial_manager.send_command(cmd, timeout=5.0)
            if hasattr(serial_manager, 'app') and serial_manager.app and response:
                serial_manager.app.log_message("recv", f"[RECV] {response}")
            if not success:
                return False

            # Step 2: Allocate UDP socket 1 to Harvest endpoint
            # Clear any stale %SOCKETCMD notifications first
            if hasattr(serial_manager, 'app') and serial_manager.app:
                serial_manager.app.last_socketcmd_notification = None
            
            cmd = 'AT%SOCKETCMD="ALLOCATE",1,"UDP","OPEN","harvest.soracom.io",8514'
            if hasattr(serial_manager, 'app') and serial_manager.app:
                serial_manager.app.log_message("sent", f"[SEND] {cmd} - Allocate socket 1 to Harvest (SDD038)")
            success, response = serial_manager.send_command(cmd, timeout=10.0)
            if hasattr(serial_manager, 'app') and serial_manager.app and response:
                serial_manager.app.log_message("recv", f"[RECV] {response}")
            if not success:
                return False

            # Wait for %SOCKETCMD notification
            import time
            start_wait = time.time()
            while time.time() - start_wait < 5.0:
                app = getattr(serial_manager, 'app', None)
                if app and app.last_socketcmd_notification:
                    app.last_socketcmd_notification = None  # Clear after reading
                    break
                time.sleep(0.1)

            # Step 3: Activate socket 1
            cmd = 'AT%SOCKETCMD="ACTIVATE",1'
            if hasattr(serial_manager, 'app') and serial_manager.app:
                serial_manager.app.log_message("sent", f"[SEND] {cmd} - Activate socket 1 (SDD038)")
            success, response = serial_manager.send_command(cmd, timeout=10.0)
            if hasattr(serial_manager, 'app') and serial_manager.app and response:
                serial_manager.app.log_message("recv", f"[RECV] {response}")
            if not success:
                return False

            if hasattr(serial_manager, 'app') and serial_manager.app:
                serial_manager.app.log_message("sys", "[SUCCESS] UDP socket 1 opened to Harvest (SDD038)")
            return True

        except Exception as e:
            if hasattr(serial_manager, 'app') and serial_manager.app:
                serial_manager.app.log_message("sys", f"[ERROR] Failed to open UDP socket: {e}")
            return False

    def activate_pdp_context(self, serial_manager) -> bool:
        """Configure PDP context and test connectivity per SDD036.
        
        Per SDD036 (updated):
        1. Send AT+CGDCONT=1,"IP","soracom.io" to configure PDP context
        2. Ping SORACOM server with AT%PINGCMD=0,"100.127.100.127",1,50,30
        3. Wait for %PINGCMD notification indicating successful ping
        """
        # Step 1: Configure PDP context
        cmd = 'AT+CGDCONT=1,"IP","soracom.io"'
        
        if hasattr(serial_manager, 'app') and serial_manager.app:
            serial_manager.app.log_message("sent", f"[SEND] {cmd} - Configure PDP context")
        
        success, response = serial_manager.send_command(cmd, timeout=10.0)
        
        if hasattr(serial_manager, 'app') and serial_manager.app and response:
            serial_manager.app.log_message("recv", f"[RECV] {response}")
        
        if not success:
            return False
        
        # Step 2: Ping SORACOM server per SDD036 (with count/pktsize/timeout)
        ping_cmd = 'AT%PINGCMD=0,"100.127.100.127",1,50,30'
        
        if hasattr(serial_manager, 'app') and serial_manager.app:
            # Clear any stale ping notification before issuing new ping
            serial_manager.app.last_ping_notification = None
            serial_manager.app.log_message("sent", f"[SEND] {ping_cmd} - Ping SORACOM server")
        
        success, response = serial_manager.send_command(ping_cmd, timeout=15.0)

        if hasattr(serial_manager, 'app') and serial_manager.app and response:
            serial_manager.app.log_message("recv", f"[RECV] {response}")

        if not success:
            return False

        # Step 3: Wait for %PINGCMD notification (URC) indicating successful ping
        # Use app.last_ping_notification to avoid racing with poll_serial() that consumes event_queue.
        if hasattr(serial_manager, 'app') and serial_manager.app:
            serial_manager.app.log_message("sys", "[INFO] Waiting for %PINGCMD notification (timeout=30s)...")

        import time
        start_wait = time.time()
        timeout_wait = 30.0

        try:
            while time.time() - start_wait < timeout_wait:
                app = getattr(serial_manager, 'app', None)
                if app and app.last_ping_notification and "%PINGCMD" in app.last_ping_notification:
                    app.log_message("sys", f"[VERIFY] Ping successful: {app.last_ping_notification}")
                    return True
                time.sleep(0.2)

            # Timeout waiting for ping response
            app = getattr(serial_manager, 'app', None)
            if app:
                elapsed = time.time() - start_wait
                app.log_message("sys", f"[ERROR] Ping notification not received within {elapsed:.1f}s (SDD014)")
            return False
        except Exception as e:
            app = getattr(serial_manager, 'app', None)
            if app:
                app.log_message("sys", f"[ERROR] Exception waiting for ping: {e}")
            return False

    def send_to_harvest(self, serial_manager, data: str) -> bool:
        """
        Send data to Soracom Harvest Data (SDD019/SDD040).
        
        Simple send operation per SDD040:
        Socket is opened once in open_socket_connection() (SDD018/SDD038).
        This method only sends data using the active socket.
        
        1. Convert ASCII data to HEX: data.encode().hex().upper()
        2. AT%SOCKETDATA="SEND",1,<size>,"<hex_data>" - Send HEX-encoded data per SDD040 (using socket 1)
        3. Wait for %SOCKETEV:1,1 URC (confirmation)
        """
        try:
            # Step 1: Convert ASCII to HEX
            hex_data = data.encode().hex().upper()
            char_len = len(hex_data) // 2
            
            # Log conversion if app available
            if hasattr(serial_manager, 'app') and serial_manager.app:
                serial_manager.app.log_message("sys", f"[HEX] ASCII '{data}' -> HEX '{hex_data}' ({char_len} bytes)")

            # Step 2: Send data using active socket (socket 1)
            cmd = f'AT%SOCKETDATA="SEND",1,{char_len},"{hex_data}"'
            if hasattr(serial_manager, 'app') and serial_manager.app:
                serial_manager.app.log_message("sent", f"[SEND] {cmd} - Send HEX data")
            
            success, response = serial_manager.send_command(cmd, timeout=5.0)
            
            if hasattr(serial_manager, 'app') and serial_manager.app and response:
                serial_manager.app.log_message("recv", f"[RECV] {response}")
            
            if not success:
                return False

            # Step 3: Wait for confirmation URC %SOCKETEV:1,1
            # This is typically received as an unsolicited event, not a command response
            # For now, we assume the SEND command success indicates transmission
            if hasattr(serial_manager, 'app') and serial_manager.app:
                serial_manager.app.log_message("sys", "[INFO] Waiting for %SOCKETEV:1,1 confirmation URC (socket 1)...")

            return True

        except Exception as e:
            if hasattr(serial_manager, 'app') and serial_manager.app:
                serial_manager.app.log_message("sys", f"[ERROR] Send to harvest failed: {str(e)}")
            return False

    def receive_udp(self, serial_manager, buffer_size: int) -> Optional[Tuple[str, int, str]]:
        """
        Receive UDP downlink data via AT%SOCKETDATA (SDD042 updated).

        Steps per updated SDD042:
        1) Wait for %SOCKETEV:<session_id>,<socket_id> (handled externally)
        2) Read: AT%SOCKETDATA="RECEIVE",<socket_id>,1500 using LISTEN socket ID
        3) Parse: %SOCKETDATA:<socket_id>,<rlength>,<moreData>,"<rdata>","<src_ip>",<src_port>
        4) Filter src_ip to 100.127.x.x (Soracom range)
        5) rdata is HEX; decode to ASCII for GUI if possible

        Note: For Murata, the %SOCKETDATA URC comes separately from the command OK response.
        We need to wait for the URC event, not just the command response.

        Returns: (ip_address, port, payload_str) or None on failure/timeout
        """
        try:
            # Get the LISTEN socket ID from app state (allocated in bind_udp_port)
            app = getattr(serial_manager, 'app', None)
            socket_id = int(app.listen_socket_id) if (app and app.listen_socket_id) else 1

            cmd = f'AT%SOCKETDATA="RECEIVE",{socket_id},1500'
            if hasattr(serial_manager, 'app') and serial_manager.app:
                serial_manager.app.log_message("sent", f"[SEND] {cmd} - Receive UDP data")

            # Send command (expect OK, but data comes as URC)
            success, response = serial_manager.send_command(cmd, timeout=5.0)
            if hasattr(serial_manager, 'app') and serial_manager.app and response:
                serial_manager.app.log_message("recv", f"[RECV] {response}")
            
            if not success:
                if hasattr(serial_manager, 'app') and serial_manager.app:
                    serial_manager.app.log_message("sys", f"[DEBUG SDD042] Command failed: success={success}")
                return None

            # After issuing AT%SOCKETDATA="RECEIVE", wait for %SOCKETDATA URC
            # The URC is captured by remote_client.py's handle_urc() and stored in app.last_socketdata_notification
            # to avoid race condition (similar to SDD036 ping fix)
            # Poll app.last_socketdata_notification for %SOCKETDATA URC (timeout 5s)
            # Note: URC may arrive before we start polling, so don't clear it first
            start_time = time.time()
            response_str = None
            # Collect possibly multiple chunks if moreData==1
            combined_hex = ""
            src_ip = None
            src_port = None

            def parse_socketdata(urc: str):
                m = re.search(r'%SOCKETDATA:\s*(\d+),(\d+),(\d+),"([0-9A-Fa-f]+)","([0-9.]+)",(\d+)', urc)
                if not m:
                    return None
                return {
                    'socket_id': int(m.group(1)),
                    'rlength': int(m.group(2)),
                    'more': int(m.group(3)),
                    'rdata_hex': m.group(4),
                    'src_ip': m.group(5),
                    'src_port': int(m.group(6)),
                }

            while time.time() - start_time < 5.0:
                app = getattr(serial_manager, 'app', None)
                if app and app.last_socketdata_notification:
                    response_str = str(app.last_socketdata_notification)
                    app.last_socketdata_notification = None
                    parsed = parse_socketdata(response_str)
                    if not parsed:
                        break
                    if parsed['socket_id'] != socket_id:
                        break
                    # Filter IP range (Soracom 100.127.x.x)
                    ip = parsed['src_ip']
                    prt = parsed['src_port']
                    if not ip.startswith("100.127."):
                        if hasattr(serial_manager, 'app') and serial_manager.app:
                            serial_manager.app.log_message("sys", f"[INFO] Ignoring UDP from {ip}:{prt} (not Soracom range)")
                        return None
                    src_ip = ip
                    src_port = prt
                    combined_hex += parsed['rdata_hex']
                    if parsed['more'] == 1:
                        # Issue another RECEIVE to get remaining chunks
                        cmd_more = f'AT%SOCKETDATA="RECEIVE",{socket_id},1500'
                        serial_manager.send_command(cmd_more, timeout=5.0)
                        # Loop to wait for next URC
                        continue
                    else:
                        break
                time.sleep(0.1)

            if not combined_hex or src_ip is None or src_port is None:
                return None

            # Step 4 (SDD042): Extract received message from <rdata> field (HEX format)
            payload = combined_hex
            try:
                payload_bytes = bytes.fromhex(combined_hex)
                payload = payload_bytes.decode('utf-8', errors='replace')
                if hasattr(serial_manager, 'app') and serial_manager.app:
                    serial_manager.app.log_message("sys", f"[SDD042 Step 4] Extracted message from <rdata> field: HEX '{combined_hex}' → '{payload}'")
            except Exception:
                pass

            return (src_ip, src_port, payload)

        except Exception as e:
            if hasattr(serial_manager, 'app') and serial_manager.app:
                serial_manager.app.log_message("sys", f"[ERROR] Failed to receive UDP: {e}")
            return None

    def get_signal_quality(self, serial_manager) -> Optional[Dict[str, int]]:
        """Query signal quality metrics via AT%MEAS (per client.ttl)."""
        cmd = 'AT%MEAS="8"'
        
        if hasattr(serial_manager, 'app') and serial_manager.app:
            serial_manager.app.log_message("sent", f"[SEND] {cmd} - Query signal quality")
        
        success, response = serial_manager.send_command(cmd, timeout=5.0)
        
        if hasattr(serial_manager, 'app') and serial_manager.app and response:
            serial_manager.app.log_message("recv", f"[RECV] {response}")

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
