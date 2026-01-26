"""Device Profile Factory for instantiating device profiles (SDD030)."""

from typing import Dict
from .base_device import BaseDeviceProfile
from .nordic_thingy91x import NordicThingy91XProfile
from .murata_type1sc_ntng import MurataType1SCProfile


class DeviceProfileFactory:
    """Factory for creating device profile instances."""

    @staticmethod
    def create(device_type: str, config: Dict = None) -> BaseDeviceProfile:
        """
        Create a device profile instance.
        
        Args:
            device_type: Device type identifier ('nordic_thingy91x' or 'murata_type1sc_ntng')
            config: Optional configuration dictionary
            
        Returns:
            BaseDeviceProfile subclass instance
            
        Raises:
            ValueError: If device_type is not supported
        """
        device_type_lower = device_type.lower().strip()

        if device_type_lower in ['nordic_thingy91x', 'nordic', 'thingy91x', 'thingy']:
            return NordicThingy91XProfile()

        elif device_type_lower in ['murata_type1sc_ntng', 'murata', 'type1sc', 'murata_type1sc']:
            return MurataType1SCProfile()

        else:
            raise ValueError(
                f"Unsupported device type: {device_type}. "
                f"Supported types: 'nordic_thingy91x', 'murata_type1sc_ntng'"
            )

    @staticmethod
    def list_supported_devices() -> list:
        """Return list of supported device types."""
        return [
            {
                'id': 'nordic_thingy91x',
                'name': 'Nordic Thingy:91 X',
                'manufacturer': 'Nordic Semiconductor',
                'aliases': ['nordic', 'thingy91x', 'thingy'],
            },
            {
                'id': 'murata_type1sc_ntng',
                'name': 'Murata Type 1SC-NTN',
                'manufacturer': 'Murata',
                'aliases': ['murata', 'type1sc', 'murata_type1sc'],
            },
        ]
