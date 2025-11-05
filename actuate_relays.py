import RPi.GPIO as GPIO

# GPIO Setup for Relays
RELAY_PINS = {
    'relay1': 29,
    'relay2': 31,
    'relay3': 33,
    'relay4': 37
}

# Initialize GPIO
GPIO.setmode(GPIO.BOARD)  # Use physical pin numbering
for pin in RELAY_PINS.values():
    GPIO.setup(pin, GPIO.OUT)
    GPIO.output(pin, GPIO.LOW)  # Initialize all relays to OFF

def actuate_relay(relay_name, state):
    """
    Actuate a specific relay on or off.
    
    Parameters:
    -----------
    relay_name : str
        Name of the relay ('relay1', 'relay2', 'relay3', or 'relay4')
    state : bool or str
        True/'on'/1 to turn relay ON, False/'off'/0 to turn relay OFF
    
    Returns:
    --------
    bool : True if successful, False otherwise
    
    Example:
    --------
    actuate_relay('relay1', True)   # Turn relay 1 ON
    actuate_relay('relay2', 'off')  # Turn relay 2 OFF
    """
    if relay_name not in RELAY_PINS:
        print(f"Error: Invalid relay name '{relay_name}'. Valid names: {list(RELAY_PINS.keys())}")
        return False
    
    pin = RELAY_PINS[relay_name]
    
    # Convert state to boolean
    if isinstance(state, str):
        state = state.lower() in ['on', 'true', '1']
    else:
        state = bool(state)
    
    try:
        GPIO.output(pin, GPIO.HIGH if state else GPIO.LOW)
        print(f"{relay_name} (Pin {pin}): {'ON' if state else 'OFF'}")
        return True
    except Exception as e:
        print(f"Error actuating {relay_name}: {e}")
        return False

def actuate_relay_by_pin(pin, state):
    """
    Actuate a relay by its physical pin number.
    
    Parameters:
    -----------
    pin : int
        Physical pin number (29, 31, 33, or 37)
    state : bool or str
        True/'on'/1 to turn relay ON, False/'off'/0 to turn relay OFF
    
    Returns:
    --------
    bool : True if successful, False otherwise
    
    Example:
    --------
    actuate_relay_by_pin(29, True)   # Turn relay on pin 29 ON
    actuate_relay_by_pin(31, False)  # Turn relay on pin 31 OFF
    """
    if pin not in RELAY_PINS.values():
        print(f"Error: Invalid pin number {pin}. Valid pins: {list(RELAY_PINS.values())}")
        return False
    
    # Convert state to boolean
    if isinstance(state, str):
        state = state.lower() in ['on', 'true', '1']
    else:
        state = bool(state)
    
    try:
        GPIO.output(pin, GPIO.HIGH if state else GPIO.LOW)
        relay_name = [name for name, p in RELAY_PINS.items() if p == pin][0]
        print(f"{relay_name} (Pin {pin}): {'ON' if state else 'OFF'}")
        return True
    except Exception as e:
        print(f"Error actuating relay on pin {pin}: {e}")
        return False

def actuate_all_relays(state):
    """
    Actuate all relays at once.
    
    Parameters:
    -----------
    state : bool or str
        True/'on'/1 to turn all relays ON, False/'off'/0 to turn all relays OFF
    
    Example:
    --------
    actuate_all_relays(True)   # Turn all relays ON
    actuate_all_relays(False)  # Turn all relays OFF
    """
    for relay_name in RELAY_PINS.keys():
        actuate_relay(relay_name, state)

def get_relay_states():
    """
    Get the current state of all relays.
    
    Returns:
    --------
    dict : Dictionary with relay names as keys and their states (True/False) as values
    """
    states = {}
    for relay_name, pin in RELAY_PINS.items():
        states[relay_name] = bool(GPIO.input(pin))
    return states

def cleanup_gpio():
    """
    Cleanup GPIO settings. Call this before exiting the program.
    """
    GPIO.cleanup()
    print("GPIO cleanup completed")

if __name__ == "__main__":
    # Example usage
    print("Relay Control Example")
    print("=" * 50)
    
    # Turn on individual relays
    actuate_relay('relay1', True)
    actuate_relay('relay2', True)
    
    # Check states
    print("\nCurrent relay states:")
    print(get_relay_states())
    
    # Turn off by pin number
    actuate_relay_by_pin(29, False)
    
    # Turn all on
    print("\nTurning all relays ON:")
    actuate_all_relays(True)
    
    # Turn all off
    print("\nTurning all relays OFF:")
    actuate_all_relays(False)
    
    # Cleanup
    cleanup_gpio()

