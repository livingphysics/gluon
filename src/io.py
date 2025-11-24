"""
Input/Output functions for bioreactor.
These are not intended to be used directly by the user, but rather to be used by the bioreactor class.
"""

import logging
logger = logging.getLogger("Bioreactor.IO")

def get_temperature(bioreactor, sensor_index=0):
        """Get temperature from DS18B20 sensor(s).
        
        Args:
            sensor_index (int): Index of sensor to read (default: 0 for first sensor)
            
        Returns:
            float: Temperature in Celsius, or NaN if sensor not available
        """
        if not bioreactor.is_component_initialized('temp_sensor'):
            return float('nan')
        
        try:
            if hasattr(bioreactor, 'temp_sensors') and len(bioreactor.temp_sensors) > sensor_index:
                return bioreactor.temp_sensors[sensor_index].get_temperature()
            else:
                bioreactor.logger.warning(f"Temperature sensor index {sensor_index} not available")
                return float('nan')
        except Exception as e:
            bioreactor.logger.error(f"Error reading temperature sensor {sensor_index}: {e}")
            return float('nan')

def change_relay(bioreactor, relay_name: str, state: bool) -> None:
        """Change the state of a specific relay.
        
        Args:
            relay_name (str): Name of the relay (e.g., 'relay_1', 'relay_2', etc.)
            state (bool): True to turn ON, False to turn OFF
        """
        if not bioreactor._initialized.get('relays'):
            bioreactor.logger.warning("Relays not initialized")
            return
            
        if relay_name not in bioreactor.relays:
            raise ValueError(f"No relay named '{relay_name}' configured. Available relays: {list(bioreactor.relays.keys())}")
            
        try:
            pin = bioreactor.relays[relay_name]
            IO.output(pin, 0 if state else 1)
            bioreactor.logger.info(f"Relay {relay_name} turned {'ON' if state else 'OFF'} (pin {pin})")
        except Exception as e:
            bioreactor.logger.error(f"Error changing relay {relay_name}: {e}")
            raise

def change_all_relays(bioreactor, state: bool) -> None:
    """Change the state of all relays simultaneously.
    
    Args:
        state (bool): True to turn all relays ON, False to turn all OFF
    """
    if not bioreactor._initialized.get('relays'):
        bioreactor.logger.warning("Relays not initialized")
        return
        
    try:
        for relay_name, pin in bioreactor.relays.items():
            IO.output(pin, 0 if state else 1)
        bioreactor.logger.info(f"All relays turned {'ON' if state else 'OFF'}")
    except Exception as e:
        bioreactor.logger.error(f"Error changing all relays: {e}")
        raise

def get_relay_state(bioreactor, relay_name: str) -> bool:
    """Get the current state of a specific relay.
    
    Args:
        relay_name (str): Name of the relay
        
    Returns:
        bool: True if relay is ON, False if OFF
    """
    if not bioreactor._initialized.get('relays'):
        bioreactor.logger.warning("Relays not initialized")
        return False
        
    if relay_name not in bioreactor.relays:
        raise ValueError(f"No relay named '{relay_name}' configured. Available relays: {list(bioreactor.relays.keys())}")
        
    try:
        pin = bioreactor.relays[relay_name]
        state = IO.input(pin) == 1
        return state
    except Exception as e:
        bioreactor.logger.error(f"Error reading relay {relay_name} state: {e}")
        return False

def get_all_relay_states(bioreactor) -> dict[str, bool]:
    """Get the current state of all relays.
    
    Returns:
        dict: Dictionary mapping relay names to their states (True=ON, False=OFF)
    """
    if not bioreactor._initialized.get('relays'):
        bioreactor.logger.warning("Relays not initialized")
        return {}
        
    try:
        states = {}
        for relay_name, pin in bioreactor.relays.items():
            states[relay_name] = IO.input(pin) == 1
        return states
    except Exception as e:
        bioreactor.logger.error(f"Error reading all relay states: {e}")
        return {}