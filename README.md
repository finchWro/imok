# IMOK - IoT Communication System

**IMOK** (I'm OK) is a bi-directional communication system that enables message exchange via IoT devices in remote or challenging environments. The system allows users to send "I'm OK" status updates and communicate with remote locations through cellular IoT networks.

**Future Vision:** The IMOK system is designed to evolve with IoT NTN (Non-Terrestrial Network) technology, enabling communication in remote locations covered only by satellite networks. This will extend coverage to areas beyond traditional cellular infrastructure, ensuring connectivity anywhere on Earth.

## Current Implementation

The IMOK system consists of two Python/Tkinter applications that communicate via Soracom's cellular network and Harvest Data API:

- **Remote Client Application** - Interfaces with Nordic Thingy:91 X via serial, sends messages to Soracom Harvest Data, and receives UDP downlink messages from the Communicator
- **Communicator Application** - Authenticates with Soracom API, manages SIM inventory, sends UDP downlink messages to Remote Client, and polls Harvest Data for received messages

## Architecture

```
┌─────────────────────────┐         ┌──────────────────────────┐
│  Remote Client App      │         │  Communicator App        │
│  (Python/Tkinter)       │         │  (Python/Tkinter)        │
│                         │         │                          │
│  - Serial (AT commands) │         │  - Soracom REST API      │
│  - LTE-M Network        │         │  - SIM Management        │
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
│  IoT Device             │  LTE-M  │  - Harvest Data API      │
│                         │ (2-way) │  - Downlink UDP (55555)  │
│  - LTE-M Modem          │         │  - SIM Management        │
│  - AT Commands          │  Uplink: Harvest Data              │
│  - UDP Socket           │  Downlink: UDP (port 55555)        │
└─────────────────────────┘         └──────────────────────────┘
```

## Requirements

### System Requirements
- **Python**: 3.13+
- **Hardware**: 
  - Nordic Thingy:91 X IoT device (for Remote Client)
  - Serial port/USB connection
- **Network**:
  - Soracom SIM with active subscription
  - LTE-M network coverage
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
- Connect Nordic Thingy:91 X via USB/Serial
- Select COM port and baud rate (default: 9600) in GUI
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
- **Connection Status**: Green (connected + network registered), Yellow (connecting/offline), Red (disconnected)
- **Serial Configuration**: Select COM port and baud rate
- **Signal Quality**: Real-time RSRP display (dBm)
- **Send Messages**: Input text and click Send to transmit to Soracom Harvest Data
- **Receive Messages**: Automatically receives UDP downlink from Communicator (port 55555)
- **Message Log**: Filterable log (All/Sent/Received/System) with timestamps
- **Chat Area**: Displays sent (`[SEND]`) and received (`[RECV]`) messages with timestamps

**Workflow:**
1. Select COM port and baud rate
2. Click **Connect** - initiates cellular network registration
3. Wait for network registration (`+CEREG 1/5`) and PDP context activation
4. UDP socket opens automatically, port 55555 binds for downlink
5. Send messages to Harvest Data or receive downlink from Communicator

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

Key AT commands implemented per ITU-T V.250:
- `AT+CFUN=1` - Set modem to full functionality
- `AT+CEREG=5` - Enable network registration URCs
- `AT%XSYSTEMMODE=1,0,0,0` - Set LTE-M only mode
- `AT+CGDCONT=1,"IP","soracom.io"` - Configure PDP context for Soracom APN
- `AT%CESQ=1` - Subscribe to signal quality (RSRP) notifications
- `AT#XSOCKET=1,2,0` - Open UDP socket
- `AT#XBIND=55555` - Bind UDP port 55555 for downlink receive
- `AT#XSENDTO="harvest.soracom.io",8514,"<data>"` - Send to Harvest Data
- `AT#XRECVFROM=256` - Receive UDP data (256 byte buffer)

### Design Documents

The system implements requirements defined in Doorstop documents:

**Requirements (REQ):**
- REQ002-REQ007: Remote Client Application specifications
- REQ008-REQ011: Communicator Application specifications

**Design Specifications (SDD):**
- SDD001-SDD019: Remote Client detailed design
- SDD020-SDD029: Communicator detailed design

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
- Check LTE-M coverage in your area
- Review message log for `+CEREG` status codes

**Cannot receive downlink messages:**
- Ensure UDP port 55555 is bound (check log for `[SUCCESS] UDP port 55555 bound`)
- Verify `+CSCON: 1` URC is received when Communicator sends
- Check source IP filtering (must be `100.127.10.16`)

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
│       └── SDD001.yml - SDD029.yml
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

- Nordic Semiconductor for Thingy:91 X hardware
- Soracom for IoT connectivity platform
- Doorstop for requirements management
