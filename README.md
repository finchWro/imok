# IMOK - IoT Communication System

**IMOK** (I'm OK) is a bi-directional communication system that enables message exchange via IoT devices in remote or challenging environments. The system allows users to send "I'm OK" status updates and communicate with remote locations through cellular IoT networks.

**NTN Support:** The IMOK system supports IoT NTN (Non-Terrestrial Network) technology via the Murata Type 1SC-NTN device, enabling satellite-based communication in remote locations beyond traditional cellular infrastructure. This provides connectivity anywhere on Earth, including areas with no terrestrial network coverage.

## Current Implementation

The IMOK system consists of two Python/Tkinter applications that communicate via Soracom's cellular network and Harvest Data API:

- **Remote Client Application** - Interfaces with IoT devices (Nordic Thingy:91 X for LTE-M, Murata Type 1SC-NTN for LTE-M/NB-IoT-NTN) via serial using Device Profile Pattern, sends messages to Soracom Harvest Data, and receives UDP downlink messages from the Communicator
- **Communicator Application** - Authenticates with Soracom API, manages SIM inventory, sends UDP downlink messages to Remote Client, and polls Harvest Data for received messages

### Supported IoT Devices

The Remote Client Application uses a **Device Profile Pattern** (SDD030) to support multiple IoT device types:

1. **Nordic Thingy:91 X** (Nordic Semiconductor)
   - Single-command operations: `AT#XSENDTO`, `AT#XRECVFROM`, `AT#XBIND`
   - ASCII data encoding
   - Standard AT commands for LTE-M (terrestrial cellular)
   - Default baud rate: 9600

2. **Murata Type 1SC-NTN** (Murata) - **NTN-Capable**
   - Multi-step socket operations: ALLOCATE → ACTIVATE → SEND
   - HEX data encoding (ASCII to HEX conversion)
   - Murata-specific AT commands: `AT%SOCKETCMD`, `AT%SOCKETDATA`
   - **Supports NB-IoT-NTN (satellite)** and LTE-M (terrestrial)
   - GNSS integration for satellite network acquisition
   - Europe S-band (256) for NTN connectivity
   - Default baud rate: 115200
   - **Use Case**: Remote locations beyond cellular coverage (mountains, oceans, deserts)

The Device Profile Pattern allows easy addition of new IoT device types by implementing a common interface without modifying core application logic.

## Architecture

```
┌─────────────────────────┐         ┌──────────────────────────┐
│  Remote Client App      │         │  Communicator App        │
│  (Python/Tkinter)       │         │  (Python/Tkinter)        │
│                         │         │                          │
│  - Serial (AT commands) │         │  - Soracom REST API      │
│  - LTE-M/NB-IoT-NTN     │         │  - SIM Management        │
│  - Harvest Data Send    │         │  - Harvest Data Poll     │
│  - UDP Receive (55555)  │         │  - UDP Downlink Send     │
└──────────┬──────────────┘         └──────────┬───────────────┘
           │                                   │
           │                                   │
       Serial Port                        HTTPS API
        (2-way)                             (2-way)
           │                                   │
           ▼                                   ▼
┌─────────────────────────┐         ┌──────────────────────────┐
│  Nordic Thingy:91 X     │◄───────►│  Soracom Platform        │
│  or Murata Type1SC-NTN │ LTE-M/  │  - Harvest Data API      │
│  IoT Device             │  NTN    │  - Downlink UDP (55555)  │
│                         │ (2-way) │  - SIM Management        │
│  - LTE-M/NB-IoT-NTN     │         │                          │
│  - AT Commands          │  Uplink: Harvest Data              │
│  - UDP Socket           │  Downlink: UDP (port 55555)        │
│  - GNSS (NTN devices)   │                                    │
└─────────────────────────┘         └──────────────────────────┘
            ▲
            │ (NTN only)
            │
     ┌──────┴──────┐
     │  Satellite  │
     │  Network    │
     └─────────────┘
```

## Requirements

### System Requirements
- **Python**: 3.13+
- **Hardware**: 
  - Nordic Thingy:91 X (LTE-M) or Murata Type 1SC-NTN (LTE-M/NB-IoT-NTN) IoT device
  - Serial port/USB connection
- **Network**:
  - Soracom SIM with active subscription
  - LTE-M network coverage (Nordic) or NTN satellite coverage (Murata)
  - Soracom account with API credentials

### Python Dependencies
```
pyserial>=3.5
requests>=2.31
```

## Installation

1. **Clone the repository**
```powershell
git clone <repository-url>
cd imok
```

2. **Set up Python virtual environment**
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

3. **Install dependencies**
```powershell
pip install -r requirements.txt
```

## Configuration

### Remote Client Application
- Connect supported IoT device (Nordic Thingy:91 X or Murata Type 1SC-NTN) via USB/Serial
- Select device type from dropdown (Device Configuration section)
- Select COM port and baud rate in GUI
- Application automatically uses appropriate AT commands for selected device
- No additional configuration required

### Communicator Application
- **Required**: Soracom account email and password (entered via GUI)
- **Optional**: Set environment variable for IMSI pre-population
```powershell
$env:SORACOM_IMSI = "your-sim-imsi"
```

## Usage

### Running the Remote Client Application

```powershell
python remote_client.py
```

**Features:**
- **Device Selection**: Choose between Nordic Thingy:91 X and Murata Type 1SC-NTN
- **Connection Status**: Green (connected + network registered), Yellow (connecting/offline), Red (disconnected)
- **Serial Configuration**: Select COM port and baud rate
- **Signal Quality**: Real-time RSRP display (dBm)
- **Send Messages**: Input text and click Send to transmit to Soracom Harvest Data
- **Receive Messages**: Automatically receives UDP downlink from Communicator (port 55555)
- **Message Log**: Filterable log (All/Sent/Received/System) with timestamps and detailed AT command traces
- **Chat Area**: Displays sent (`[SEND]`) and received (`[RECV]`) messages with timestamps
- **SDD016 Compliance**: Sequential initialization - waits for network registration before proceeding with UDP socket operations

**Workflow:**
1. Select device type (Nordic Thingy:91 X for LTE-M or Murata Type 1SC-NTN for NTN)
2. Select COM port and appropriate baud rate (9600 for Nordic, 115200 for Murata)
3. Click **Connect** - initiates cellular network registration
   - **Murata NTN**: Waits for GNSS fix before network registration (crucial for satellite connectivity)
   - **Nordic LTE-M**: Proceeds directly to network registration
4. Application waits for network registration (`+CEREG 1/5` or `CEREG: 5`) per SDD016 requirements
   - **Timeout**: 60s for terrestrial LTE-M, 120s for NTN satellite
5. Only after successful registration: PDP context activation, UDP socket opening, and port binding
6. Send messages to Harvest Data or receive downlink from Communicator

### Running the Communicator Application

```powershell
python communicator_app.py
```

**Features:**
- **Connection Status**: Authenticate with Soracom API using email/password
- **SIM Inventory**: Lists all SIMs with online/offline session status
- **Session Indicator**: Green (online), Yellow (offline), Red (disconnected)
- **Send Messages**: Select online SIM, input text, click Send for UDP downlink (port 55555)
- **Receive Messages**: Polls Harvest Data API every 5 seconds for new messages
- **Message Log**: Filterable log with timestamps and error details (Code/Description)
- **Chat Area**: Displays sent (`[SEND][SUCCESS]`/`[SEND][FAILURE]`) and received (`[RECV]`) messages

**Workflow:**
1. Enter Soracom email and password
2. Click **Connect** - authenticates and loads SIM inventory
3. Select a SIM from the list (session status shows online/offline)
4. Send messages via UDP downlink (requires SIM online)
5. Received messages from Harvest Data appear automatically in chat

## Technical Specifications

### Communication Flow

**Remote Client → Communicator (via Harvest Data):**
1. Remote Client sends message via AT command `AT#XSENDTO="harvest.soracom.io",8514,"<message>"`
2. Message stored in Soracom Harvest Data
3. Communicator polls Harvest Data API every 5 seconds (`GET /v1/subscribers/{imsi}/data`)
4. New messages appear in Communicator chat with server timestamp

**Communicator → Remote Client (via UDP Downlink):**
1. Communicator sends message via Soracom API `POST /v1/sims/{simid}/downlink/udp`
2. Payload base64-encoded, port 55555, response code 204 on success
3. Soracom delivers UDP packet to Remote Client's modem
4. Modem sends `+CSCON: 1` URC when data arrives
5. Remote Client reads via `AT#XRECVFROM=256`, extracts payload
6. Message filtered by source IP (100.127.10.16) and displayed in chat

### AT Commands (Remote Client)

**Nordic Thingy:91 X (LTE-M):**
- `AT+CFUN=1` - Set modem to full functionality
- `AT+CEREG=5` - Enable network registration URCs
- `AT%XSYSTEMMODE=1,0,1,0` - Set LTE-M mode
- `AT+CGDCONT=1,"IP","soracom.io"` - Configure PDP context for Soracom APN
- `AT%CESQ=1` - Subscribe to signal quality (RSRP) notifications
- `AT#XSOCKET=1,2,0` - Open UDP socket
- `AT#XBIND=55555` - Bind UDP port 55555 for downlink receive
- `AT#XSENDTO="harvest.soracom.io",8514,"<data>"` - Send to Harvest Data
- `AT#XRECVFROM=1500` - Receive UDP data (1500 byte buffer)

**Murata Type 1SC-NTN (NB-IoT-NTN):**
- `AT+CPIN?` - Check SIM state
- `AT%SETACFG="radiom.config.multi_rat_enable","true"` - Enable multi-RAT
- `AT+CSIM=52,"80C2000015D613190103820282811B0100130799F08900010001"` - Switch to NTN SIM plan
- `AT%RATIMGSEL=2` - Select NTN RAT image
- `AT%RATACT="NBNTN","1"` - Activate NB-IoT-NTN RAT
- `AT%SETCFG="BAND","256"` - Lock to Europe S band
- `AT%IGNSSACT=1` - Enable iGNSS (wait for fix before network registration)
- `AT+CEREG=2` - Enable network registration URCs with location
- `AT+CGDCONT=1,"IP","soracom.io"` - Configure PDP context
- `AT%PINGCMD=0,"100.127.100.127",1,50,30` - Ping Soracom server (verify PDP context)
- `AT%SOCKETEV=0,1` - Enable socket events
- `AT%SOCKETCMD="ALLOCATE",1,"UDP","OPEN","harvest.soracom.io",8514` - Allocate socket to Harvest
- `AT%SOCKETCMD="ACTIVATE",1` - Activate socket
- `AT%SOCKETDATA="SEND",1,<size>,"<hex_data>"` - Send HEX-encoded data
- `AT%SOCKETCMD="ALLOCATE",1,"UDP","LISTEN","0.0.0.0",,55555` - Allocate LISTEN socket for downlink
- `AT%SOCKETDATA="RECEIVE",2,1500` - Receive UDP data on socket 2

### Design Documents

The system implements requirements defined in Doorstop documents:

**Requirements (REQ):**
- REQ002-REQ007: Remote Client Application specifications
- REQ008-REQ011: Communicator Application specifications

**Design Specifications (SDD):**
- SDD001-SDD019: Remote Client detailed design
- SDD020-SDD029: Communicator detailed design
- SDD030-SDD042: Device-specific implementations (Nordic LTE-M, Murata NTN)

Generate documentation:
```powershell
doorstop publish -H all all
```

View in browser: `all/index.html`

## Requirements Traceability

| Requirement | Description | Implementation |
|-------------|-------------|----------------|
| **REQ002** | Remote Client GUI | `remote_client.py` - Tkinter 3-row layout |
| **REQ003** | Connection to IoT Device | Serial port communication via pyserial |
| **REQ004** | Connection Status Display | Color-coded indicator (green/yellow/red) |
| **REQ005** | Send Messages | Send to Harvest Data via AT#XSENDTO |
| **REQ006** | Receive Messages | UDP downlink via AT#XRECVFROM |
| **REQ007** | Message Log | Filterable log with timestamps |
| **REQ008** | Communicator GUI | `communicator_app.py` - Tkinter 3-row layout |
| **REQ009** | Send Messages | UDP downlink via Soracom API |
| **REQ010** | Receive Messages | Poll Harvest Data API every 5s |
| **REQ011** | Message Log | Filterable log with timestamps |

## Troubleshooting

### Remote Client Issues

**Device not connecting:**
- Verify COM port is correct (check Device Manager)
- Ensure baud rate matches device setting (typically 9600 or 115200)
- Check USB cable and drivers

**Network registration fails:**
- Verify SIM is inserted and active
- **Nordic (LTE-M)**: Check LTE-M coverage in your area
- **Murata (NTN)**: 
  - Ensure GNSS fix is acquired (requires clear sky view for satellite signal)
  - Check satellite coverage for your location (Europe S-band)
  - Typical registration time: 60-120 seconds after GNSS fix
- Review message log for `+CEREG` status codes

**Cannot receive downlink messages:**
- Ensure UDP port 55555 is bound (check log for `[SUCCESS] UDP port 55555 bound`)
- **Nordic**: Verify `+CSCON: 1` URC is received when Communicator sends, check source IP filtering (100.127.10.16)
- **Murata**: Verify `%SOCKETEV:<session_id>,<socket_id>` notification is received, check Soracom IP range (100.127.x.x)
- Review socket allocation logs to confirm correct socket IDs are used

### Communicator Issues

**Authentication fails:**
- Verify Soracom email/password credentials
- Check internet connectivity
- Review message log for error Code/Description

**Cannot send to Remote Client:**
- Ensure selected SIM session is online (green indicator)
- Verify SIM ID is correct
- Check message log for downlink error details

**Not receiving Harvest messages:**
- Verify IMSI is set (via environment variable or GUI)
- Ensure Remote Client is sending to Harvest Data
- Check polling is active (only polls when SIM online)

## Development

### Project Structure
```
imok/
├── remote_client.py         # Remote Client Application
├── communicator_app.py      # Communicator Application
├── requirements.txt         # Python dependencies
├── README.md               # This file
├── .gitignore              # Git ignore patterns
├── reqs/                   # Doorstop requirements
│   ├── REQ001.yml - REQ011.yml
│   └── design/             # Design specifications
│       ├── SDD001.yml - SDD029.yml
│       └── SDD030.yml - SDD042.yml  # Device-specific (Nordic/Murata)
└── .venv/                  # Virtual environment (ignored)
```

### Testing

**Remote Client Manual Test:**
1. Connect to device, wait for network registration
2. Send test message to Harvest Data
3. Use Communicator to send downlink
4. Verify message appears in chat

**Communicator Manual Test:**
1. Authenticate with Soracom
2. Select online SIM from inventory
3. Send test downlink message
4. Poll Harvest Data to receive messages from Remote Client

## License

[Specify license here]

## Authors

[Specify authors here]

## Acknowledgments

- Nordic Semiconductor for Thingy:91 X hardware (LTE-M)
- Murata for Type 1SC-NTN hardware (NB-IoT-NTN satellite connectivity)
- Soracom for IoT connectivity platform (terrestrial and satellite)
- Doorstop for requirements management
