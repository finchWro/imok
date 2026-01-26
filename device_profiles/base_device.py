"""Abstract base class for IoT device profiles (SDD030)."""

from abc import ABC, abstractmethod
from typing import Optional, Tuple, Dict


class BaseDeviceProfile(ABC):
    """
    Abstract base class defining the interface for device-specific implementations.
    
    Subclasses implement device-specific AT command sequences and protocols
    while maintaining a common interface for the Remote Client Application.
    """

    @abstractmethod
    def get_device_info(self) -> Dict[str, str]:
        """
        Return device metadata.
        
        Returns:
            dict with keys: name, manufacturer, firmware_type
        """
        pass

    @abstractmethod
    def initialize_network(self, serial_manager) -> bool:
        """
        Complete network initialization sequence per SDD030.
        
        Includes RAT selection, band configuration, PDP context setup,
        and waiting for network registration.
        
        Args:
            serial_manager: SerialManager instance for AT command execution
            
        Returns:
            bool: True if successful, False otherwise
        """
        pass

    @abstractmethod
    def bind_udp_port(self, serial_manager, port: int) -> bool:
        """
        Bind UDP port for downlink reception per SDD026/SDD027.
        
        Args:
            serial_manager: SerialManager instance
            port: UDP port number (e.g., 55555)
            
        Returns:
            bool: True if successful, False otherwise
        """
        pass

    @abstractmethod
    def open_socket_connection(self, serial_manager) -> bool:
        """
        Open UDP socket connection to Soracom Harvest Data (SDD018/SDD037/SDD038).
        
        Device-specific implementation for creating UDP socket.
        
        Args:
            serial_manager: SerialManager instance
            
        Returns:
            bool: True if successful, False otherwise
        """
        pass

    @abstractmethod
    def send_to_harvest(self, serial_manager, data: str) -> bool:
        """
        Send data to Soracom Harvest Data (SDD019).
        
        Handles device-specific encoding and multi-step operations.
        
        Args:
            serial_manager: SerialManager instance
            data: Message string to send
            
        Returns:
            bool: True if successful, False otherwise
        """
        pass

    @abstractmethod
    def receive_udp(self, serial_manager, buffer_size: int) -> Optional[Tuple[str, int, str]]:
        """
        Receive UDP downlink data (SDD027/SDD028).
        
        Args:
            serial_manager: SerialManager instance
            buffer_size: UDP buffer size in bytes
            
        Returns:
            tuple: (ip_address, port, payload) on success, None on failure
        """
        pass

    @abstractmethod
    def get_signal_quality(self, serial_manager) -> Optional[Dict[str, int]]:
        """
        Query signal quality metrics (SDD015).
        
        Args:
            serial_manager: SerialManager instance
            
        Returns:
            dict with keys: rsrp, rsrq, sinr, rssi (all in dBm) or None on failure
        """
        pass

    @abstractmethod
    def activate_pdp_context(self, serial_manager) -> bool:
        """
        Configure PDP context for data communication (SDD014/SDD035/SDD036).
        
        Args:
            serial_manager: SerialManager instance
            
        Returns:
            bool: True if successful, False otherwise
        """
        pass

    @abstractmethod
    def parse_network_registration_urc(self, urc: str) -> Optional[Dict]:
        """
        Parse network registration URCs.
        
        Args:
            urc: Unsolicited result code string
            
        Returns:
            dict with registration status info, or None if not a registration URC
        """
        pass
