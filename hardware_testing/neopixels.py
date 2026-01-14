from pi5neo import Pi5Neo
import time

# Initialize the Pi5Neo class with 10 LEDs and an SPI speed of 800kHz
neo = Pi5Neo('/dev/spidev0.0', 8, 800)
# Fill the strip with a red color
neo.fill_strip(12, 0, 0)
neo.update_strip()  # Commit changes to the LEDs
time.sleep(2)
# Set the 5th LED to blue
neo.set_led_color(4, 0, 0, 12)
neo.update_strip()
time.sleep(2)
neo.fill_strip(0, 0, 0)
neo.update_strip()

