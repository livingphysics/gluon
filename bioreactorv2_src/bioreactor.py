import csv
import logging
import os
import threading
import time
from contextlib import contextmanager
from typing import List, Tuple, Optional, Union
from datetime import datetime

import adafruit_ads7830.ads7830 as ADC
import board
import busio
import matplotlib.pyplot as plt
import neopixel
import numpy as np
import RPi.GPIO as IO
from adafruit_ina219 import INA219
from matplotlib.animation import FuncAnimation
from ticlib import TicUSB


from .config import Config as cfg
from ds18b20 import DS18B20

logging.basicConfig(
    level=getattr(logging, cfg.LOG_LEVEL),
    format=cfg.LOG_FORMAT
)


class Bioreactor():
    """Class to manage all sensors and operations for the bioreactor"""
    
    def __init__(self) -> None:
        """Initialize selected hardware components based on init_components dict."""

        self.cfg = cfg

        self.logger = logging.getLogger("Bioreactor")
        self.logger.setLevel(getattr(cfg, 'LOG_LEVEL', 'INFO'))
        if hasattr(cfg, 'LOG_FILE') and cfg.LOG_FILE:
            handler = logging.FileHandler(cfg.LOG_FILE)
        else:
            handler = logging.StreamHandler()
        formatter = logging.Formatter(cfg.LOG_FORMAT)
        handler.setFormatter(formatter)
        if not self.logger.hasHandlers():
            self.logger.addHandler(handler)
        self.logger.info("Initializing Bioreactor...")

        self._init_components = {k: cfg.INIT_COMPONENTS.get(k, True) for k in cfg.INIT_COMPONENTS}
        self._initialized = {}

        # I2C (required for several components)
        if any([self._init_components.get(k, True) for k in ['pumps', 'optical_density', 'peltier']]):
            try:
                self.i2c = busio.I2C(board.SCL, board.SDA)
                self._initialized['i2c'] = True
                self.logger.info("I2C initialized.")
            except Exception as e:
                self.logger.error(f"I2C initialization failed: {e}")
                self._initialized['i2c'] = False

        # LEDs
        if self._init_components.get('leds', True):
            try:
                self.board_mode = cfg.LED_MODE.upper()
                self.led_pin = cfg.LED_PIN
                if self.board_mode == 'BOARD':
                    IO.setmode(IO.BOARD)
                elif self.board_mode == 'BCM':
                    self.led_pin = cfg.BCM_MAP[self.led_pin]
                    IO.setmode(IO.BCM)
                else:
                    raise ValueError("Invalid board mode: use 'BCM' or 'BOARD'")
                IO.setup(self.led_pin, IO.OUT)
                IO.output(self.led_pin, 0)
                self._initialized['leds'] = True
                self.logger.info("LEDs initialized.")
            except Exception as e:
                self.logger.error(f"LEDs initialization failed: {e}")
                self._initialized['leds'] = False

        # Stirrer
        if self._init_components.get('stirrer', True):
            try:
                IO.setup(cfg.STIRRER_PIN, IO.OUT)
                self.stirrer = IO.PWM(cfg.STIRRER_PIN, cfg.STIRRER_SPEED)
                self.stirrer.start(0)
                self.stirrer.ChangeDutyCycle(cfg.DUTY_CYCLE)
                self._initialized['stirrer'] = True
                self.logger.info("Stirrer initialized.")
            except Exception as e:
                self.logger.error(f"Stirrer initialization failed: {e}")
                self._initialized['stirrer'] = False

        # Ring Light
        if self._init_components.get('ring_light', True):
            try:
                self.ring_light = neopixel.NeoPixel(board.D10, cfg.RING_LIGHT_COUNT, brightness=cfg.RING_LIGHT_BRIGHTNESS, auto_write=False)
                self.change_ring_light((0,0,0))
                self._initialized['ring_light'] = True
                self.logger.info("Ring light initialized.")
            except Exception as e:
                self.logger.error(f"Ring light initialization failed: {e}")
                self._initialized['ring_light'] = False

        # Optical Density
        if self._init_components.get('optical_density', True):
            try:
                self.adc_1 = ADC.ADS7830(self.i2c, address=cfg.ADC_1_ADDRESS)
                self.REF_1 = cfg.ADC_1_REF_VOLTAGE
                self.adc_2 = ADC.ADS7830(self.i2c, address=cfg.ADC_2_ADDRESS)
                self.REF_2 = cfg.ADC_2_REF_VOLTAGE
                self._initialized['optical_density'] = True
                self.logger.info("Optical density sensors initialized.")
            except Exception as e:
                self.logger.error(f"Optical density initialization failed: {e}")
                self._initialized['optical_density'] = False

        # Temp sensors
        if self._init_components.get('temp', True):
            try:
                self.vial_temp_sensors = np.array(DS18B20.get_all_sensors())[cfg.VIAL_TEMP_SENSOR_ORDER]
                self._initialized['temp'] = True
                self.logger.info("Temperature sensors initialized.")
            except Exception as e:
                self.logger.error(f"Temperature sensors initialization failed: {e}")
                self._initialized['temp'] = False

        # Ambient temperature sensor
        if self._init_components.get('ambient', True):
            try:
                from adafruit_pct2075 import PCT2075
                self.ambient = PCT2075(self.i2c)
                self._initialized['ambient'] = True
                self.logger.info("Ambient temperature sensor initialized.")
            except Exception as e:
                self.logger.error(f"Ambient temperature sensor initialization failed: {e}")
                self._initialized['ambient'] = False

        # Peltier
        if self._init_components.get('peltier', True):
            try:
                self.peltier_curr_sensor = INA219(self.i2c)
                IO.setup(cfg.PELTIER_PWM_PIN, IO.OUT)
                IO.setup(cfg.PELTIER_DIR_PIN, IO.OUT)
                self.pwm = IO.PWM(cfg.PELTIER_PWM_PIN, cfg.PELTIER_PWM_FREQ)
                self.pwm.start(0)
                self._initialized['peltier'] = True
                self.logger.info("Peltier initialized.")
            except Exception as e:
                self.logger.error(f"Peltier initialization failed: {e}")
                self._initialized['peltier'] = False

        # Relays
        if self._init_components.get('relays', True):
            try:
                self.relays = {}
                for i, (pin, name) in enumerate(zip(cfg.RELAY_PINS, cfg.RELAY_NAMES)):
                    IO.setup(pin, IO.OUT)
                    IO.output(pin, 1)  # Initialize relays to OFF state
                    self.relays[name] = pin
                    self.logger.info(f"Relay {name} initialized on pin {pin}.")
                self._initialized['relays'] = True
            except Exception as e:
                self.logger.error(f"Relay initialization failed: {e}")
                self._initialized['relays'] = False

        # Pumps
        if self._init_components.get('pumps', True):
            try:
                self.pumps = {}
                self.calibration = {}
                self.pump_direction = {}
                for name, settings in cfg.PUMPS.items():
                    serial = settings['serial']
                    direction = settings.get('direction')
                    if direction not in ('forward', 'reverse'):
                        raise ValueError(f"Pump {name} must have direction set to 'forward' or 'reverse'")
                    if 'forward' not in settings:
                        raise ValueError(f"Pump {name} must have 'forward' calibration settings")
                    tic = TicUSB(serial_number=serial)
                    tic.energize()
                    tic.exit_safe_start()
                    tic.set_step_mode(3)
                    tic.set_current_limit(32)
                    tic.set_target_velocity(2000000)
                    time.sleep(3.0)
                    tic.set_target_velocity(0)
                    tic.deenergize()
                    self.pumps[name] = tic
                    self.calibration[name] = {
                        'forward': settings['forward']
                    }
                    self.pump_direction[name] = direction
                    self.logger.info(f"Pump {name} initialized (serial {serial}, direction {direction}).")
                self._initialized['pumps'] = True
            except Exception as e:
                self.logger.error(f"Pump initialization failed: {e}")
                self._initialized['pumps'] = False

        # For PID
        self._temp_integral = 0.0
        self._temp_last_error = 0.0

        # Threading
        self._threads = []
        self._stop_event = threading.Event()

        # Set up CSV writer for sensor data using SENSOR_LABELS
        sensor_keys = (
            [f'photodiode_{i+1}' for i in range(12)] +
            [f'io_temp_{i+1}' for i in range(2)] +
            [f'vial_temp_{i+1}' for i in range(4)] +
            ['ambient_temp'] +
            ['peltier_current']
        )
        fieldnames = ['time'] + [cfg.SENSOR_LABELS[k] for k in sensor_keys]
        self.fieldnames = fieldnames
        # Add timestamp to filename and create bioreactor_data directory
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        base_filename = getattr(cfg, 'DATA_OUT_FILE', 'bioreactor_data.csv')
        
        # Ensure bioreactor_data directory exists
        data_dir = 'bioreactor_data'
        os.makedirs(data_dir, exist_ok=True)
        
        out_file_path = os.path.join(data_dir, f"{timestamp}_{base_filename}")
        self.out_file = open(out_file_path, 'w', newline='')
        self.writer = csv.DictWriter(self.out_file, fieldnames=fieldnames)
        self.writer.writeheader()

        self.logger.info("Bioreactor initialization complete.")

    # Utility methods for hardware actions

    def change_led(self, state: bool) -> None:
        if not self._initialized.get('leds'):
            return
        
        try:
            IO.output(self.led_pin, 1 if state else 0)
            self.logger.info(f"LEDs turned {'ON' if state else 'OFF'}.")
        except Exception as e:
            self.logger.error(f"Error changing LED state: {e}")
            raise

    def change_ring_light(self, color, pixel=None) -> None:
        if not self._initialized.get('ring_light'):
            return
        
        try:
            if pixel is None:
                self.ring_light.fill(color)
            else:
                self.ring_light[pixel] = color
            self.ring_light.show()
            self.logger.info(f"Ring light changed to {color} (pixel {pixel}).")
        except Exception as e:
            self.logger.error(f"Error changing ring light: {e}")
            raise



    def change_peltier(self, power: int, forward: bool) -> None:
        """Change the peltier power and direction.
        
        Args:
            power (int): Power level from 0-100 (duty cycle percentage)
            forward (bool): Direction of peltier (True for forward, False for reverse)
        """
        if not self._initialized.get('peltier'):
            return
            
        try:
            IO.output(self.cfg.PELTIER_DIR_PIN, IO.HIGH if forward else IO.LOW)
            self.pwm.ChangeDutyCycle(power)
            self.logger.info(f"Peltier set to {power}% power, direction: {'forward' if forward else 'reverse'}")
        except Exception as e:
            self.logger.error(f"Error changing peltier: {e}")
            raise

    def change_relay(self, relay_name: str, state: bool) -> None:
        """Change the state of a specific relay.
        
        Args:
            relay_name (str): Name of the relay (e.g., 'relay_1', 'relay_2', etc.)
            state (bool): True to turn ON, False to turn OFF
        """
        if not self._initialized.get('relays'):
            self.logger.warning("Relays not initialized")
            return
            
        if relay_name not in self.relays:
            raise ValueError(f"No relay named '{relay_name}' configured. Available relays: {list(self.relays.keys())}")
            
        try:
            pin = self.relays[relay_name]
            IO.output(pin, 0 if state else 1)
            self.logger.info(f"Relay {relay_name} turned {'ON' if state else 'OFF'} (pin {pin})")
        except Exception as e:
            self.logger.error(f"Error changing relay {relay_name}: {e}")
            raise

    def change_all_relays(self, state: bool) -> None:
        """Change the state of all relays simultaneously.
        
        Args:
            state (bool): True to turn all relays ON, False to turn all OFF
        """
        if not self._initialized.get('relays'):
            self.logger.warning("Relays not initialized")
            return
            
        try:
            for relay_name, pin in self.relays.items():
                IO.output(pin, 0 if state else 1)
            self.logger.info(f"All relays turned {'ON' if state else 'OFF'}")
        except Exception as e:
            self.logger.error(f"Error changing all relays: {e}")
            raise

    def get_relay_state(self, relay_name: str) -> bool:
        """Get the current state of a specific relay.
        
        Args:
            relay_name (str): Name of the relay
            
        Returns:
            bool: True if relay is ON, False if OFF
        """
        if not self._initialized.get('relays'):
            self.logger.warning("Relays not initialized")
            return False
            
        if relay_name not in self.relays:
            raise ValueError(f"No relay named '{relay_name}' configured. Available relays: {list(self.relays.keys())}")
            
        try:
            pin = self.relays[relay_name]
            state = IO.input(pin) == 1
            return state
        except Exception as e:
            self.logger.error(f"Error reading relay {relay_name} state: {e}")
            return False

    def get_all_relay_states(self) -> dict[str, bool]:
        """Get the current state of all relays.
        
        Returns:
            dict: Dictionary mapping relay names to their states (True=ON, False=OFF)
        """
        if not self._initialized.get('relays'):
            self.logger.warning("Relays not initialized")
            return {}
            
        try:
            states = {}
            for relay_name, pin in self.relays.items():
                states[relay_name] = IO.input(pin) == 1
            return states
        except Exception as e:
            self.logger.error(f"Error reading all relay states: {e}")
            return {}

    def change_pump(self, pump_name: str, ml_per_sec: float) -> None:
        if not self._initialized.get('pumps'):
            return
        if pump_name not in self.pumps:
            raise ValueError(f"No pump named '{pump_name}' configured")
        if ml_per_sec < 0:
            raise ValueError("ml_per_sec must be positive")
        direction = self.pump_direction.get(pump_name)
        if direction not in ('forward', 'reverse'):
            raise ValueError(f"Pump {pump_name} has invalid direction configuration")
        cal = self.calibration[pump_name].get(direction)
        if cal is None:
            raise ValueError(f"Calibration for direction '{direction}' not found for pump '{pump_name}'")
        gradient = cal.get('gradient')
        intercept = cal.get('intercept')
        if gradient is None or intercept is None:
            raise ValueError(f"Calibration for pump '{pump_name}' direction '{direction}' missing 'gradient' or 'intercept'")
        steps_per_sec = 8*int((ml_per_sec - intercept) / gradient)
        # Set velocity sign: positive if direction is 'forward', negative if 'reverse'
        velocity = steps_per_sec if direction == 'forward' else -steps_per_sec
        try:
            if velocity == 0:
                self.pumps[pump_name].deenergize()
                self.logger.info(f"Set pump {pump_name} to de-energized).")
            else:
                self.pumps[pump_name].energize()
                self.pumps[pump_name].exit_safe_start()
                time.sleep(0.01)
                self.pumps[pump_name].set_target_velocity(velocity)
                self.logger.info(f"Set pump {pump_name} to {ml_per_sec} ml/sec (velocity {velocity}, direction {direction}).")
        except Exception as e:
            self.logger.error(f"Error setting velocity for '{pump_name}': {e}")
            raise

    def get_photodiodes(self):
        if not self._initialized.get('optical_density'):
            return [float('nan')] * 12
        
        # Turn on IR LEDs if available
        leds_were_on = False
        if self._initialized.get('leds'):
            try:
                # Check if LEDs are already on
                leds_were_on = IO.input(self.led_pin) == 1
                if not leds_were_on:
                    self.change_led(True)
                    # Wait for photodiodes to stabilize
                    time.sleep(1.0)
            except Exception as e:
                self.logger.error(f"Error controlling LEDs for photodiode reading: {e}")
        
        try:
            # Read photodiodes while LEDs are on
            readings = [self.adc_1.read(i) * self.REF_1 / 65535.0 for i in self.cfg.ADC_1_PHOTODIODE_CHANNELS] + [self.adc_2.read(i) * self.REF_2 / 65535.0 for i in self.cfg.ADC_2_PHOTODIODE_CHANNELS]
            self.logger.info(f"Photodiodes Read ")
            return readings
        except Exception as e:
            self.logger.error(f"Error reading photodiodes: {e}")
            return [float('nan')] * 12
        finally:
            # Turn off LEDs only if we turned them on
            if self._initialized.get('leds') and not leds_were_on:
                try:
                    self.change_led(False)
                except Exception as e:
                    self.logger.error(f"Error turning off LEDs after photodiode reading: {e}")
        
    def get_io_temp(self):
        if not self._initialized.get('optical_density'):
            return [float('nan')] * 2
        
        try:
            return [self.adc_1.read(i) * self.REF_1 / 65535.0 for i in self.cfg.ADC_1_IO_TEMP_CHANNELS] + [self.adc_2.read(i) * self.REF_2 / 65535.0 for i in self.cfg.ADC_2_IO_TEMP_CHANNELS]
        except Exception as e:
            self.logger.error(f"Error reading IO temp: {e}")
            return [float('nan')] * 2
        
    def get_vial_temp(self):
        if not self._initialized.get('temp'):
            return [float('nan')]
        
        try:
            return [vial_temp_sensor.get_temperature() for vial_temp_sensor in self.vial_temp_sensors]
        except Exception as e:
            self.logger.error(f"Error reading vial temp: {e}")
            return [float('nan')] * len(self.vial_temp_sensors)
        
    def get_peltier_curr(self):
        if not self._initialized.get('peltier'):
            return float('nan')
        
        try:
            return self.peltier_curr_sensor.current / 1000
        except Exception as e:
            self.logger.error(f"Error reading peltier current: {e}")
            return float('nan')

    def get_ambient_temp(self):
        if not self._initialized.get('ambient'):
            return float('nan')
        
        try:
            return self.ambient.temperature
        except Exception as e:
            self.logger.error(f"Error reading ambient temperature: {e}")
            return float('nan')

    # Threaded scheduling

    def run(self, jobs):
        """
        jobs: list of (function, frequency, duration) tuples.
        Each function is called with self (or bioreactor_instance) as first argument.
        Non-blocking: returns immediately after starting threads.
        If duration is True, the job runs indefinitely until stop_all() is called.
        """
        self._stop_event.clear()

        self._threads = []
        def thread_worker(func, freq, dur):
            start = time.time()
            while not self._stop_event.is_set() and (dur is True or time.time() - start < dur):
                t0 = time.time()

                try:
                    global_elapsed = time.time() - start
                    func(self, elapsed=global_elapsed)
                except Exception as e:
                    self.logger.error(f"Exception in thread for {func.__name__}: {e}")

                if freq is True:
                    continue

                loop_elapsed = time.time() - t0
                sleep_time = max(0, freq - loop_elapsed)
                if sleep_time > 0:
                    time.sleep(sleep_time)

        for func, freq, dur in jobs:
            th = threading.Thread(target=thread_worker, args=(func, freq, dur))
            th.daemon = True
            th.start()
            self._threads.append(th)

        self.logger.info(f"Started {len(jobs)} job threads.")

    def stop_all(self):
        self._stop_event.set()
        self.logger.info("Stop event set for all threads.")

    def finish(self) -> None:
        self.logger.info("Cleaning up Bioreactor...")

        # Stop all threads
        self.stop_all()

        # LEDs
        if self._initialized.get('leds'):
            try:
                IO.output(self.led_pin, 0)
            except Exception:
                self.logger.error("Error turning off LEDs.")

        # Stirrer
        if self._initialized.get('stirrer'):
            try:
                self.stirrer.stop(0)
            except Exception:
                self.logger.error("Error stopping stirrer.")

        # Ring Light
        if self._initialized.get('ring_light'):
            try:
                self.change_ring_light((0,0,0))
            except Exception:
                self.logger.error("Error turning off ring light.")

        # Peltier
        if self._initialized.get('peltier'):
            try:
                self.pwm.ChangeDutyCycle(0)
            except Exception:
                self.logger.error("Error stopping peltier.")

        # Pumps
        if self._initialized.get('pumps'):
            try:
                for tic in self.pumps.values():
                    tic.deenergize()
                    tic.enter_safe_start()
            except Exception:
                self.logger.error("Error stopping pumps.")

        # Relays
        if self._initialized.get('relays'):
            try:
                for relay_name, pin in self.relays.items():
                    IO.output(pin, 0)  # Turn off all relays
                self.logger.info("All relays turned off.")
            except Exception:
                self.logger.error("Error turning off relays.")

        # GPIO cleanup
        if self._initialized.get('leds') or self._initialized.get('stirrer') or self._initialized.get('peltier') or self._initialized.get('relays'):
            try:
                IO.cleanup()
            except Exception:
                self.logger.error("Error cleaning up GPIO.")

        self.logger.info("Bioreactor cleanup complete.")

    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_value, traceback):
        self.finish()
        return False
