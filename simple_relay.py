import lgpio

# Open GPIO chip and set pin 29 (GPIO 5) as output
chip = lgpio.gpiochip_open(4)
lgpio.gpio_claim_output(chip, 5, 0)

def relay(state):
    """Turn relay on (True/1) or off (False/0)"""
    lgpio.gpio_write(chip, 5, 1 if state else 0)

# Example usage:
relay(True)   # Turn ON
relay(False)  # Turn OFF

