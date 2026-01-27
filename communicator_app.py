"""
Communicator Application
Implements REQ008-REQ011 per SDD002, SDD004, SDD020-SDD026.
- REQ008: Connection Status Display (Level 3.1) - with session (online/offline) indicator per SDD024
- REQ009: Send Messages (Level 3.2)
- REQ010: Receive Messages (Level 3.3)
- REQ011: Message Log with timestamps (Level 3.4)

Design references:
- SDD002: Communicator Application GUI Layout
- SDD004: Communicator Application programming language (Python + Tkinter)
- SDD020: Communicator Application Functions (placeholder)
- SDD021: Generating SORACOM API Key/Token with ID and Password
- SDD022: (SDD021 implementation)
- SDD023: List SIMs Associated with the User Account
- SDD024: Session Status Indication in GUI (online/offline indicator color)
- SDD025: Sending Data from Communicator to Remote Client (via Soracom downlink when SIM online)
- SDD026: UDP Transmission (port 55555 for all communications)
"""
from __future__ import annotations

import base64
import json
import os
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional, Tuple

import requests
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, simpledialog
import geopandas as gpd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import io
from PIL import Image, ImageTk


@dataclass
class HarvestMessage:
    timestamp_ms: int
    text: str

    @property
    def timestamp(self) -> datetime:
        return datetime.fromtimestamp(self.timestamp_ms / 1000.0)


class SoracomApiClient:
    """Lightweight Soracom API client for authentication, downlink, and Harvest Data access (SDD022)."""

    def __init__(self, api_base: str = "https://g.api.soracom.io"):
        self.api_base = api_base.rstrip("/")
        self.api_key: Optional[str] = None
        self.token: Optional[str] = None
        self.session = requests.Session()

    def is_authenticated(self) -> bool:
        return bool(self.api_key and self.token)

    def authenticate(self, email: str, password: str) -> Tuple[bool, str]:
        """Authenticate with Soracom and store API key/token (SDD022)."""
        url = f"{self.api_base}/v1/auth"
        try:
            resp = self.session.post(url, json={"email": email, "password": password}, timeout=10)
            if resp.status_code != 200:
                return False, f"Authentication failed: {resp.text}".strip()
            data = resp.json()
            self.api_key = data.get("apiKey")
            self.token = data.get("token")
            if not self.api_key or not self.token:
                return False, "Authentication response missing apiKey/token"
            return True, "Authenticated"
        except requests.RequestException as exc:
            return False, f"Network error: {exc}"

    def _headers(self) -> dict:
        return {
            "X-Soracom-API-Key": self.api_key or "",
            "X-Soracom-Token": self.token or "",
            "Content-Type": "application/json",
        }

    def send_downlink_udp(self, simid: str, message: str, port: int) -> Tuple[bool, str]:
        """Send UDP downlink payload to the SIM via Soracom (REQ009/SDD025)."""
        if not self.is_authenticated():
            return False, "Not authenticated"
        payload_b64 = base64.b64encode(message.encode()).decode()
        url = f"{self.api_base}/v1/sims/{simid}/downlink/udp"
        body = {
            "payload": payload_b64,
            "payloadEncoding": "base64",
            "port": port,
        }
        try:
            resp = self.session.post(url, headers=self._headers(), json=body, timeout=10)
            # Soracom returns 204 (per SDD025) on success; also allow 200/201 for robustness.
            if resp.status_code not in (200, 201, 204):
                error_msg = "Downlink failed"
                try:
                    error_json = resp.json()
                    code = error_json.get("code", "UNKNOWN")
                    description = error_json.get("message", error_json.get("description", "No description"))
                    error_msg = f"Code: {code}, Description: {description}"
                except (ValueError, KeyError):
                    error_msg = f"Code: HTTP {resp.status_code}, Description: {resp.text}"
                return False, error_msg
            return True, f"Downlink accepted (status {resp.status_code})"
        except requests.RequestException as exc:
            return False, f"Network error: {exc}"

    def fetch_harvest_messages(self, sim_id: str, since_ms: Optional[int]) -> Tuple[bool, List[HarvestMessage] | str]:
        """Fetch Harvest Data messages for the SIM (by simId) since the given timestamp (REQ010)."""
        if not self.is_authenticated():
            return False, "Not authenticated"

        if not sim_id:
            return False, "Missing simId for Harvest fetch"

        params = {"resourceType": "harvest"}
        if since_ms is not None:
            # Use +1 to avoid re-fetching the same timestamped message repeatedly
            params["from"] = int(since_ms) + 1
        url = f"{self.api_base}/v1/sims/{sim_id}/data"
        try:
            resp = self.session.get(url, headers=self._headers(), params=params, timeout=10)
            if resp.status_code != 200:
                return False, f"Harvest fetch failed: {resp.text}".strip()
            data = resp.json()
            messages: List[HarvestMessage] = []
            for entry in data if isinstance(data, list) else []:
                ts = self._extract_timestamp(entry)
                text = self._extract_message_text(entry)
                if ts is None or text is None:
                    continue
                messages.append(HarvestMessage(timestamp_ms=ts, text=text))
            messages.sort(key=lambda m: m.timestamp_ms)
            return True, messages
        except requests.RequestException as exc:
            return False, f"Network error: {exc}"
        except ValueError:
            return False, "Invalid JSON response from Harvest Data"

    def list_sims(self) -> Tuple[bool, List[dict] | str]:
        """List SIMs for the authenticated account (SDD023).

        Returns simId, IMSI, and session status as a normalized string: "online" or "offline".
        """
        if not self.is_authenticated():
            return False, "Not authenticated"
        url = f"{self.api_base}/v1/sims"
        try:
            resp = self.session.get(url, headers=self._headers(), timeout=10)
            if resp.status_code != 200:
                return False, f"SIM list failed: {resp.text}".strip()
            data = resp.json()
            sims: List[dict] = []
            for entry in data if isinstance(data, list) else []:
                sess = entry.get("sessionStatus")
                online = False
                imsi = entry.get("imsi")
                if isinstance(sess, dict):
                    # Expect shape: { ..., "imsi": "...", "online": true/false, ... }
                    imsi = sess.get("imsi") or imsi
                    online = bool(sess.get("online", False))
                elif isinstance(sess, bool):
                    online = sess
                elif isinstance(sess, str):
                    online = sess.strip().lower() == "online"

                sims.append({
                    "simId": entry.get("simId") or entry.get("id"),
                    "imsi": imsi or "",
                    # Store normalized text so the UI shows only online/offline
                    "sessionStatus": "online" if online else "offline",
                })
            return True, sims
        except requests.RequestException as exc:
            return False, f"Network error: {exc}"
        except ValueError:
            return False, "Invalid JSON response from SIM list"

    @staticmethod
    def _extract_timestamp(entry: dict) -> Optional[int]:
        candidates = [
            entry.get("time"),
            entry.get("timestamp"),
            entry.get("captureTime"),
        ]
        for candidate in candidates:
            if candidate is None:
                continue
            try:
                return int(candidate)
            except (TypeError, ValueError):
                continue
        return None

    @staticmethod
    def _extract_message_text(entry: dict) -> Optional[str]:
        candidates = [
            entry.get("content"),
            entry.get("payload"),
            entry.get("message"),
            entry.get("data"),
        ]
        for candidate in candidates:
            if candidate is None:
                continue
            if isinstance(candidate, dict):
                # Common pattern: {"payload":"..."}
                nested = candidate.get("payload") or candidate.get("data")
                if nested:
                    candidate = nested
            if isinstance(candidate, (bytes, bytearray)):
                try:
                    return candidate.decode()
                except Exception:
                    continue
            if isinstance(candidate, str):
                # If candidate looks like JSON, try to parse and extract 'payload' then base64-decode it
                try:
                    if candidate.strip().startswith("{"):
                        obj = json.loads(candidate)
                        inner = obj.get("payload") or obj.get("data")
                        if isinstance(inner, str):
                            decoded_json = base64.b64decode(inner, validate=True).decode()
                            if decoded_json:
                                return decoded_json
                except Exception:
                    pass
                # Try HEX decode (for Murata device messages stored in Harvest)
                try:
                    if all(c in '0123456789ABCDEFabcdef' for c in candidate.strip()):
                        decoded_hex = bytes.fromhex(candidate.strip()).decode('ascii')
                        if decoded_hex:
                            return decoded_hex
                except Exception:
                    pass
                # Try base64 decode first; fall back to raw string on failure
                try:
                    decoded = base64.b64decode(candidate, validate=True).decode()
                    # If decoding yielded unreadable output, keep original
                    if decoded:
                        return decoded
                except Exception:
                    pass
                return candidate
        return None


class CommunicatorApplication:
    """Tkinter GUI for Communicator Application (REQ008-REQ011)."""

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Communicator Application")
        self.root.geometry("900x700")

        self.api_client = SoracomApiClient()
        self.connected = False
        self.connection_state = "disconnected"  # disconnected | connecting | connected
        self.poll_interval_ms = 5000
        self.polling = False
        self.last_harvest_ts: Optional[int] = None
        self._seen_harvest: set[tuple[int, str]] = set()
        self.sims: List[dict] = []
        self.sim_active = False
        self.selected_sim_status = tk.StringVar(value="Status: --")
        self.selected_sim_id = ""  # Store simId for sendDownlinkUdp

        # Location tracking for remote clients (REQ012, SDD002)
        self.remote_clients = {}  # {client_id: {"lat": lat_str, "lon": lon_str}}
        self.map_canvas = None
        self.world_gdf = None  # GeoPandas world boundaries
        self.map_photo = None  # PhotoImage for map

        self.email_var = tk.StringVar()
        self.password_var = tk.StringVar()
        # Per SDD021: only request ID/password via GUI; IMSI comes from env/config
        self.imsi_var = tk.StringVar(value=os.getenv("SORACOM_IMSI", ""))
        # UDP port 55555 per SDD026
        self.udp_port = 55555

        self._build_gui()
        self._schedule_poll()

    # GUI construction -------------------------------------------------
    def _build_gui(self):
        main = ttk.Frame(self.root, padding="10")
        main.grid(row=0, column=0, sticky="nsew")
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main.columnconfigure(0, weight=1)
        main.rowconfigure(0, weight=0)
        main.rowconfigure(1, weight=0)
        main.rowconfigure(2, weight=2)
        main.rowconfigure(3, weight=1)

        self._build_connection_panel(main)
        self._build_map_panel(main)
        self._build_chat_panel(main)
        self._build_log_panel(main)

    def _build_connection_panel(self, parent: ttk.Frame):
        frame = ttk.LabelFrame(parent, text="Connection Status", padding="10")
        frame.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        frame.columnconfigure(1, weight=1)
        frame.rowconfigure(5, weight=1)

        status_row = ttk.Frame(frame)
        status_row.grid(row=0, column=0, columnspan=4, sticky="ew", pady=5)
        self.status_canvas = tk.Canvas(status_row, width=30, height=30, bg="white")
        self.status_canvas.pack(side=tk.LEFT, padx=5)
        self.status_label = ttk.Label(status_row, text="Status: Disconnected", font=("Arial", 11, "bold"))
        self.status_label.pack(side=tk.LEFT, padx=10)
        self._update_status_indicator()

        ttk.Label(frame, text="Email (Soracom ID):").grid(row=1, column=0, sticky="w", padx=5, pady=2)
        email_entry = ttk.Entry(frame, textvariable=self.email_var)
        email_entry.grid(row=1, column=1, columnspan=3, sticky="ew", padx=5, pady=2)

        ttk.Label(frame, text="Password:").grid(row=2, column=0, sticky="w", padx=5, pady=2)
        password_entry = ttk.Entry(frame, textvariable=self.password_var, show="*")
        password_entry.grid(row=2, column=1, columnspan=3, sticky="ew", padx=5, pady=2)

        button_row = ttk.Frame(frame)
        button_row.grid(row=3, column=0, columnspan=4, sticky="w", pady=8)
        self.connect_btn = ttk.Button(button_row, text="Connect", command=self.connect)
        self.connect_btn.pack(side=tk.LEFT, padx=5)
        self.disconnect_btn = ttk.Button(button_row, text="Disconnect", command=self.disconnect, state="disabled")
        self.disconnect_btn.pack(side=tk.LEFT, padx=5)

        # SIM list (SDD023)
        sims_frame = ttk.LabelFrame(frame, text="SIMs", padding="5")
        sims_frame.grid(row=4, column=0, columnspan=4, sticky="nsew", pady=5)
        sims_frame.columnconfigure(0, weight=1)
        sims_frame.rowconfigure(0, weight=1)

        self.sims_tree = ttk.Treeview(sims_frame, columns=("simId", "imsi", "sessionStatus"), show="headings", height=4)
        self.sims_tree.heading("simId", text="SIM ID")
        self.sims_tree.heading("imsi", text="IMSI")
        self.sims_tree.heading("sessionStatus", text="Session")
        self.sims_tree.column("simId", width=180, anchor="w")
        self.sims_tree.column("imsi", width=160, anchor="w")
        self.sims_tree.column("sessionStatus", width=100, anchor="center")
        self.sims_tree.grid(row=0, column=0, sticky="nsew")
        sims_scroll = ttk.Scrollbar(sims_frame, orient="vertical", command=self.sims_tree.yview)
        self.sims_tree.configure(yscrollcommand=sims_scroll.set)
        sims_scroll.grid(row=0, column=1, sticky="ns")
        self.sims_tree.bind("<<TreeviewSelect>>", self._on_sim_select)

        # SIM active status display (SDD024)
        status_row = ttk.Frame(frame)
        status_row.grid(row=5, column=0, columnspan=4, sticky="w", pady=4)
        ttk.Label(status_row, text="Selected SIM:").pack(side=tk.LEFT, padx=(0, 6))
        self.sim_status_label = ttk.Label(status_row, textvariable=self.selected_sim_status, font=("Arial", 10, "bold"))
        self.sim_status_label.pack(side=tk.LEFT)

    def _build_map_panel(self, parent: ttk.Frame):
        """Map panel showing remote client locations (REQ012, SDD002)."""
        frame = ttk.LabelFrame(parent, text="Remote Client Locations", padding="10")
        frame.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)

        self.map_canvas = tk.Canvas(frame, width=600, height=150, bg="#f2f6fb", highlightthickness=1, highlightbackground="#c0c0c0")
        self.map_canvas.grid(row=0, column=0, sticky="nsew")
        self._draw_map_background()
        self._update_map_display()

    def _draw_map_background(self):
        """Draw world map background using GeoPandas (SDD002)."""
        if not self.map_canvas:
            return
        self.map_canvas.delete("bg")
        w = int(self.map_canvas['width'])
        h = int(self.map_canvas['height'])
        
        try:
            # Load world boundaries from natural earth dataset
            if self.world_gdf is None:
                # Download Natural Earth data directly (GeoPandas 1.0+ removed built-in datasets)
                url = "https://naciscdn.org/naturalearth/110m/cultural/ne_110m_admin_0_countries.zip"
                self.world_gdf = gpd.read_file(url)
            
            # Create matplotlib figure
            dpi = 100
            fig, ax = plt.subplots(figsize=(w/dpi, h/dpi), dpi=dpi)
            
            # Plot world map
            self.world_gdf.plot(ax=ax, color='#f5f0e8', edgecolor='#8a9199', linewidth=0.5)
            ax.set_facecolor('#d4e5f7')
            ax.set_xlim(-180, 180)
            ax.set_ylim(-90, 90)
            ax.axis('off')
            plt.subplots_adjust(left=0, right=1, top=1, bottom=0)
            
            # Convert to image for tkinter
            buf = io.BytesIO()
            fig.savefig(buf, format='png', dpi=dpi, bbox_inches='tight', pad_inches=0)
            plt.close(fig)
            buf.seek(0)
            
            img = Image.open(buf)
            img = img.resize((w, h), Image.Resampling.LANCZOS)
            self.map_photo = ImageTk.PhotoImage(img)
            self.map_canvas.create_image(0, 0, anchor="nw", image=self.map_photo, tags="bg")
            
        except Exception as e:
            # Fallback to simple rectangle if geopandas fails
            print(f"[ERROR] GeoPandas map rendering failed: {e}")
            import traceback
            traceback.print_exc()
            self.map_canvas.create_rectangle(0, 0, w, h, fill="#d4e5f7", outline="#c0c0c0", tags="bg")
            self._draw_continents(w, h)

    def _update_map_display(self):
        """Render all remote client location markers on the map."""
        if not self.map_canvas:
            return
        self._draw_map_background()
        self.map_canvas.delete("marker")

        w = int(self.map_canvas['width'])
        h = int(self.map_canvas['height'])

        for client_id, location in self.remote_clients.items():
            try:
                lat_f = float(location.get("lat"))
                lon_f = float(location.get("lon"))
            except (ValueError, TypeError):
                continue

            x = (lon_f + 180) / 360 * w
            y = (90 - lat_f) / 180 * h
            x = max(5, min(w - 5, x))
            y = max(5, min(h - 5, y))

            r = 6
            self.map_canvas.create_oval(x - r, y - r, x + r, y + r, fill="#e63946", outline="#ffffff", width=2, tags="marker")
            self.map_canvas.create_text(x, y - 12, text=f"{lat_f:.6f}, {lon_f:.6f}", fill="#0b1f33", font=("Arial", 8, "bold"), tags="marker")

    def _draw_continents(self, w: int, h: int):
        """Draw simplified continent outlines for world map (SDD002)."""
        def lat_lon_to_xy(lat, lon):
            x = (lon + 180) / 360 * w
            y = (90 - lat) / 180 * h
            return x, y
        
        # Simplified continent polygons (lat, lon) for equirectangular projection
        continents = [
            # North America
            [(-10, -170), (15, -170), (25, -155), (50, -130), (60, -100), (70, -90), (75, -80), (70, -65), (55, -60), (48, -52), (25, -80), (10, -90), (10, -105), (-10, -110)],
            # South America
            [(12, -80), (10, -75), (-5, -80), (-20, -70), (-40, -73), (-55, -70), (-55, -65), (-35, -57), (-22, -43), (-5, -35), (5, -50), (10, -60)],
            # Europe
            [(35, -10), (40, 0), (60, 10), (70, 25), (65, 30), (55, 30), (50, 15), (45, 10), (40, 5)],
            # Africa
            [(37, -5), (35, 10), (32, 20), (20, 35), (15, 40), (10, 45), (-10, 42), (-20, 35), (-30, 25), (-35, 20), (-35, 30), (-15, 40), (10, 50), (20, 45), (30, 30), (37, 10)],
            # Asia
            [(35, 35), (40, 45), (50, 50), (60, 60), (70, 80), (75, 100), (70, 120), (60, 140), (50, 145), (40, 140), (30, 120), (25, 100), (20, 80), (25, 70), (30, 60), (35, 50)],
            # Australia
            [(-10, 110), (-15, 130), (-35, 140), (-40, 145), (-40, 138), (-30, 115), (-20, 113)],
        ]
        
        for continent in continents:
            points = []
            for lat, lon in continent:
                x, y = lat_lon_to_xy(lat, lon)
                points.extend([x, y])
            if len(points) >= 6:
                self.map_canvas.create_polygon(points, fill="#f5f0e8", outline="#8a9199", width=1, tags="bg")

    def _update_client_location(self, client_id: str, lat: str, lon: str):
        """Track and display a remote client location (REQ012, SDD002)."""
        if client_id not in self.remote_clients:
            self.remote_clients[client_id] = {}
        self.remote_clients[client_id]["lat"] = lat
        self.remote_clients[client_id]["lon"] = lon
        self._update_map_display()

    def _build_chat_panel(self, parent: ttk.Frame):
        frame = ttk.LabelFrame(parent, text="Chat Area", padding="10")
        frame.grid(row=2, column=0, sticky="nsew", padx=5, pady=5)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)

        self.chat_display = scrolledtext.ScrolledText(frame, height=15, width=80, state="disabled")
        self.chat_display.grid(row=0, column=0, sticky="nsew", pady=5)
        self.chat_display.tag_configure("sent", foreground="blue")
        self.chat_display.tag_configure("recv", foreground="green")
        self.chat_display.tag_configure("sys", foreground="red")

        ttk.Label(frame, text="Message:", font=("Arial", 9)).grid(row=1, column=0, sticky="w", pady=(8, 4))
        input_frame = ttk.Frame(frame)
        input_frame.grid(row=2, column=0, sticky="ew", pady=4)
        input_frame.columnconfigure(0, weight=1)

        self.message_input = tk.Text(input_frame, height=3, width=80)
        self.message_input.grid(row=0, column=0, sticky="ew", padx=(0, 5))
        self.send_btn = ttk.Button(input_frame, text="Send", command=self.send_message, state="disabled")
        self.send_btn.grid(row=0, column=1, sticky="n")

    def _build_log_panel(self, parent: ttk.Frame):
        frame = ttk.LabelFrame(parent, text="Message Log", padding="10")
        frame.grid(row=3, column=0, sticky="nsew", padx=5, pady=5)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(1, weight=1)

        control = ttk.Frame(frame)
        control.grid(row=0, column=0, sticky="ew", pady=4)
        ttk.Button(control, text="Clear Log", command=self.clear_log).pack(side=tk.LEFT, padx=5)

        self.log_text = scrolledtext.ScrolledText(frame, height=10, width=80, state="disabled")
        self.log_text.grid(row=1, column=0, sticky="nsew")
        self.log_text.tag_configure("sent", foreground="blue")
        self.log_text.tag_configure("recv", foreground="green")
        self.log_text.tag_configure("sys", foreground="red")

    # State helpers ----------------------------------------------------
    def _set_status(self, state: str, message: str):
        self.connection_state = state
        self._refresh_status_text(message)
        self._update_status_indicator()

    def _refresh_status_text(self, base_message: str = ""):
        if not base_message:
            if self.connection_state == "connecting":
                base_message = "Status: Connecting..."
            elif self.connection_state == "connected":
                base_message = "Status: Connected"
            else:
                base_message = "Status: Disconnected"

        # Append session state when connected (online/offline per SDD023)
        if self.connection_state == "connected":
            suffix = " (Session online)" if self.sim_active else " (Session offline)"
            base_message += suffix

        self.status_label.config(text=base_message)

    def _update_status_indicator(self):
        color = "red"
        if self.connection_state == "connecting":
            color = "yellow"
        elif self.connection_state == "connected":
            color = "green" if self.sim_active else "yellow"
        self.status_canvas.delete("all")
        self.status_canvas.create_oval(5, 5, 25, 25, fill=color, outline="black")

    # Connection flow --------------------------------------------------
    def connect(self):
        email = self.email_var.get().strip()
        password = self.password_var.get().strip()
        imsi = self.imsi_var.get().strip()
        if not email or not password:
            messagebox.showerror("Missing Fields", "Email and password are required")
            return

        self._set_status("connecting", "Status: Connecting...")
        self.connect_btn.config(state="disabled")

        def worker():
            success, msg = self.api_client.authenticate(email, password)
            def finish():
                if success:
                    self.connected = True
                    self.last_harvest_ts = int(time.time() * 1000)
                    self._set_status("connected", "Status: Connected")
                    self.disconnect_btn.config(state="normal")
                    # Enable send only after selecting a SIM with online session
                    self.send_btn.config(state="disabled")
                    self.log_message("sys", f"Authenticated with Soracom. Downlink port {self.udp_port} (SDD026)")
                    self._fetch_and_show_sims()
                else:
                    self.connected = False
                    self._set_status("disconnected", "Status: Disconnected")
                    self.connect_btn.config(state="normal")
                    messagebox.showerror("Authentication Failed", msg)
            self.root.after(0, finish)

        threading.Thread(target=worker, daemon=True).start()

    def disconnect(self):
        self.connected = False
        self.api_client.api_key = None
        self.api_client.token = None
        self.sim_active = False
        self._set_status("disconnected", "Status: Disconnected")
        self.connect_btn.config(state="normal")
        self.disconnect_btn.config(state="disabled")
        self.send_btn.config(state="disabled")
        self.log_message("sys", "Disconnected from Soracom API")
        self._clear_sim_list()

    # Messaging --------------------------------------------------------
    def send_message(self):
        if not self.connected:
            messagebox.showwarning("Not Connected", "Connect to Soracom first")
            return
        if not self.sim_active:
            messagebox.showwarning("Session Offline", "Selected SIM session is offline. Select an online SIM or wait until it is online.")
            return
        message = self.message_input.get("1.0", "end").strip()
        if not message:
            messagebox.showwarning("Empty Message", "Enter a message to send")
            return
        if not self.selected_sim_id:
            messagebox.showerror("Missing SIM", "Select a SIM first.")
            return

        self.message_input.delete("1.0", "end")
        # Per SDD025 step 5: Only display final status in chat (success/failure), not intermediate states
        self.log_message("sent", f"Sending to {str(self.selected_sim_id)}:{self.udp_port} (SDD025/SDD026)")

        def worker():
            success, info = self.api_client.send_downlink_udp(str(self.selected_sim_id), message, self.udp_port)
            def finish():
                if success:
                    self.log_message("sent", f"Downlink accepted: {info}")
                    self._append_chat("sent", f"[SEND][SUCCESS] {message}")
                else:
                    self.log_message("sys", f"Downlink error: {info}")
                    self._append_chat("sys", f"[SEND][FAILURE] {message} | {info}")
            self.root.after(0, finish)

        threading.Thread(target=worker, daemon=True).start()

    # Receiving --------------------------------------------------------
    def _schedule_poll(self):
        """Schedule next poll cycle (SDD029 - 5 second interval)."""
        self.root.after(self.poll_interval_ms, self._poll_harvest)

    def _poll_harvest(self):
        """Poll SORACOM Harvest Data API for messages (SDD029/REQ010).
        
        Per SDD029 precondition: Only poll when SIM is connected (online).
        """
        # Skip polling if not connected or SIM not online (SDD029 precondition)
        if not self.connected or not self.sim_active or self.polling:
            self._schedule_poll()
            return
        self.polling = True
        sim_id = str(self.selected_sim_id).strip()
        if not sim_id:
            self.polling = False
            self._schedule_poll()
            return

        def worker():
            try:
                success, result = self.api_client.fetch_harvest_messages(sim_id, self.last_harvest_ts)
                def finish():
                    if success and isinstance(result, list):
                        # Only log when messages are received
                        if result:
                            self.log_message("sys", f"[HARVEST] Fetched {len(result)} message(s)")
                            for msg in result:
                                self.log_message("sys", f"[HARVEST] Processing: timestamp={msg.timestamp_ms}, text='{msg.text}'")
                                key = (msg.timestamp_ms, msg.text)
                                if key in self._seen_harvest:
                                    self.log_message("sys", f"[HARVEST] Skipping duplicate message")
                                    continue
                                self._seen_harvest.add(key)
                                if self.last_harvest_ts is None or msg.timestamp_ms > self.last_harvest_ts:
                                    self.last_harvest_ts = msg.timestamp_ms
                                    self.log_message("sys", f"[HARVEST] Advancing cursor to {self.last_harvest_ts}")
                                # Display received message in chat using Harvest timestamp (SDD029)
                                self._append_chat("recv", f"[RECV] {msg.text}", ts=msg.timestamp)
                                self.log_message("recv", f"Harvest at {msg.timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
                                # Try to parse location from message (REQ012)
                                self._maybe_extract_location(msg.text)
                        else:
                            # Single line for empty polls
                            self.log_message("sys", "[HARVEST] Fetched 0 message(s)")
                    elif not success:
                        self.log_message("sys", f"[HARVEST] Poll failed for simId={sim_id}: {result}")
                    self.polling = False
                    self._schedule_poll()
                self.root.after(0, finish)
            except Exception as exc:
                self.log_message("sys", f"[HARVEST] Worker exception: {exc}")
                self.polling = False
                self.root.after(0, self._schedule_poll)

        threading.Thread(target=worker, daemon=True).start()

    # UI helpers -------------------------------------------------------
    def _maybe_extract_location(self, message_text: str):
        """Extract LOCATION payload from message and update map (REQ012, SDD002, SDD047)."""
        try:
            import re
            # Match ["LOCATION", "lat", "lon"] format
            match = re.search(r'\["LOCATION",\s*"(-?\d+\.?\d*)",\s*"(-?\d+\.?\d*)"\]', message_text)
            if match:
                lat, lon = match.group(1), match.group(2)
                # Use timestamp as client ID; in real scenario could use IMSI or device ID
                client_id = f"client_{int(time.time())}"
                self._update_client_location(client_id, lat, lon)
                self.log_message("sys", f"[LOCATION] Updated {client_id}: lat={lat}, lon={lon}")
        except Exception:
            pass

    def _append_chat(self, tag: str, message: str, ts: Optional[datetime] = None):
        ts_str = (ts or datetime.now()).strftime("%Y-%m-%d %H:%M:%S")
        entry = f"[{ts_str}] {message}\n"
        self.chat_display.config(state="normal")
        self.chat_display.insert("end", entry, tag)
        self.chat_display.config(state="disabled")
        self.chat_display.see("end")

    def log_message(self, tag: str, message: str):
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        entry = f"[{ts}] {message}"
        self.log_text.config(state="normal")
        self.log_text.insert("end", entry + "\n", tag)
        self.log_text.config(state="disabled")
        self.log_text.see("end")

    def clear_log(self):
        self.log_text.config(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.config(state="disabled")
        self.log_message("sys", "Log cleared")

    # SIM listing (SDD023) -------------------------------------------
    def _fetch_and_show_sims(self):
        def worker():
            success, result = self.api_client.list_sims()
            def finish():
                if success and isinstance(result, list):
                    self.sims = result
                    self._populate_sim_tree()
                    self.log_message("sys", f"Loaded {len(result)} SIMs")
                elif not success:
                    self.log_message("sys", str(result))
            self.root.after(0, finish)

        threading.Thread(target=worker, daemon=True).start()

    def _populate_sim_tree(self):
        self.sims_tree.delete(*self.sims_tree.get_children())
        first_iid = None
        for sim in self.sims:
            # Ensure we only display normalized online/offline text
            session_status = sim.get("sessionStatus", "").strip().lower()
            session_text = "online" if session_status == "online" else "offline"
            iid = self.sims_tree.insert("", "end", values=(
                sim.get("simId", ""),
                sim.get("imsi", ""),
                session_text
            ))
            if first_iid is None:
                first_iid = iid
        if first_iid:
            self.sims_tree.selection_set(first_iid)
            self._on_sim_select()

    def _clear_sim_list(self):
        self.sims = []
        self.sims_tree.delete(*self.sims_tree.get_children())
        self.selected_sim_status.set("Status: --")
        self.sim_active = False

    def _on_sim_select(self, event=None):
        selection = self.sims_tree.selection()
        if not selection:
            return
        item = self.sims_tree.item(selection[0])
        values = item.get("values", [])
        sim_id, imsi, session_status = (values + ["", "", ""] )[:3]
        # Store simId for use in sendDownlinkUdp; coerce to string to avoid int/strip issues
        self.selected_sim_id = str(sim_id)
        if imsi:
            self.imsi_var.set(imsi)
        
        # Parse session status (online/offline)
        session_text = str(session_status).lower()
        is_session_online = session_text in {"online"}
        
        # Display session status (SDD023)
        session_label = "Online" if is_session_online else "Offline"
        self.selected_sim_status.set(f"Session: {session_label}")
        
        # Use session status for connection indicator
        self.sim_active = is_session_online
        # Enable send button only when connected and session is online
        self.send_btn.config(state=("normal" if (self.connected and self.sim_active) else "disabled"))
        self._refresh_status_text()
        self._update_status_indicator()


def main():
    root = tk.Tk()
    app = CommunicatorApplication(root)
    root.mainloop()


if __name__ == "__main__":
    main()
