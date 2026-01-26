"""
Remote Client Application
Implements Software Requirements Specification (SRS):
- REQ002: Remote Client Application GUI (Level 2.0)
- REQ004: Connection Status Display (Level 2.1)
- REQ005: Send Messages (Level 2.2)
- REQ006: Receive Messages (Level 1.1)
- REQ007: Message Log via Serial Console with Timestamps (Level 2.4)

Design specified in Software Design Document (SDD):
- SDD001: Remote Client Application GUI Layout (Level 1.0)
- SDD003: Python + Tkinter (Level 3.0)
- SDD005: Supported IoT Devices (Level 5.0) - Nordic Thingy:91 X and Murata Type 1SC-NTN
- SDD006: Connection Status Design (Level 1.1) - Green/Yellow/Red indicators
- SDD007: Connect to IoT Device via Serial (Level 7.2)
- SDD009: Remote Client Application functions (Level 7)
- SDD010: Send Messages Design (Level 1.2)
- SDD011: Received Messages Design (Level 1.3)
- SDD012: Message Log Design (Level 1.4) - Filtering and clear log features
- SDD013: Establish connection with cellular network (Level 7.3) - AT commands for LTE-M setup
- SDD014: PDP Context Configuration Design (Level 7.4) - SORACOM APN configuration
- SDD015: Signal Quality Monitoring Design (Level 7.5) - RSRP monitoring with GUI display
- SDD016: IoT device configuration sequence (Level 7.1) - Complete startup sequence
- SDD017: AT commands (Level 6) - Implement timeout, response waiting, and 100ms delay per ITU-T V.250
- SDD018: Open UDP socket connection to Soracom Harvest Data (Level 7.6)
- SDD030: Device Profile Pattern Architecture (Level 1.5) - Support multiple IoT device types
"""

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
from datetime import datetime
import threading
import queue
import serial
import serial.tools.list_ports

from device_profiles import DeviceProfileFactory



class SerialManager:
    """Manages serial communication with IoT device (SDD007, SDD009)."""
    
    def __init__(self, app=None):
        self.app = app  # Reference to application for GUI updates
        self.serial_port = None
        self.is_connected = False
        self.receive_thread = None
        self.receive_queue = queue.Queue()  # For backwards compatibility
        self.response_queue = queue.Queue()  # SDD017: For AT command responses (OK, ERROR, etc.)
        self.event_queue = queue.Queue()     # For URCs (unsolicited events starting with +)
        self.stop_event = threading.Event()
        self.command_lock = threading.Lock()  # SDD017: Lock to ensure only one command at a time
    
    @staticmethod
    def list_ports():
        """Get list of available COM ports."""
        ports = serial.tools.list_ports.comports()
        return [(p.device, p.description) for p in ports]
    
    def connect(self, port, baudrate):
        """Establish serial connection (SDD007)."""
        try:
            self.serial_port = serial.Serial(
                port=port,
                baudrate=baudrate,
                timeout=1,
                write_timeout=1
            )
            self.is_connected = True
            self.stop_event.clear()
            
            # Start receive thread
            self.receive_thread = threading.Thread(
                target=self._receive_loop, daemon=True
            )
            self.receive_thread.start()
            return True, f"Connected to {port} @ {baudrate} baud"
        except Exception as e:
            return False, str(e)
    
    def disconnect(self):
        """Close serial connection."""
        self.stop_event.set()
        if self.serial_port and self.serial_port.is_open:
            self.serial_port.close()
        self.is_connected = False
        return True, "Disconnected"
    
    def send_command(self, command, timeout=3.0):
        """Send AT command to device (SDD005, SDD007, SDD010, SDD017).
        
        SDD017: Implement timeout procedure per ITU-T V.250:
        - Wait for appropriate response from modem using lock to ensure sequential sending
        - Implement timeout to prevent indefinite waiting
        - Enforce 100ms delay after receiving result code
        - Log interactions for debugging
        - Implement error handling for unexpected responses
        """
        import time
        if not self.is_connected:
            return False, "Not connected"
        
        with self.command_lock:  # SDD017: Ensure only one command is sent at a time
            try:
                # Format as AT command if needed
                if not command.upper().startswith("AT"):
                    command = f"AT+{command}"
                
                # Send AT command
                self.serial_port.write((command + "\r\n").encode())
                
                # Wait for response with timeout (SDD017 - timeout procedure)
                # Collect responses until we get OK or ERROR
                responses = []
                start_time = time.time()
                while time.time() - start_time < timeout:
                    try:
                        msg = self.response_queue.get(timeout=0.1)  # Use blocking get with short timeout
                        responses.append(msg)
                        # Stop waiting when we get a result code (OK, ERROR)
                        if msg.startswith("OK") or msg.startswith("ERROR"):
                            break
                    except queue.Empty:
                        continue
                
                # If no response within timeout, return timeout error (SDD017)
                if not responses:
                    return False, f"Timeout: No response after {timeout}s"
                
                # Enforce 100ms delay after receiving result code per SDD017/ITU-T V.250
                time.sleep(0.1)
                
                return True, " | ".join(responses)
            except Exception as e:
                return False, str(e)
    
    def _receive_loop(self):
        """Receive data from device (SDD009, SDD011).
        Separates responses from events per SDD017.
        """
        import time
        import serial
        buffer = ""
        while not self.stop_event.is_set() and self.is_connected:
            try:
                if self.serial_port and self.serial_port.in_waiting:
                    data = self.serial_port.read(self.serial_port.in_waiting)
                    buffer += data.decode('utf-8', errors='ignore')
                    
                    # Extract complete lines
                    while '\r\n' in buffer or '\n' in buffer:
                        if '\r\n' in buffer:
                            line, buffer = buffer.split('\r\n', 1)
                        else:
                            line, buffer = buffer.split('\n', 1)
                        
                        if line.strip():
                            # Separate URCs (events) from responses (SDD017)
                            # URCs start with + or % (SDD015: %CESQ notifications)
                            if line.strip().startswith('+') or line.strip().startswith('%'):
                                self.event_queue.put(line.strip())
                            else:
                                # OK, ERROR, and other responses
                                self.response_queue.put(line.strip())
                            # Also put in receive_queue for backwards compatibility
                            self.receive_queue.put(line.strip())
                else:
                    # Small sleep to avoid busy-waiting
                    time.sleep(0.01)
            except serial.SerialException as e:
                # Serial port disconnected or became unavailable
                self.log_message(f"Serial port disconnected: {e}")
                self.is_connected = False
                # Update GUI connection status on main thread
                if self.app:
                    self.app.root.after(0, lambda: self.app.status_label.config(text="Status: Disconnected (Device Unplugged)"))
                break  # Exit receive loop cleanly
            except Exception as e:
                # Log other unexpected errors
                self.log_message(f"Error in receive loop: {e}")
                import traceback
                traceback.print_exc()
                pass
    
    def get_message(self):
        """Get received message from queue."""
        try:
            return self.receive_queue.get_nowait()
        except queue.Empty:
            return None


class RemoteClientApplication:
    """Remote Client Application implementing REQ002-REQ007 per SDD001-SDD030."""
    
    def __init__(self, root):
        self.root = root
        self.root.title("Remote Client Application")
        self.root.geometry("900x700")
        
        # Serial manager (SDD007, SDD009)
        self.serial = SerialManager(app=self)
        self.is_connected = False
        self.connection_state = "disconnected"  # SDD006: disconnected, connecting, connected
        self.urc_monitoring_active = False
        self.network_registered = False  # SDD014: track +CEREG registration (stat 1 or 5)
        self.last_ping_notification = None  # Track %PINGCMD URC to avoid queue races (SDD036)
        
        # Device Profile (SDD030) - will be initialized after GUI is built
        self.device_type = tk.StringVar(value="nordic_thingy91x")  # Default device
        self.device_profile = None
        
        # Signal Quality Monitoring (SDD015)
        self.signal_quality = {"rssi": 0, "rsrp": 0}
        self.rssi_threshold = -110  # dBm threshold for acceptable signal
        self.rsrp_threshold = -130  # dBm threshold for acceptable signal

        # UDP receive configuration (SDD026, SDD027, SDD028)
        self.udp_port = 55555  # SDD026: Port for UDP communications
        self.udp_buffer_size = 1500  # SDD042: read up to 1500 bytes
        self.udp_bound = False
        
        # Variables
        self.selected_port = tk.StringVar()
        self.selected_baud = tk.StringVar(value="9600")
        
        # Shared state for URC race condition mitigation (SDD036, SDD042)
        self.last_ping_notification = None  # SDD036: %PINGCMD URC
        self.last_socketdata_notification = None  # SDD042: %SOCKETDATA URC
        self.last_socketcmd_notification = None  # SDD042: %SOCKETCMD URC for bind verification
        self.listen_socket_id = None  # SDD042: Socket ID for LISTEN (downlink receive)
        
        # Build GUI per SDD001 (2 columns x 3 rows layout)
        self.build_gui()
        
        # Initialize device profile after GUI is built (SDD030)
        self._update_device_profile()
        
        # Start polling (SDD011, SDD013, SDD015)
        self.poll_serial()
    
    def _update_device_profile(self):
        """Update device profile based on selected device type (SDD030)."""
        try:
            self.device_profile = DeviceProfileFactory.create(self.device_type.get())
            device_info = self.device_profile.get_device_info()
            self.log_message("sys", f"Device profile: {device_info['name']} by {device_info['manufacturer']}")
        except ValueError as e:
            self.log_message("sys", f"[ERROR] {str(e)}")
            self.device_profile = DeviceProfileFactory.create("nordic_thingy91x")  # Fallback to default

    
    def build_gui(self):
        """Build GUI layout per SDD001 - 3 rows: Connection Status | Chat Area | Message Log"""
        main = ttk.Frame(self.root, padding="10")
        main.grid(row=0, column=0, sticky='nsew')
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main.columnconfigure(0, weight=1)
        main.rowconfigure(0, weight=0)
        main.rowconfigure(1, weight=1)
        main.rowconfigure(2, weight=1)
        
        # Row 0: REQ004 - Connection Status (SDD006, SDD007)
        self.build_connection_panel(main)
        
        # Row 1: Unified Chat Area (REQ005 + REQ006 - SDD010, SDD011)
        self.build_chat_panel(main)
        
        # Row 2: REQ007 - Message Log via Serial Console (SDD012)
        self.build_log_panel(main)
    
    def build_connection_panel(self, parent):
        """REQ004: Connection Status Display (SDD006, SDD007, SDD015, SDD030)."""
        frame = ttk.LabelFrame(
            parent, text="Connection Status",
            padding="10"
        )
        frame.grid(row=0, column=0, columnspan=2, sticky='nsew', padx=5, pady=5)
        frame.columnconfigure(1, weight=1)
        
        # Status indicator
        status_row = ttk.Frame(frame)
        status_row.grid(row=0, column=0, columnspan=2, sticky='ew', pady=5)
        
        self.status_canvas = tk.Canvas(status_row, width=30, height=30, bg='white')
        self.status_canvas.pack(side=tk.LEFT, padx=5)
        self.update_status()
        
        self.status_label = ttk.Label(status_row, text="Status: Disconnected", font=("Arial", 11, "bold"))
        self.status_label.pack(side=tk.LEFT, padx=10)
        
        # Signal Quality Display (SDD015 - RSRP only)
        signal_row = ttk.Frame(frame)
        signal_row.grid(row=0, column=2, columnspan=2, sticky='e', pady=5)
        
        ttk.Label(signal_row, text="RSRP: ", font=("Arial", 9)).pack(side=tk.LEFT, padx=2)
        self.rsrp_label = ttk.Label(signal_row, text="-- dBm", font=("Arial", 9, "bold"))
        self.rsrp_label.pack(side=tk.LEFT, padx=2)
        
        # Device Selection (SDD030)
        device_frame = ttk.LabelFrame(frame, text="Device Configuration", padding="5")
        device_frame.grid(row=1, column=0, columnspan=2, sticky='ew', pady=5)
        device_frame.columnconfigure(1, weight=1)
        
        ttk.Label(device_frame, text="Device:").grid(row=0, column=0, sticky='w', padx=5)
        device_combo = ttk.Combobox(
            device_frame, textvariable=self.device_type, width=30, state='readonly',
            values=["nordic_thingy91x", "murata_type1sc_ntng"]
        )
        device_combo.grid(row=0, column=1, sticky='ew', padx=5)
        device_combo.bind("<<ComboboxSelected>>", lambda e: self._update_device_profile())
        
        # Serial Configuration
        config_frame = ttk.LabelFrame(frame, text="Serial Configuration", padding="5")
        config_frame.grid(row=2, column=0, columnspan=2, sticky='ew', pady=5)
        config_frame.columnconfigure(1, weight=1)
        
        ttk.Label(config_frame, text="Port:").grid(row=0, column=0, sticky='w', padx=5)
        port_combo = ttk.Combobox(config_frame, textvariable=self.selected_port, width=20, state='readonly')
        port_combo.grid(row=0, column=1, sticky='ew', padx=5)
        self.refresh_ports(port_combo)
        
        ttk.Button(config_frame, text="Refresh", command=lambda: self.refresh_ports(port_combo)).grid(row=0, column=2, padx=5)
        
        ttk.Label(config_frame, text="Baud:").grid(row=1, column=0, sticky='w', padx=5)
        baud_combo = ttk.Combobox(config_frame, textvariable=self.selected_baud, width=20, state='readonly',
                                  values=["9600", "19200", "38400", "57600", "115200"])
        baud_combo.grid(row=1, column=1, sticky='ew', padx=5)
        
        # Buttons
        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=3, column=0, columnspan=2, sticky='w', pady=10, padx=5)
        
        self.connect_btn = ttk.Button(btn_frame, text="Connect", command=self.connect)
        self.connect_btn.pack(side=tk.LEFT, padx=5)
        
        self.disconnect_btn = ttk.Button(btn_frame, text="Disconnect", command=self.disconnect, state='disabled')
        self.disconnect_btn.pack(side=tk.LEFT, padx=5)

    
    def build_chat_panel(self, parent):
        """REQ005 + REQ006: Unified Chat Area for sending and receiving messages (SDD001, SDD010, SDD011)."""
        frame = ttk.LabelFrame(parent, text="Chat Area", padding="10")
        frame.grid(row=1, column=0, sticky='nsew', padx=5, pady=5)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)
        frame.rowconfigure(2, weight=0)
        
        # Display area for messages (both sent and received)
        self.chat_display = scrolledtext.ScrolledText(frame, height=15, width=80, state='disabled')
        self.chat_display.grid(row=0, column=0, sticky='nsew', pady=5)
        
        # Configure tags for message types
        self.chat_display.tag_configure('sent', foreground='blue')
        self.chat_display.tag_configure('recv', foreground='green')
        self.chat_display.tag_configure('sys', foreground='red')
        
        # Input area for sending commands
        ttk.Label(frame, text="Command Input:", font=("Arial", 9)).grid(row=1, column=0, sticky='w', pady=(10, 5))
        
        input_frame = ttk.Frame(frame)
        input_frame.grid(row=2, column=0, sticky='ew', pady=5)
        input_frame.columnconfigure(0, weight=1)
        
        self.command_input = tk.Text(input_frame, height=3, width=80)
        self.command_input.grid(row=0, column=0, sticky='ew', padx=(0, 5))
        
        self.send_btn = ttk.Button(input_frame, text="Send Command", command=self.send_message)
        self.send_btn.grid(row=0, column=1, sticky='n')
    
    def build_send_panel(self, parent):
        """DEPRECATED - Use build_chat_panel instead."""
        pass
    
    def build_receive_panel(self, parent):
        """DEPRECATED - Use build_chat_panel instead."""
        pass
    
    def build_log_panel(self, parent):
        """REQ007: Message Log via Serial Console with Timestamps (SDD012)."""
        frame = ttk.LabelFrame(parent, text="Message Log", padding="10")
        frame.grid(row=2, column=0, columnspan=2, sticky='nsew', padx=5, pady=5)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(1, weight=1)
        
        # Control panel for filter and clear (SDD012)
        control_frame = ttk.Frame(frame)
        control_frame.grid(row=0, column=0, sticky='ew', pady=5)
        control_frame.columnconfigure(1, weight=1)
        
        ttk.Label(control_frame, text="Filter:").pack(side=tk.LEFT, padx=5)
        
        self.filter_var = tk.StringVar(value="All")
        filter_combo = ttk.Combobox(
            control_frame, textvariable=self.filter_var, width=15, 
            state='readonly', values=["All", "Sent", "Received", "System"]
        )
        filter_combo.pack(side=tk.LEFT, padx=5)
        filter_combo.bind("<<ComboboxSelected>>", lambda e: self.apply_log_filter())
        
        ttk.Button(control_frame, text="Clear Log", command=self.clear_log_with_confirmation).pack(side=tk.LEFT, padx=5)
        
        # Log display
        self.log_text = scrolledtext.ScrolledText(frame, height=10, width=80, state='disabled')
        self.log_text.grid(row=1, column=0, sticky='nsew')
        
        # Configure tags
        self.log_text.tag_configure('sent', foreground='blue')
        self.log_text.tag_configure('recv', foreground='green')
        self.log_text.tag_configure('sys', foreground='red')
        
        # Store full log for filtering
        self.full_log = []
    
    def update_status(self):
        """Update status indicator (SDD006).
        Green: connected, Yellow: connecting, Red: disconnected.
        """
        if self.connection_state == "connected":
            color = "green"
        elif self.connection_state == "connecting":
            color = "yellow"
        else:
            color = "red"
        self.status_canvas.delete("all")
        self.status_canvas.create_oval(5, 5, 25, 25, fill=color, outline="black")
    
    def refresh_ports(self, combo):
        """Refresh available ports."""
        ports = self.serial.list_ports()
        if ports:
            combo['values'] = [f"{p[0]} - {p[1]}" for p in ports]
            self.selected_port.set(f"{ports[0][0]} - {ports[0][1]}")
        else:
            combo['values'] = ["No ports"]
            self.selected_port.set("No ports")
    
    def connect(self):
        """Connect to IoT device (SDD006, SDD007) and establish cellular network (SDD013).
        Initialization runs in a separate thread to avoid blocking the GUI.
        """
        # reset registration tracking on each connect attempt
        self.network_registered = False

        if not self.selected_port.get() or "No ports" in self.selected_port.get():
            messagebox.showerror("Error", "Select a valid port")
            return
        
        port = self.selected_port.get().split(" - ")[0]
        baud = int(self.selected_baud.get())
        
        # Set connecting state (SDD006)
        self.connection_state = "connecting"
        self.status_label.config(text="Status: Connecting...")
        self.update_status()
        self.connect_btn.config(state='disabled')
        
        success, msg = self.serial.connect(port, baud)
        if success:
            self.is_connected = True
            self.log_message("sys", f"Connected to {port} @ {baud} baud")
            
            # Device-specific handshake (SDD031 Thingy:91 X, SDD032 Murata)
            if not self._handshake_device():
                self.disconnect()
                return
            
            # Update UI to show connected (SDD006)
            self.connection_state = "connected"
            self.status_label.config(text="Status: Connected")
            self.update_status()
            self.disconnect_btn.config(state='normal')
            self.send_btn.config(state='normal')
            
            # Initialize cellular network connection in separate thread (SDD013, SDD016)
            # This runs the device configuration sequence: SDD007 -> SDD013 -> (SDD014 + SDD015 + SDD018)
            init_thread = threading.Thread(target=self.initialize_cellular_network, daemon=True)
            init_thread.start()
        else:
            # Return to disconnected state on failure (SDD006)
            self.connection_state = "disconnected"
            self.update_status()
            self.connect_btn.config(state='normal')
            messagebox.showerror("Connection Error", msg)

    def _handshake_device(self) -> bool:
        """Perform device-specific handshake per SDD031/SDD032."""
        device = self.device_type.get().lower()
        # Thingy:91 X (SDD031): send AT and expect OK
        if device.startswith("nordic") or "thingy" in device:
            self.log_message("sent", "[SEND] AT")
            success, resp = self.serial.send_command("AT")
            if success and resp:
                self.log_message("recv", f"[RECV] {resp}")
            if not success:
                self.log_message("sys", "AT handshake failed (no response)")
                messagebox.showerror("Connection Error", "AT handshake failed (no response)")
            return success

        # Murata Type 1SC-NTN (SDD032): send ATZ and wait for %BOOTEV:0 URC
        if "murata" in device or "type1sc" in device:
            import time
            self.log_message("sent", "[SEND] ATZ")
            # Use raw write inside command lock to avoid races
            with self.serial.command_lock:
                try:
                    self.serial.serial_port.write(("ATZ\r\n").encode())
                except Exception as e:
                    self.log_message("sys", f"[ERROR] Failed to send ATZ: {e}")
                    messagebox.showerror("Connection Error", f"Failed to send ATZ: {e}")
                    return False

                got_boot = False
                start = time.time()
                timeout = 30.0  # Increased timeout: %BOOTEV:0 can be delayed for Murata
                self.log_message("sys", f"[INFO] Waiting for %BOOTEV:0 (timeout={timeout}s)...")
                while time.time() - start < timeout:
                    try:
                        evt = self.serial.event_queue.get(timeout=0.2)
                        self.log_message("recv", f"[RECV] {evt}")
                        if "%BOOTEV:0" in evt:
                            elapsed = time.time() - start
                            self.log_message("sys", f"[SUCCESS] Murata handshake complete (%BOOTEV:0 received in {elapsed:.1f}s)")
                            got_boot = True
                            break
                    except queue.Empty:
                        pass
                    # Also log plain responses if any
                    try:
                        resp = self.serial.response_queue.get_nowait()
                        self.log_message("recv", f"[RECV] {resp}")
                    except queue.Empty:
                        pass

                if not got_boot:
                    elapsed = time.time() - start
                    self.log_message("sys", f"[ERROR] Murata handshake failed: %BOOTEV:0 not received within {elapsed:.1f}s")
                    messagebox.showerror("Connection Error", f"Murata handshake failed: %BOOTEV:0 not received within {timeout}s")
                    return False
                return True

        # Fallback to generic AT
        self.log_message("sent", "[SEND] AT")
        success, resp = self.serial.send_command("AT")
        if success and resp:
            self.log_message("recv", f"[RECV] {resp}")
        if not success:
            self.log_message("sys", "AT handshake failed (no response)")
            messagebox.showerror("Connection Error", "AT handshake failed (no response)")
        return success
    
    def initialize_cellular_network(self):
        """Initialize cellular network connection per SDD016/SDD030.
        
        Per SDD016 sequence:
        1. Establish Cellular Connection (SDD013) - send AT commands and wait for +CEREG URC
        2. If successful, then Signal Quality Monitoring (SDD015)
        3. If successful, then Activate PDP Context (SDD014)
        4. If successful, then Open UDP socket (SDD018)
        5. If successful, then enable Receive Messages (SDD027)
        """
        self.log_message("sys", f"Initializing cellular network (SDD016/SDD030, device: {self.device_type.get()})...")
        
        if not self.device_profile:
            self.log_message("sys", "[ERROR] Device profile not initialized")
            return False
        
        # Step 1: Send initialization AT commands (SDD013)
        success = self.device_profile.initialize_network(self.serial)
        
        if not success:
            self.log_message("sys", "[ERROR] Device network initialization failed (SDD013)")
            return False
        
        self.log_message("sys", "[SUCCESS] AT commands sent, waiting for network registration (SDD013)...")
        
        # Step 2: Wait for +CEREG URC with stat=1/5 per SDD013
        self.monitor_urcs()  # Start monitoring URCs
        
        # NTN networks require longer timeout (120s) than terrestrial LTE-M (60s)
        timeout = 120 if "murata" in self.device_type.get().lower() else 60
        self.log_message("sys", f"[INFO] Using {timeout}s timeout for network registration")
        
        if not self.wait_for_network_registration(timeout=timeout):
            self.log_message("sys", f"[ERROR] Network registration timeout - +CEREG 1/5 not received within {timeout}s (SDD013)")
            return False
        
        self.log_message("sys", "[SUCCESS] Cellular connection established - registered on network (SDD013)")
        
        # Per SDD016: Execute steps sequentially, only if previous step succeeds
        # Step 3: Start Signal Quality Monitoring (SDD015) - runs in parallel with SDD014
        self.monitor_signal_quality()
        
        # Step 4: Activate PDP Context (SDD014)
        success = self.activate_pdp_context()
        if not success:
            self.log_message("sys", "[ERROR] PDP context activation failed (SDD014) - stopping initialization")
            return False
        
        # Step 5: Open UDP Socket (SDD018) - only if SDD014 succeeded
        success = self.open_socket_connection()
        if not success:
            self.log_message("sys", "[ERROR] UDP socket connection failed (SDD018) - stopping initialization")
            return False
        
        # Step 6: Bind UDP port for receiving (SDD027) - only if SDD018 succeeded
        success = self.bind_udp_port()
        if not success:
            self.log_message("sys", "[ERROR] UDP port binding failed (SDD027) - stopping initialization")
            return False
        
        self.log_message("sys", "[SUCCESS] Device initialization complete (SDD016)")
        return True

    
    def monitor_urcs(self):
        """Monitor and handle unsolicited result codes (URCs) from modem (SDD013).
        
        Per SDD013: Network registration confirmed by +CEREG URC with stat=1/5.
        This method just activates URC monitoring - it doesn't execute subsequent steps.
        Per SDD016, subsequent steps are executed only after network registration succeeds.
        """
        # Initialize URC flag
        self.urc_monitoring_active = True
        self.log_message("sys", "URC monitoring active - listening for +CEREG and other URCs (SDD013)")
    
    def handle_urc(self, message):
        """Handle unsolicited result codes from modem (SDD013, SDD015, SDD018).
        
        This interprets URCs to determine current network status and updates connection status.
        Common URCs:
        - +CEREG: Network registration status
        - +CSCON: Connection state notification
        - %CESQ: RSRP notifications (SDD015)
        - +CMT, +CDS, etc: Message/data URCs
        """
        if message.startswith("+CEREG"):
            # Network registration status per SDD013
            try:
                # Parse +CEREG format
                parts = message.split(":")[1].strip().split(",")
                
                # Distinguish query response from URC:
                # Query response: +CEREG: <n>,<stat> - exactly 2 integer parameters
                # URC: +CEREG: <stat>[,<tac>,<ci>,<AcT>,...] - 1 param or includes quoted strings
                
                # Check if this is a query response (AT+CEREG?) being mishandled as URC
                if len(parts) == 2 and '"' not in message:
                    # This is a query response, not a URC - ignore it
                    # Query responses should be handled by send_command(), not as URCs
                    return
                
                self.log_message("sys", f"[URC] Network registration: {message}")
                
                # Parse URC: +CEREG: <stat>[,[<tac>],[<ci>],[<AcT>]...] per revised SDD013
                stat = int(parts[0].strip())  # First parameter is <stat>
                
                # Per SDD013 Note: Handle all <stat> values
                if stat == 1:
                    self.log_message("sys", "[URC] Registered, home network (stat=1)")
                    self.network_registered = True
                elif stat == 5:
                    self.log_message("sys", "[URC] Registered, roaming (stat=5)")
                    self.network_registered = True
                elif stat == 0:
                    self.log_message("sys", "[URC] Not registered, not searching (stat=0)")
                    self.network_registered = False
                elif stat == 2:
                    self.log_message("sys", "[URC] Not registered, searching/attaching (stat=2)")
                    self.network_registered = False
                elif stat == 3:
                    self.log_message("sys", "[URC] Registration denied (stat=3)")
                    self.network_registered = False
                elif stat == 4:
                    self.log_message("sys", "[URC] Unknown, out of coverage (stat=4)")
                    self.network_registered = False
                elif stat == 90:
                    self.log_message("sys", "[URC] Not registered, UICC failure (stat=90)")
                    self.network_registered = False
                else:
                    self.log_message("sys", f"[URC] Unrecognized stat value: {stat}")
                    self.network_registered = False
            except (ValueError, IndexError):
                pass
        elif message.startswith("+CSCON"):
            # Connection state notification per SDD013
            self.log_message("sys", f"[URC] Connection state: {message}")
            try:
                state = int(message.split(":")[1].strip().split(",")[0])
                if state == 1:
                    # Modem indicates connected; attempt to receive pending UDP data (SDD027)
                    threading.Thread(target=self.receive_udp_message, daemon=True).start()
            except Exception:
                pass
        elif message.startswith("%CESQ"):
            # Handle RSRP notification (SDD015)
            self.log_message("sys", f"[URC] Signal quality: {message}")
            try:
                # Parse %CESQ: <rsrp>,<rsrq>,<snr>,<rscp>
                parts = message.split(":")[1].strip().split(",")
                if len(parts) >= 1:
                    rsrp_value = int(parts[0].strip())
                    # Convert to dBm per SDD015: reported_value - 141 = dBm
                    if rsrp_value != 255:  # 255 means not known or not detectable
                        rsrp_dbm = rsrp_value - 141
                        self.signal_quality["rsrp"] = rsrp_dbm
                        self.log_message("sys", f"[SIGNAL] RSRP: {rsrp_dbm} dBm")
                        # Update GUI
                        self.update_signal_quality_display()
                        # Check threshold
                        if rsrp_dbm < self.rsrp_threshold:
                            self.log_message("sys", f"[ALERT] RSRP below threshold ({rsrp_dbm} < {self.rsrp_threshold} dBm)")
            except (ValueError, IndexError):
                pass
        elif message.startswith("%PINGCMD"):
            # Capture ping notification for SDD036 to avoid race with device profile waits
            self.last_ping_notification = message
            self.log_message("sys", f"[URC] Ping result: {message}")
        elif message.startswith("%SOCKETDATA"):
            # Capture socket data URC for SDD042 to avoid race with device profile waits
            self.last_socketdata_notification = message
            self.log_message("sys", f"[URC] %SOCKETDATA: {message}")
        elif message.startswith("%SOCKETCMD"):
            # Capture socket command URC for SDD042 to avoid race with device profile waits
            self.last_socketcmd_notification = message
            self.log_message("sys", f"[URC] %SOCKETCMD: {message}")
        elif message.startswith("%SOCKETEV"):
            # Handle socket event notification per SDD042 (Murata downlink data ready)
            self.log_message("sys", f"[URC] Socket event: {message}")
            try:
                # Parse %SOCKETEV:<session_id>,<socket_id> per updated SDD042
                parts = message.split(":")[1].strip().split(",")
                if len(parts) >= 2:
                    session_id = int(parts[0].strip())
                    socket_id = int(parts[1].strip())
                    # Data available on specified socket; attempt to receive per SDD042 step 2
                    # Check if this matches the LISTEN socket ID (typically socket 2 if socket 1 is OPEN to Harvest)
                    if self.listen_socket_id and socket_id == int(self.listen_socket_id):
                        self.log_message("sys", f"[INFO] Data available on LISTEN socket {socket_id} (session {session_id}) per %SOCKETEV:{session_id},{socket_id} - issuing receive (SDD042)")
                        threading.Thread(target=self.receive_udp_message, daemon=True).start()
                    else:
                        self.log_message("sys", f"[INFO] Socket event on socket {socket_id} (session {session_id}), but LISTEN socket is {self.listen_socket_id}")
            except (ValueError, IndexError):
                pass
        elif message.startswith("%XSOCKET"):
            # Handle socket creation response (SDD018)
            self.log_message("sys", f"[URC] Socket response: {message}")
        else:
            self.log_message("sys", f"[URC] {message}")
    
    def activate_pdp_context(self):
        """Configure PDP context for SORACOM APN (SDD014/SDD035/SDD036).
        
        Delegates to device profile for device-specific configuration:
        - SDD035: Nordic uses AT+CGDCONT
        - SDD036: Murata uses AT+CGDCONT + ping test
        """
        self.log_message("sys", "Configuring PDP context (SDD014)...")

        # Delegate to device profile per SDD035/SDD036
        success = self.device_profile.activate_pdp_context(self.serial)
        
        if success:
            self.log_message("sys", "[SUCCESS] PDP context configured (SDD014)")
        else:
            self.log_message("sys", "[ERROR] PDP context configuration failed (SDD014)")
        
        return success
    
    def wait_for_network_registration(self, timeout=30, interval=0.1):
        """Wait for +CEREG URC with stat=1/5 per SDD013.
        
        Per SDD013: Successful establishment indicated by unsolicited +CEREG notification,
        NOT by querying AT+CEREG?. This function passively waits for the URC.
        """
        import time
        end_time = time.time() + timeout
        while time.time() < end_time:
            if self.network_registered:
                self.log_message("sys", "[VERIFY] Network registration confirmed via +CEREG URC (SDD013)")
                return True
            time.sleep(interval)  # Wait for URC to arrive
        return False
    
    def monitor_signal_quality(self):
        """Monitor signal quality metrics (SDD015).
        
        Subscribe to RSRP notifications using AT%CESQ=1 per SDD015.
        Notifications received as URCs in format: %CESQ: <rsrp>,<rsrq>,<snr>,<rscp>
        """
        self.log_message("sys", "Starting signal quality monitoring (SDD015)...")
        
        # Subscribe to RSRP notifications (SDD015)
        success, response = self.serial.send_command("AT%CESQ=1")
        if success:
            self.log_message("sent", "[SEND] AT%CESQ=1 - Subscribe to RSRP notifications")
            if response:
                self.log_message("recv", f"[RECV] {response}")
            self.log_message("sys", "Subscribed to RSRP notifications - will receive %CESQ URCs")
        else:
            self.log_message("sys", "Failed to subscribe to RSRP notifications")
    
    def open_socket_connection(self):
        """Open UDP socket connection to Soracom Harvest Data (SDD018/SDD037/SDD038).
        
        Delegates to device profile for device-specific socket creation:
        - SDD037: Nordic uses AT#XSOCKET=1,2,0
        - SDD038: Murata uses AT%SOCKETCMD ALLOCATE + ACTIVATE
        """
        self.log_message("sys", "Opening UDP socket connection to Soracom Harvest Data (SDD018)...")
        
        # Delegate to device profile per SDD037/SDD038
        success = self.device_profile.open_socket_connection(self.serial)
        
        if success:
            self.log_message("sys", "[SUCCESS] UDP socket opened successfully for Soracom Harvest Data")
        else:
            self.log_message("sys", "[ERROR] Failed to open UDP socket")
        
        return success

    def bind_udp_port(self):
        """Bind UDP port for receiving downlink messages (SDD041/SDD042).
        
        Per SDD041 (Nordic Thingy:91 X):
        - Use AT#XBIND=<udp_port> to bind UDP port
        
        Per SDD042 (Murata Type 1SC-NTN):
        - Socket 1 is allocated/activated to Harvest in SDD038
        - Enable notifications with AT%SOCKETDATA="ON",1
        """
        if not self.is_connected:
            self.log_message("sys", "[ERROR] Cannot bind UDP port - not connected")
            return False

        self.log_message("sys", f"Binding UDP port {self.udp_port} for downlink (SDD041/SDD042)...")
        success = self.device_profile.bind_udp_port(self.serial, self.udp_port)
        
        if success:
            self.log_message("sys", f"[SUCCESS] UDP port {self.udp_port} bound for receive (SDD041/SDD042)")
            self.udp_bound = True
            return True
        else:
            self.log_message("sys", f"[ERROR] Failed to bind UDP port {self.udp_port} (SDD041/SDD042)")
            self.udp_bound = False
            return False

    def receive_udp_message(self):
        """Receive UDP message using device profile (SDD041/SDD042).
        
        Per SDD041 (Nordic Thingy:91 X):
        - After +CSCON:1 notification, call AT#XRECVFROM=<buffer_size>
        - Parse response to extract ip_addr, port, and payload
        - Display only if ip_addr="100.127.10.16"
        
        Per SDD042 (Murata Type 1SC-NTN):
        - Bind receive port via AT%SOCKETCMD="ALLOCATE",1,"UDP","LISTEN","0.0.0.0",<udp_port> then ACTIVATE
        - After %SOCKETEV:1,1 notification, call AT%SOCKETDATA="RECEIVE",1,1500
        - Parse %SOCKETDATA:<socket_id>,<rlength>,<moreData>,"<rdata>","<src_ip>",<src_port>
        - If <moreData>==1, keep reading until 0; decode HEX to ASCII
        - Display for Soracom IP range 100.127.x.x
        
        Device profile handles device-specific reception logic.
        Returns: (ip_address, port, payload) or None on failure/timeout
        """
        if not (self.is_connected and self.udp_bound):
            self.log_message("sys", "[INFO] Skipping UDP receive - not connected or not bound")
            return

        # Use device profile to receive (SDD041/SDD042)
        result = self.device_profile.receive_udp(self.serial, self.udp_buffer_size)
        
        if result:
            ip_addr, port, payload = result
            self.log_message("sys", f"[SUCCESS] Received UDP from {ip_addr}:{port} (SDD041/SDD042)")
            self.display_chat_message("recv", f"[RECV] {payload}")
        else:
            # No message received - this is normal for polling
            pass
    
    def update_signal_quality_display(self):
        """Update GUI signal quality display (SDD015 - RSRP only)."""
        try:
            rsrp_text = f"{self.signal_quality['rsrp']} dBm" if self.signal_quality["rsrp"] != 0 else "-- dBm"
            self.rsrp_label.config(text=rsrp_text)
        except:
            pass
    
    def disconnect(self):
        """Disconnect from device (SDD006)."""
        success, msg = self.serial.disconnect()
        self.is_connected = False
        self.connection_state = "disconnected"
        self.urc_monitoring_active = False
        self.network_registered = False
        self.udp_bound = False
        self.status_label.config(text="Status: Disconnected")
        self.update_status()
        self.connect_btn.config(state='normal')
        self.disconnect_btn.config(state='disabled')
        self.send_btn.config(state='disabled')
        self.log_message("sys", msg)
    
    def send_message(self):
        """Send message from GUI input (REQ005, SDD019).
        
        Per SDD019: After message is received from GUI message input, send to Soracom Harvest Data
        using AT command #XSENDTO=<url>,<port>[,<data>].
        """
        if not self.is_connected:
            messagebox.showwarning("Not Connected", "Connect first")
            return
        
        msg = self.command_input.get("1.0", "end").strip()
        if not msg:
            messagebox.showwarning("Empty", "Enter a message")
            return
        
        # Send to Soracom Harvest Data per SDD019
        self.send_to_harvest_data(msg)
        
        self.command_input.delete("1.0", "end")
    
    def send_to_harvest_data(self, data):
        """Send message to Soracom Harvest Data (SDD019/SDD039/SDD040).
        
        Delegates to device profile for device-specific send operations:
        - SDD039: Nordic uses AT#XSENDTO with ASCII payload
        - SDD040: Murata uses AT%SOCKETDATA with HEX-encoded payload
        """
        if not self.is_connected:
            self.log_message("sys", "[ERROR] Not connected - cannot send to Harvest Data")
            return False
        
        if not data:
            self.log_message("sys", "[ERROR] Empty message - cannot send to Harvest Data")
            return False
        
        # Use device profile to send per SDD039/SDD040
        success = self.device_profile.send_to_harvest(self.serial, data)
        
        if success:
            self.log_message("sys", "[SUCCESS] Sent message to Soracom Harvest Data (SDD019)")
            self.display_chat_message("sent", f"[SEND] {data}")
            return True
        else:
            self.log_message("sys", "[ERROR] Failed to send message to Soracom Harvest Data (SDD019)")
            return False
    
    def log_message(self, tag, msg):
        """Log message with timestamp (REQ007, SDD012)."""
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{ts}] {msg}"

        # Store for filtering (SDD012)
        self.full_log.append((tag, log_entry))
        
        self.log_text.config(state='normal')
        self.log_text.insert('end', log_entry + "\n", tag)
        self.log_text.config(state='disabled')
        self.log_text.see('end')
    
    def display_chat_message(self, tag, msg):
        """Display message in chat area with timestamp (REQ005, REQ006, SDD001)."""
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        chat_entry = f"[{ts}] {msg}\n"
        
        self.chat_display.config(state='normal')
        self.chat_display.insert('end', chat_entry, tag)
        self.chat_display.config(state='disabled')
        self.chat_display.see('end')
    
    def apply_log_filter(self):
        """Filter log entries by type (SDD012)."""
        filter_type = self.filter_var.get()
        
        # Clear display
        self.log_text.config(state='normal')
        self.log_text.delete('1.0', 'end')
        
        # Re-display filtered entries
        for tag, entry in self.full_log:
            if filter_type == "All":
                self.log_text.insert('end', entry + "\n", tag)
            elif filter_type == "Sent" and tag == "sent":
                self.log_text.insert('end', entry + "\n", tag)
            elif filter_type == "Received" and tag == "recv":
                self.log_text.insert('end', entry + "\n", tag)
            elif filter_type == "System" and tag == "sys":
                self.log_text.insert('end', entry + "\n", tag)
        
        self.log_text.config(state='disabled')
        self.log_text.see('end')
    
    def clear_log_with_confirmation(self):
        """Clear log with confirmation prompt (SDD012)."""
        if messagebox.askyesno("Clear Log", "Are you sure you want to clear the message log? This cannot be undone."):
            self.full_log.clear()
            self.log_text.config(state='normal')
            self.log_text.delete('1.0', 'end')
            self.log_text.config(state='disabled')
            self.log_message("sys", "Log cleared by user")
    
    def poll_serial(self):
        """Poll for unsolicited events (URCs) only (REQ006, SDD011, SDD013).
        Command responses are handled inside send_command to comply with SDD017.
        Displays received messages in unified chat area (SDD001, SDD011).
        Per SDD011: Chat must NOT display AT command responses or URCs from the modem.
        """
        if self.is_connected:
            while True:
                try:
                    msg = self.serial.event_queue.get_nowait()
                except queue.Empty:
                    break
                
                # Per SDD011: Only display actual messages, not modem responses or URCs
                # URCs (starting with +, %, #) are handled separately, not displayed in chat
                # The chat area is reserved for messages from Communicator Application only
                
                # Log all received data for debugging (SDD012)
                self.log_message("recv", f"[RECV] {msg}")
                
                # Handle URCs separately (SDD013, SDD015, etc) without displaying in chat
                self.handle_urc(msg)
        
        self.root.after(100, self.poll_serial)

def main():
    root = tk.Tk()
    app = RemoteClientApplication(root)
    root.mainloop()


if __name__ == "__main__":
    main()

