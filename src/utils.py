"""
Utility functions for bioreactor operations.
These functions are designed to be used with bioreactor.run() for scheduled tasks.
"""

import time
import logging

logger = logging.getLogger("Bioreactor.Utils")


def actuate_relay_timed(bioreactor, relay_name, duration_seconds, elapsed=None):
    """
    Generic function to actuate any relay for a specified duration.
    
    Args:
        bioreactor: Bioreactor instance
        relay_name: Name of the relay to actuate
        duration_seconds: How long to keep relay ON (in seconds)
        elapsed: Time elapsed since job started (optional)
    """
    if not bioreactor.is_component_initialized('relays'):
        bioreactor.logger.warning("Relays not initialized")
        return
    
    if not hasattr(bioreactor, 'relays') or relay_name not in bioreactor.relays:
        bioreactor.logger.warning(f"Relay '{relay_name}' not found")
        return
    
    try:
        import lgpio
        
        relay_info = bioreactor.relays[relay_name]
        gpio_chip = relay_info['chip']
        pin = relay_info['pin']
        
        # Turn relay ON
        lgpio.gpio_write(gpio_chip, pin, 0)
        bioreactor.logger.info(f"{relay_name} relay turned ON")
        
        # Wait for specified duration
        time.sleep(duration_seconds)
        
        # Turn relay OFF
        lgpio.gpio_write(gpio_chip, pin, 1)
        bioreactor.logger.info(f"{relay_name} relay turned OFF ({duration_seconds}s elapsed)")
        
    except Exception as e:
        bioreactor.logger.error(f"Error actuating {relay_name} relay: {e}")


def actuate_pump1_relay(bioreactor, elapsed=None):
    """
    Actuate pump1 relay ON for 10 seconds.
    Designed to run every 5 minutes (300 seconds).
    
    Uses the general actuate_relay_timed function.
    
    Args:
        bioreactor: Bioreactor instance
        elapsed: Time elapsed since job started (optional, provided by run())
    """
    actuate_relay_timed(bioreactor, 'pump_1', 10, elapsed)

