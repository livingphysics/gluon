"""
Utility functions for bioreactor operations.
These functions are designed to be used with bioreactor.run() for scheduled tasks.
"""

import time
import logging
import queue
from collections import deque
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.animation as animation
from matplotlib.widgets import TextBox

logger = logging.getLogger("Bioreactor.Utils")

# Global variables for plotting (shared across calls)
_plot_initialized = False
_fig = None
_ax1 = None
_ax2 = None
_co2_line = None  # Line object for CO2 plot
_o2_line = None  # Line object for O2 plot
_co2_data = deque(maxlen=1000)
_o2_data = deque(maxlen=1000)
_time_data = deque(maxlen=1000)
_start_time = None
_sensor_queue = queue.Queue()  # Thread-safe queue for sensor data
_anim = None  # Animation object

# Global variables for CO2 duration (editable via text box)
_co2_duration = 1.0  # Default 1 second (for pressurize_and_inject_co2 job)
_co2_setpoint = 10000.0  # Default CO2 setpoint in ppm (editable via text box)
_co2_setpoint_textbox = None  # Store text box reference
_bioreactor_ref = None  # Store bioreactor reference
_setpoint_ref = None  # Reference to setpoint for control job

# Global variable for pressurize duration (used by stabilize_co2)
_pressurize_duration = 10.0  # Default 10 seconds


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


def pressurize_and_inject_co2(bioreactor, pressurize_duration=10, pause=30, co2_duration=None, elapsed=None):
    """
    Pressurize with pump1, wait, then inject CO2.
    
    Sequence:
    1. Turn ON pump_1 relay for pressurize_duration seconds
    2. Turn OFF pump_1 relay
    3. Wait pause seconds
    4. Turn ON co2_solenoid relay for co2_duration seconds (uses global _co2_duration if not provided)
    5. Turn OFF co2_solenoid relay
    
    Args:
        bioreactor: Bioreactor instance
        pressurize_duration: Duration to run pump_1 (default: 10 seconds)
        pause: Wait time between pump and CO2 injection (default: 30 seconds)
        co2_duration: Duration for CO2 injection (default: uses global _co2_duration, typically 1 second)
        elapsed: Time elapsed since job started (optional)
    """
    global _co2_duration
    
    if not bioreactor.is_component_initialized('relays'):
        bioreactor.logger.warning("Relays not initialized")
        return
    
    # Use global co2_duration if not provided
    if co2_duration is None:
        co2_duration = _co2_duration
    
    pump_relay = 'pump_1'
    co2_relay = 'co2_solenoid'
    
    if pump_relay not in bioreactor.relays or co2_relay not in bioreactor.relays:
        bioreactor.logger.warning("Required relays not found")
        return
    
    try:
        import lgpio
        
        pump_info = bioreactor.relays[pump_relay]
        co2_info = bioreactor.relays[co2_relay]
        gpio_chip = pump_info['chip']  # Both use same chip
        pump_pin = pump_info['pin']
        co2_pin = co2_info['pin']
        
        # Step 1: Turn ON pump_1 for pressurize_duration
        bioreactor.logger.info(f"Pressurizing: pump_1 ON for {pressurize_duration}s")
        lgpio.gpio_write(gpio_chip, pump_pin, 0)  # 0 = ON
        time.sleep(pressurize_duration)
        lgpio.gpio_write(gpio_chip, pump_pin, 1)  # 1 = OFF
        bioreactor.logger.info("pump_1 turned OFF")
        
        # Step 2: Wait pause seconds
        bioreactor.logger.info(f"Waiting {pause}s before CO2 injection...")
        time.sleep(pause)
        
        # Step 3: Turn ON co2_solenoid for co2_duration
        bioreactor.logger.info(f"Injecting CO2: co2_solenoid ON for {co2_duration}s")
        lgpio.gpio_write(gpio_chip, co2_pin, 0)  # 0 = ON
        time.sleep(co2_duration)
        lgpio.gpio_write(gpio_chip, co2_pin, 1)  # 1 = OFF
        bioreactor.logger.info("co2_solenoid turned OFF - Pressurize and inject complete")
        
    except Exception as e:
        bioreactor.logger.error(f"Error in pressurize_and_inject_co2: {e}")
        # Try to turn off both relays in case of error
        try:
            import lgpio
            gpio_chip = bioreactor.relays[pump_relay]['chip']
            lgpio.gpio_write(gpio_chip, pump_info['pin'], 1)  # Turn off pump
            lgpio.gpio_write(gpio_chip, co2_info['pin'], 1)  # Turn off CO2
            bioreactor.logger.info("Emergency: Both relays turned OFF")
        except:
            pass


def create_inject_co2_job(delay_seconds, injection_duration_seconds):
    """
    Create an inject_co2_delayed function with specific delay and injection duration for use with bioreactor.run().
    
    Args:
        delay_seconds: Time to wait before starting CO2 injection
        injection_duration_seconds: Duration to keep CO2 solenoid ON
        
    Returns:
        function: A function that can be used with bioreactor.run()
        
    Example:
        jobs = [
            (create_inject_co2_job(300, 30), True, 330),  # Wait 5 min, inject 30s
        ]
    """
    def inject_co2_job(bioreactor, elapsed=None):
        inject_co2_delayed(bioreactor, delay_seconds, injection_duration_seconds, elapsed)
    
    return inject_co2_job


def inject_co2_delayed(bioreactor, delay_seconds, injection_duration_seconds, elapsed=None):
    """
    Wait for specified delay, then inject CO2 for specified duration by turning on co2_solenoid relay.
    This is a one-time job that completes after the injection.
    
    Sequence:
    1. Wait for delay_seconds
    2. Turn ON co2_solenoid relay for injection_duration_seconds
    3. Turn OFF co2_solenoid relay
    4. Job completes
    
    Args:
        bioreactor: Bioreactor instance
        delay_seconds: Time to wait before starting CO2 injection (in seconds)
        injection_duration_seconds: Duration to keep CO2 solenoid ON (in seconds)
        elapsed: Time elapsed since job started (optional, provided by run())
    """
    if not bioreactor.is_component_initialized('relays'):
        bioreactor.logger.warning("Relays not initialized, cannot inject CO2")
        return
    
    if not hasattr(bioreactor, 'relays') or 'co2_solenoid' not in bioreactor.relays:
        bioreactor.logger.warning("co2_solenoid relay not found")
        return
    
    try:
        import lgpio
        
        relay_info = bioreactor.relays['co2_solenoid']
        gpio_chip = relay_info['chip']
        relay_pin = relay_info['pin']
        
        # Step 1: Wait for specified delay
        bioreactor.logger.info(f"Waiting {delay_seconds} seconds before CO2 injection...")
        time.sleep(delay_seconds)
        
        # Step 2: Turn ON co2_solenoid for specified duration
        bioreactor.logger.info(f"Starting CO2 injection ({injection_duration_seconds} seconds)...")
        lgpio.gpio_write(gpio_chip, relay_pin, 0)  # 0 = ON
        bioreactor.logger.info("co2_solenoid turned ON")
        
        time.sleep(injection_duration_seconds)  # Inject for specified duration
        
        # Step 3: Turn OFF co2_solenoid
        lgpio.gpio_write(gpio_chip, relay_pin, 1)  # 1 = OFF
        bioreactor.logger.info("co2_solenoid turned OFF - CO2 injection complete")
        
    except Exception as e:
        bioreactor.logger.error(f"Error during CO2 injection: {e}")
        # Try to turn off relay in case of error
        try:
            import lgpio
            gpio_chip = bioreactor.relays['co2_solenoid']['chip']
            relay_pin = bioreactor.relays['co2_solenoid']['pin']
            lgpio.gpio_write(gpio_chip, relay_pin, 1)  # Turn off
            bioreactor.logger.info("Emergency: co2_solenoid turned OFF")
        except:
            pass


def create_flush_tank_job(duration_seconds):
    """
    Create a flush_tank function with a specific duration for use with bioreactor.run().
    
    Args:
        duration_seconds: Duration to keep valve open during flush
        
    Returns:
        function: A function that can be used with bioreactor.run()
        
    Example:
        jobs = [
            (create_flush_tank_job(30), 3600, True),  # Flush every hour for 30s
        ]
    """
    def flush_tank_job(bioreactor, elapsed=None):
        flush_tank(bioreactor, duration_seconds, elapsed)
    
    return flush_tank_job


def flush_tank(bioreactor, duration_seconds, elapsed=None):
    """
    Flush tank by running pump_1 and opening dump_valve for specified duration,
    then closing valve and continuing pump for the same duration.
    
    Sequence:
    1. Turn ON pump_1
    2. Turn ON dump_valve (valve opens)
    3. Wait for duration_seconds
    4. Turn OFF dump_valve (valve closes)
    5. Continue running pump_1 for additional duration_seconds
    6. Turn OFF pump_1
    
    Args:
        bioreactor: Bioreactor instance
        duration_seconds: Duration to keep valve open and continue pump after closing (in seconds)
        elapsed: Time elapsed since job started (optional, provided by run())
    """
    if not bioreactor.is_component_initialized('relays'):
        bioreactor.logger.warning("Relays not initialized, cannot flush tank")
        return
    
    if not hasattr(bioreactor, 'relays'):
        bioreactor.logger.warning("Relays not found")
        return
    
    pump_relay = 'pump_1'
    valve_relay = 'dump_valve'
    
    if pump_relay not in bioreactor.relays:
        bioreactor.logger.warning(f"Relay '{pump_relay}' not found")
        return
    
    if valve_relay not in bioreactor.relays:
        bioreactor.logger.warning(f"Relay '{valve_relay}' not found")
        return
    
    try:
        import lgpio
        
        pump_info = bioreactor.relays[pump_relay]
        valve_info = bioreactor.relays[valve_relay]
        gpio_chip = pump_info['chip']  # Both should use same chip
        pump_pin = pump_info['pin']
        valve_pin = valve_info['pin']
        
        bioreactor.logger.info(f"Starting tank flush: pump ON, valve opening for {duration_seconds}s")
        
        # Step 1: Turn ON pump_1
        lgpio.gpio_write(gpio_chip, pump_pin, 0)  # 0 = ON
        bioreactor.logger.info(f"{pump_relay} turned ON")
        
        # Step 2: Turn ON dump_valve (valve opens)
        lgpio.gpio_write(gpio_chip, valve_pin, 0)  # 0 = ON
        bioreactor.logger.info(f"{valve_relay} turned ON (valve open)")
        
        # Step 3: Wait for specified duration
        time.sleep(duration_seconds)
        bioreactor.logger.info(f"Valve open duration ({duration_seconds}s) completed")
        
        # Step 4: Turn OFF dump_valve (valve closes)
        lgpio.gpio_write(gpio_chip, valve_pin, 1)  # 1 = OFF
        bioreactor.logger.info(f"{valve_relay} turned OFF (valve closed)")
        
        # Step 5: Continue running pump_1 for additional duration_seconds
        bioreactor.logger.info(f"Continuing pump for additional {duration_seconds} seconds")
        time.sleep(duration_seconds)
        
        # Step 6: Turn OFF pump_1
        lgpio.gpio_write(gpio_chip, pump_pin, 1)  # 1 = OFF
        bioreactor.logger.info(f"{pump_relay} turned OFF - Tank flush complete")
        
    except Exception as e:
        bioreactor.logger.error(f"Error during tank flush: {e}")
        # Try to turn off both relays in case of error
        try:
            import lgpio
            gpio_chip = bioreactor.relays[pump_relay]['chip']
            lgpio.gpio_write(gpio_chip, pump_info['pin'], 1)  # Turn off pump
            lgpio.gpio_write(gpio_chip, valve_info['pin'], 1)  # Turn off valve
            bioreactor.logger.info("Emergency: Both relays turned OFF")
        except:
            pass


def create_stabilize_co2_job(setpoint_ppm=1000, tolerance_ppm=2000, pressurize_duration=10, pause=30):
    """
    Create a stabilize_co2 function with setpoint checking for use with bioreactor.run().
    
    Pauses when CO2 is above setpoint by more than tolerance_ppm (lets CO2 control job take over).
    Otherwise runs full stabilization.
    
    Each job instance maintains its own independent pressurize_duration state.
    Sets baseline CO2 duration to setpoint/100000 if setpoint exists, otherwise 0.5s.
    
    Args:
        setpoint_ppm: Target CO2 level in ppm (default: 1000)
        tolerance_ppm: Tolerance above setpoint in ppm - job pauses when CO2 exceeds setpoint+tolerance (default: 2000)
        pressurize_duration: Initial duration to run pump_1 (default: 10 seconds, may be adjusted)
        pause: Wait time between pump and CO2 injection (default: 30 seconds)
        
    Returns:
        function: A function that can be used with bioreactor.run()
        
    Example:
        jobs = [
            (create_stabilize_co2_job(10000, tolerance_ppm=2000), 180, True),  # Stabilize CO2 every 3 minutes, pauses when >2000ppm above setpoint
        ]
    """
    # Store pressurize_duration in closure to maintain independent state
    _local_pressurize_duration = {'value': pressurize_duration}
    
    # Set baseline CO2 duration based on setpoint
    global _co2_duration
    if setpoint_ppm is not None:
        _co2_duration = setpoint_ppm / 100000.0
    else:
        _co2_duration = 0.5
    
    def stabilize_co2_job(bioreactor, elapsed=None):
        stabilize_co2(bioreactor, setpoint_ppm=setpoint_ppm, tolerance_ppm=tolerance_ppm, 
                     pressurize_duration=_local_pressurize_duration['value'], pause=pause, 
                     elapsed=elapsed, pressurize_duration_ref=_local_pressurize_duration)
    
    return stabilize_co2_job


def stabilize_co2(bioreactor, setpoint_ppm=None, tolerance_ppm=1000, pressurize_duration=10, pause=30, co2_duration=None, elapsed=None, pressurize_duration_ref=None):
    """
    Stabilize CO2 by adjusting injection duration based on CO2 trend.
    
    If setpoint_ppm is provided and CO2 is not within tolerance_ppm of setpoint, just pressurizes with 0s CO2 injection.
    Otherwise, performs full stabilization:
    Does a linear fit on the last 70 CO2 measurements (or all if fewer exist),
    calculates the slope, and adjusts CO2 injection duration accordingly.
    If CO2 duration goes to zero, increases pressurize_duration instead.
    
    Sequence:
    1. (If setpoint provided) Check if CO2 is within tolerance - if not, just pressurize with 0s CO2
    2. Calculate linear fit slope from recent CO2 data
    3. Adjust CO2 duration by -slope/100 if slope != 0
    4. If CO2 duration hits zero, increase pressurize_duration by slope/100
    5. Run pressurize_and_inject_co2 with adjusted parameters
    
    Args:
        bioreactor: Bioreactor instance
        setpoint_ppm: Target CO2 level in ppm (optional, if None, always runs full stabilization)
        tolerance_ppm: Tolerance around setpoint in ppm (default: 1000)
        pressurize_duration: Initial duration to run pump_1 (default: 10 seconds, may be adjusted)
        pause: Wait time between pump and CO2 injection (default: 30 seconds)
        co2_duration: Initial CO2 injection duration (default: uses global _co2_duration, may be adjusted)
        elapsed: Time elapsed since job started (optional)
        pressurize_duration_ref: Reference to store pressurize_duration state (optional, for independent state per job)
    """
    global _co2_duration, _co2_data, _time_data, _start_time
    
    if not bioreactor.is_component_initialized('relays'):
        bioreactor.logger.warning("Relays not initialized")
        return
    
    # Use global co2_duration if not provided
    if co2_duration is None:
        co2_duration = _co2_duration
    
    # Use pressurize_duration from reference if provided (for independent state), otherwise use parameter
    if pressurize_duration_ref is not None:
        current_pressurize_duration = pressurize_duration_ref['value']
    else:
        current_pressurize_duration = pressurize_duration
    
    # Check if we should run full stabilization or just pressurize
    setpoint_adjustment = 0.0  # Will be calculated if setpoint is provided
    if setpoint_ppm is not None:
        # Get CO2 data to check if within tolerance
        if len(_co2_data) < 1:
            bioreactor.logger.warning("No CO2 data available, just pressurizing")
            pressurize_and_inject_co2(bioreactor, pressurize_duration, pause, 0, elapsed)
            return
        
        # Get the last 15 points (or all if fewer) to calculate average
        n_points = min(15, len(_co2_data))
        co2_values = np.array(list(_co2_data)[-n_points:])
        avg_co2 = np.mean(co2_values)
        signed_difference = avg_co2 - setpoint_ppm  # Positive if above, negative if below
        difference = abs(signed_difference)
        
        # Calculate setpoint adjustment: difference * 2.5e-4
        setpoint_adjustment = signed_difference * 2.5e-4
        
        # Only pause stabilization if CO2 is above setpoint by more than tolerance (let flush job handle it)
        if signed_difference > tolerance_ppm:
            # CO2 is significantly above setpoint - pause stabilization and let flush job handle it
            bioreactor.logger.info(f"Stabilization paused: CO2 ({avg_co2:.1f} ppm) is {signed_difference:.1f} ppm above setpoint ({setpoint_ppm} ppm), exceeds tolerance ({tolerance_ppm} ppm), flush job will handle")
            return
        else:
            # CO2 is at or below setpoint+tolerance - continue with normal stabilization
            if signed_difference > 0:
                bioreactor.logger.info(f"CO2 ({avg_co2:.1f} ppm) is {signed_difference:.1f} ppm above setpoint ({setpoint_ppm} ppm), within tolerance, running full stabilization")
            else:
                bioreactor.logger.info(f"CO2 ({avg_co2:.1f} ppm) is {abs(signed_difference):.1f} ppm below setpoint ({setpoint_ppm} ppm), running full stabilization")
            if setpoint_adjustment != 0:
                bioreactor.logger.info(f"Setpoint adjustment: {setpoint_adjustment:.3f}s (will be added to CO2 injection if below setpoint)")
    
    # Get CO2 data for linear fit (last 70 points or all if fewer)
    if len(_co2_data) < 2:
        bioreactor.logger.warning("Not enough CO2 data for stabilization (need at least 2 points)")
        # Run with default parameters if no data
        pressurize_and_inject_co2(bioreactor, pressurize_duration, pause, co2_duration, elapsed)
        return
    
    # Get the last 70 points (or all if fewer)
    n_points = min(70, len(_co2_data))
    co2_values = np.array(list(_co2_data)[-n_points:])
    
    # Get corresponding time points (relative to start)
    # Note: time_data and co2_data should be aligned, but we'll use indices to be safe
    if _start_time is None:
        time_values = np.arange(len(co2_values))
    else:
        # Get time values corresponding to the CO2 data points
        # Since both are appended together, they should be aligned
        time_list = list(_time_data)
        if len(time_list) >= n_points:
            time_values = np.array([(t - _start_time) for t in time_list[-n_points:]])
        else:
            # Fallback: use indices if time data is shorter
            time_values = np.arange(len(co2_values))
    
    # Perform linear regression: y = slope * x + intercept
    # Using numpy's polyfit for linear fit (degree 1)
    if len(time_values) > 1 and len(co2_values) > 1 and len(time_values) == len(co2_values):
        
        # Linear fit: [slope, intercept]
        coeffs = np.polyfit(time_values, co2_values, 1)
        slope = coeffs[0]  # ppm per second
        
        bioreactor.logger.info(f"CO2 slope: {slope:.2f} ppm/s (from {len(co2_values)} points)")
        
        # Adjust CO2 duration based on slope
        if abs(slope) < 1e-6:  # Essentially zero (avoid floating point issues)
            # Slope is zero, don't change duration
            bioreactor.logger.info("CO2 slope is zero, keeping current durations")
        else:
            # Calculate adjustment: -slope/100 seconds
            adjustment = -slope / 100.0
            
            # Apply adjustment to CO2 duration
            new_co2_duration = co2_duration + adjustment
            
            # If CO2 duration would go to zero or negative, increase pressurize_duration instead
            if new_co2_duration <= 0:
                # Increase pressurize_duration by slope/100
                pressurize_adjustment = slope / 100.0
                current_pressurize_duration = max(0, current_pressurize_duration + pressurize_adjustment)
                # Update the reference if provided (for independent state per job)
                if pressurize_duration_ref is not None:
                    pressurize_duration_ref['value'] = current_pressurize_duration
                # Keep CO2 duration at zero
                co2_duration = 0.0
                _co2_duration = 0.0
                bioreactor.logger.info(f"CO2 duration at zero, increased pressurize_duration to {current_pressurize_duration:.2f}s")
            else:
                # Update CO2 duration
                co2_duration = new_co2_duration
                _co2_duration = co2_duration
                bioreactor.logger.info(f"Adjusted CO2 duration to {co2_duration:.3f}s (change: {adjustment:.3f}s)")
    else:
        bioreactor.logger.warning("Insufficient data for linear fit")
    
    # Add setpoint-based adjustments based on average CO2 vs setpoint
    if setpoint_ppm is not None:
        # Get average CO2 again (from last 15 points for consistency with earlier check)
        if len(_co2_data) >= 1:
            n_points_avg = min(15, len(_co2_data))
            co2_values_avg = np.array(list(_co2_data)[-n_points_avg:])
            avg_co2 = np.mean(co2_values_avg)
            signed_difference = avg_co2 - setpoint_ppm
            
            if signed_difference > 0:
                # CO2 is above setpoint: first reduce CO2 duration if > 0, then increase pressurize duration
                pressurize_adjustment = signed_difference * 1e-3
                
                if co2_duration > 0:
                    # First subtract adjustment from CO2 duration
                    old_co2_duration = co2_duration
                    co2_duration = max(0, co2_duration - pressurize_adjustment)
                    _co2_duration = co2_duration
                    
                    # If CO2 duration was reduced to zero, apply remaining adjustment to pressurize
                    if co2_duration == 0:
                        remaining_adjustment = pressurize_adjustment - old_co2_duration
                        if remaining_adjustment > 0:
                            current_pressurize_duration = max(0, current_pressurize_duration + remaining_adjustment)
                            if pressurize_duration_ref is not None:
                                pressurize_duration_ref['value'] = current_pressurize_duration
                            bioreactor.logger.info(f"CO2 above setpoint: reduced CO2 duration to 0, increased pressurize duration by {remaining_adjustment:.3f}s to {current_pressurize_duration:.3f}s")
                        else:
                            bioreactor.logger.info(f"CO2 above setpoint: reduced CO2 duration to 0 (1e-3 * {signed_difference:.1f} ppm)")
                    else:
                        bioreactor.logger.info(f"CO2 above setpoint: reduced CO2 duration by {pressurize_adjustment:.3f}s (1e-3 * {signed_difference:.1f} ppm) to {co2_duration:.3f}s")
                else:
                    # CO2 duration is already 0, increase pressurize duration
                    current_pressurize_duration = max(0, current_pressurize_duration + pressurize_adjustment)
                    # Update the reference if provided
                    if pressurize_duration_ref is not None:
                        pressurize_duration_ref['value'] = current_pressurize_duration
                    bioreactor.logger.info(f"CO2 above setpoint: increased pressurize duration by {pressurize_adjustment:.3f}s (1e-3 * {signed_difference:.1f} ppm) to {current_pressurize_duration:.3f}s")
            elif signed_difference < 0:
                # CO2 is below setpoint: first decrease pressurize duration if > 10, then increase CO2 duration
                if current_pressurize_duration > 10:
                    # Decrease pressurize duration using same factor (1e-3 * difference)
                    pressurize_adjustment = abs(signed_difference) * 1e-3
                    current_pressurize_duration = max(10, current_pressurize_duration - pressurize_adjustment)
                    # Update the reference if provided
                    if pressurize_duration_ref is not None:
                        pressurize_duration_ref['value'] = current_pressurize_duration
                    bioreactor.logger.info(f"CO2 below setpoint: decreased pressurize duration by {pressurize_adjustment:.3f}s (1e-3 * {abs(signed_difference):.1f} ppm) to {current_pressurize_duration:.3f}s")
                else:
                    # Pressurize duration is at or below 10, now increase CO2 injection duration
                    co2_adjustment = abs(signed_difference) * 1e-5
                    co2_duration = max(0, co2_duration + co2_adjustment)
                    _co2_duration = co2_duration
                    bioreactor.logger.info(f"CO2 below setpoint: pressurize duration at {current_pressurize_duration:.3f}s, increased CO2 injection duration by {co2_adjustment:.3f}s (1e-5 * {abs(signed_difference):.1f} ppm) to {co2_duration:.3f}s")
    
    # Run pressurize_and_inject_co2 with adjusted parameters
    pressurize_and_inject_co2(bioreactor, current_pressurize_duration, pause, co2_duration, elapsed)


def pressurize_only(bioreactor, duration_seconds, elapsed=None):
    """
    Pressurize by running pump_1 for specified duration.
    
    Args:
        bioreactor: Bioreactor instance
        duration_seconds: Duration to run pump_1 (in seconds)
        elapsed: Time elapsed since job started (optional)
    """
    if not bioreactor.is_component_initialized('relays'):
        bioreactor.logger.warning("Relays not initialized")
        return
    
    if not hasattr(bioreactor, 'relays') or 'pump_1' not in bioreactor.relays:
        bioreactor.logger.warning("pump_1 relay not found")
        return
    
    try:
        import lgpio
        
        relay_info = bioreactor.relays['pump_1']
        gpio_chip = relay_info['chip']
        relay_pin = relay_info['pin']
        
        bioreactor.logger.info(f"Pressurizing: pump_1 ON for {duration_seconds}s")
        lgpio.gpio_write(gpio_chip, relay_pin, 0)  # 0 = ON
        time.sleep(duration_seconds)
        lgpio.gpio_write(gpio_chip, relay_pin, 1)  # 1 = OFF
        bioreactor.logger.info("pump_1 turned OFF - Pressurization complete")
        
    except Exception as e:
        bioreactor.logger.error(f"Error during pressurization: {e}")
        # Try to turn off relay in case of error
        try:
            import lgpio
            gpio_chip = bioreactor.relays['pump_1']['chip']
            relay_pin = bioreactor.relays['pump_1']['pin']
            lgpio.gpio_write(gpio_chip, relay_pin, 1)  # Turn off
            bioreactor.logger.info("Emergency: pump_1 turned OFF")
        except:
            pass


def create_control_co2_setpoint_job(setpoint_ppm=1000, initial_delay=0, flush_multiplier=2.5e-4, inject_multiplier=2.5e-5, pause_tolerance_ppm=1000, resume_tolerance_ppm=2000):
    """
    Create a control_co2_setpoint function with a specific setpoint for use with bioreactor.run().
    
    The job uses hysteresis: pauses when average is within pause_tolerance_ppm, resumes when difference exceeds resume_tolerance_ppm.
    This allows the stabilize job to take control when close to setpoint.
    The setpoint can be updated via the text box in the plot window.
    
    Args:
        setpoint_ppm: Initial target CO2 level in ppm (default: 1000, can be updated via text box)
        initial_delay: Initial delay in seconds before first execution (default: 0)
        flush_multiplier: Multiplier for flush duration when CO2 is above setpoint (default: 2.5e-4)
        inject_multiplier: Multiplier for CO2 injection duration when CO2 is below setpoint (default: 2.5e-4)
        pause_tolerance_ppm: Tolerance around setpoint in ppm - job pauses when average is within this range (default: 1000)
        resume_tolerance_ppm: Tolerance around setpoint in ppm - job resumes when difference exceeds this (default: 2000)
        
    Returns:
        function: A function that can be used with bioreactor.run()
        
    Example:
        jobs = [
            (create_control_co2_setpoint_job(1000, initial_delay=30, flush_multiplier=5e-4, pause_tolerance_ppm=1000, resume_tolerance_ppm=2000), 180, True),  # Control CO2 every 3 minutes, starting 30s after other jobs
        ]
    """
    global _setpoint_ref, _co2_setpoint
    _first_call = {'value': True}
    _is_paused = {'value': False}  # Track pause state for hysteresis
    _setpoint_ref = {'value': setpoint_ppm}  # Store setpoint reference for text box updates
    _co2_setpoint = setpoint_ppm  # Update global setpoint for text box initialization
    
    def control_co2_setpoint_job(bioreactor, elapsed=None):
        # On first call, wait for initial_delay if specified
        if _first_call['value'] and initial_delay > 0:
            bioreactor.logger.info(f"Waiting {initial_delay}s before first CO2 setpoint control...")
            time.sleep(initial_delay)
            _first_call['value'] = False
        # Use setpoint from reference (can be updated via text box)
        current_setpoint = _setpoint_ref['value']
        control_co2_setpoint(bioreactor, setpoint_ppm=current_setpoint, flush_multiplier=flush_multiplier, 
                           inject_multiplier=inject_multiplier, pause_tolerance_ppm=pause_tolerance_ppm,
                           resume_tolerance_ppm=resume_tolerance_ppm, is_paused_ref=_is_paused, elapsed=elapsed)
    
    return control_co2_setpoint_job


def control_co2_setpoint(bioreactor, setpoint_ppm=1000, flush_multiplier=2.5e-4, inject_multiplier=2.5e-4, pause_tolerance_ppm=1000, resume_tolerance_ppm=2000, is_paused_ref=None, elapsed=None):
    """
    Control CO2 level based on setpoint using average of last 15 measurements.
    
    Uses hysteresis: pauses when average is within pause_tolerance_ppm, resumes when difference exceeds resume_tolerance_ppm.
    If CO2 is below setpoint: inject CO2 for inject_multiplier * difference seconds
    If CO2 is above setpoint: flush tank for flush_multiplier * difference seconds, then pressurize for same duration
    
    Args:
        bioreactor: Bioreactor instance
        setpoint_ppm: Target CO2 level in ppm (default: 1000)
        flush_multiplier: Multiplier for flush duration when CO2 is above setpoint (default: 2.5e-4)
        inject_multiplier: Multiplier for CO2 injection duration when CO2 is below setpoint (default: 2.5e-4)
        pause_tolerance_ppm: Tolerance around setpoint in ppm - job pauses when average is within this range (default: 1000)
        resume_tolerance_ppm: Tolerance around setpoint in ppm - job resumes when difference exceeds this (default: 2000)
        is_paused_ref: Reference to track pause state for hysteresis (optional)
        elapsed: Time elapsed since job started (optional)
    """
    global _co2_data
    
    if not bioreactor.is_component_initialized('relays'):
        bioreactor.logger.warning("Relays not initialized")
        return
    
    # Get CO2 data (last 15 points or all if fewer)
    if len(_co2_data) < 1:
        bioreactor.logger.warning("No CO2 data available for setpoint control")
        return
    
    # Get the last 15 points (or all if fewer)
    n_points = min(15, len(_co2_data))
    co2_values = np.array(list(_co2_data)[-n_points:])
    
    # Calculate average
    avg_co2 = np.mean(co2_values)
    difference = avg_co2 - setpoint_ppm
    abs_difference = abs(difference)
    
    bioreactor.logger.info(f"CO2 setpoint control: average={avg_co2:.1f} ppm, setpoint={setpoint_ppm} ppm, difference={difference:.1f} ppm")
    
    # Hysteresis logic: pause when within pause_tolerance, resume when outside resume_tolerance
    if is_paused_ref is not None:
        is_paused = is_paused_ref['value']
    else:
        is_paused = False
    
    if is_paused:
        # Currently paused - check if we should resume (difference > resume_tolerance)
        if abs_difference > resume_tolerance_ppm:
            is_paused = False
            if is_paused_ref is not None:
                is_paused_ref['value'] = False
            bioreactor.logger.info(f"CO2 setpoint control resumed: average ({avg_co2:.1f} ppm) is {abs_difference:.1f} ppm away from setpoint, exceeds resume threshold ({resume_tolerance_ppm} ppm)")
        else:
            bioreactor.logger.info(f"CO2 setpoint control paused: average ({avg_co2:.1f} ppm) is {abs_difference:.1f} ppm away from setpoint, within resume threshold ({resume_tolerance_ppm} ppm), stabilize job is active")
            return
    else:
        # Currently active - check if we should pause (difference <= pause_tolerance)
        if abs_difference <= pause_tolerance_ppm:
            is_paused = True
            if is_paused_ref is not None:
                is_paused_ref['value'] = True
            bioreactor.logger.info(f"CO2 setpoint control paused: average ({avg_co2:.1f} ppm) is within {pause_tolerance_ppm} ppm of setpoint ({setpoint_ppm} ppm), stabilize job is active")
            return
    
    if difference < 0:
        # Below setpoint: inject CO2
        duration = abs(difference) * inject_multiplier
        bioreactor.logger.info(f"CO2 below setpoint, injecting CO2 for {duration:.3f} seconds (multiplier: {inject_multiplier})")
        inject_co2_delayed(bioreactor, delay_seconds=0, injection_duration_seconds=duration, elapsed=elapsed)
    elif difference > 0:
        # Above setpoint: flush tank, then pressurize
        duration = abs(difference) * flush_multiplier
        bioreactor.logger.info(f"CO2 above setpoint, flushing tank for {duration:.3f} seconds, then pressurizing for {duration:.3f} seconds (flush multiplier: {flush_multiplier})")
        flush_tank(bioreactor, duration_seconds=duration, elapsed=elapsed)
        pressurize_only(bioreactor, duration_seconds=duration, elapsed=elapsed)
    else:
        # At setpoint (within floating point precision)
        bioreactor.logger.info("CO2 at setpoint, no action needed")


def _update_co2_setpoint(text):
    """Handler for CO2 setpoint text box - updates global value in real time."""
    global _co2_setpoint, _co2_setpoint_textbox, _setpoint_ref
    try:
        new_value = float(text)
        if new_value > 0:
            _co2_setpoint = new_value
            # Update the reference if it exists (for control job)
            if _setpoint_ref is not None:
                _setpoint_ref['value'] = new_value
            logger.info(f"CO2 setpoint updated to {_co2_setpoint} ppm")
        else:
            logger.warning("CO2 setpoint must be positive")
            # Reset to previous value
            if _co2_setpoint_textbox:
                _co2_setpoint_textbox.set_val(str(_co2_setpoint))
    except ValueError:
        logger.warning(f"Invalid CO2 setpoint value: {text}")
        # Reset to previous value
        if _co2_setpoint_textbox:
            _co2_setpoint_textbox.set_val(str(_co2_setpoint))


def _animate(frame):
    """
    Animation function that runs in the main thread.
    Reads sensor data from queue and updates plot lines.
    """
    global _co2_data, _o2_data, _time_data, _start_time, _ax1, _ax2, _co2_line, _o2_line
    
    # Process all available sensor readings from queue (non-blocking)
    while True:
        try:
            data = _sensor_queue.get_nowait()
            co2_value, o2_value, current_time = data
            
            if _start_time is None:
                _start_time = current_time
            
            if co2_value is not None:
                _co2_data.append(co2_value)
            if o2_value is not None:
                _o2_data.append(o2_value)
            _time_data.append(current_time)
        except queue.Empty:
            break
    
    # Update plots if we have data
    if len(_time_data) > 0 and _ax1 is not None and _ax2 is not None:
        # Convert time to relative seconds
        time_relative = [(t - _start_time) for t in _time_data]
        
        # Update CO2 plot line (don't clear, just update data)
        if len(_co2_data) > 0:
            co2_time = time_relative[-len(_co2_data):]
            if _co2_line is None:
                _co2_line, = _ax1.plot(co2_time, list(_co2_data), 'b-', linewidth=2, label='CO2')
                _ax1.legend()
            else:
                _co2_line.set_data(co2_time, list(_co2_data))
                # Keep fixed y-limits instead of autoscaling
                _ax1.set_xlim(max(0, min(co2_time) - 10), max(co2_time) + 10)
        
        # Update O2 plot line (don't clear, just update data)
        if len(_o2_data) > 0:
            o2_time = time_relative[-len(_o2_data):]
            if _o2_line is None:
                _o2_line, = _ax2.plot(o2_time, list(_o2_data), 'r-', linewidth=2, label='O2')
                _ax2.legend()
            else:
                _o2_line.set_data(o2_time, list(_o2_data))
                # Keep fixed y-limits instead of autoscaling
                _ax2.set_xlim(max(0, min(o2_time) - 10), max(o2_time) + 10)
    
    return _co2_line, _o2_line


def init_plot_window(bioreactor):
    """
    Initialize the plot window in the main thread.
    This MUST be called from the main thread before starting jobs.
    
    Args:
        bioreactor: Bioreactor instance
    """
    global _plot_initialized, _fig, _ax1, _ax2, _co2_duration, _co2_setpoint, _co2_setpoint_textbox, _bioreactor_ref, _anim, _start_time
    
    if _plot_initialized:
        return  # Already initialized
    
    try:
        _fig, (_ax1, _ax2) = plt.subplots(2, 1, figsize=(12, 8))
        _fig.suptitle('Live CO2 and O2 Monitoring')
        
        # CO2 subplot (top)
        _ax1.set_title('CO2 Concentration')
        _ax1.set_ylabel('CO2 (ppm)')
        _ax1.set_ylim(300, 100000)  # Fixed scale
        _ax1.grid(True, alpha=0.3)
        _ax1.legend()
        
        # O2 subplot (bottom)
        _ax2.set_title('O2 Concentration')
        _ax2.set_ylabel('O2 (%)')
        _ax2.set_xlabel('Time (seconds)')
        _ax2.set_ylim(15, 25)  # Fixed scale
        _ax2.grid(True, alpha=0.3)
        _ax2.legend()
        
        # Store bioreactor reference for button callbacks
        _bioreactor_ref = bioreactor
        
        # Add CO2 setpoint text box at the bottom (for CO2 control job)
        global _co2_setpoint, _co2_setpoint_textbox
        text_box_ax = plt.axes([0.15, 0.02, 0.2, 0.04])
        _co2_setpoint_textbox = TextBox(text_box_ax, 'CO2 Setpoint (ppm): ', initial=str(_co2_setpoint))
        _co2_setpoint_textbox.on_submit(_update_co2_setpoint)
        
        plt.subplots_adjust(bottom=0.1)  # Make room for text box
        
        plt.ion()  # Turn on interactive mode
        plt.show(block=False)
        
        # Start animation (runs in main thread)
        # Store animation globally to prevent garbage collection
        _anim = animation.FuncAnimation(_fig, _animate, interval=50, blit=False, cache_frame_data=False, repeat=True)
        
        # Force initial draw
        plt.draw()
        plt.pause(0.01)
        
        _start_time = time.time()
        _plot_initialized = True
        bioreactor.logger.info("Plot initialized for sensor monitoring with CO2 setpoint control")
    except Exception as e:
        bioreactor.logger.error(f"Error initializing plot: {e}")
        raise


def read_sensors_and_plot(bioreactor, elapsed=None):
    """
    Read CO2 and O2 sensors and put data in queue for plot updates.
    Plot updates happen in main thread via animation framework.
    Designed to run periodically (e.g., every 1-5 seconds).
    
    Args:
        bioreactor: Bioreactor instance
        elapsed: Time elapsed since job started (optional, provided by run())
    """
    global _plot_initialized
    
    # Plot should be initialized via init_plot_window() from main thread
    # If not initialized, log warning but continue (plot will just not update)
    if not _plot_initialized:
        bioreactor.logger.warning("Plot not initialized. Call init_plot_window(bioreactor) from main thread before starting jobs.")
        return
    
    try:
        co2_value = None
        o2_value = None
        
        # Read O2 sensor if available
        if bioreactor.is_component_initialized('o2_sensor') and hasattr(bioreactor, 'o2_sensor'):
            try:
                from atlas_i2c import commands
                o2_reading = bioreactor.o2_sensor.query(commands.READ)
                o2_value = float(o2_reading.data.decode().replace('%', '').strip())
            except Exception as e:
                bioreactor.logger.warning(f"Error reading O2 sensor: {e}")
        
        # Read CO2 sensor from serial if available
        if bioreactor.is_component_initialized('co2_sensor') and hasattr(bioreactor, 'co2_sensor'):
            try:
                # CO2 sensor is now a serial.Serial object
                bioreactor.co2_sensor.write(b"\xFE\x44\x00\x08\x02\x9F\x25")
                time.sleep(0.1)
                resp = bioreactor.co2_sensor.read(7)
                if len(resp) >= 5:
                    high = resp[3]
                    low = resp[4]
                    co2_value = 10 * ((high * 256) + low)
            except Exception as e:
                bioreactor.logger.warning(f"Error reading CO2 sensor: {e}")
        
        # Put sensor data in queue (non-blocking, thread-safe)
        current_time = time.time()
        try:
            _sensor_queue.put_nowait((co2_value, o2_value, current_time))
        except queue.Full:
            bioreactor.logger.warning("Sensor queue full, dropping reading")
        
        # Log readings
        readings = []
        if co2_value is not None:
            readings.append(f"CO2: {co2_value:.1f} ppm")
        if o2_value is not None:
            readings.append(f"O2: {o2_value:.1f}%")
        
        if readings:
            bioreactor.logger.info(", ".join(readings))
        
        # Write to CSV if available
        if hasattr(bioreactor, 'writer') and hasattr(bioreactor, 'fieldnames'):
            try:
                # Use sensor labels from config if available, otherwise use generic names
                row = {'time': current_time}
                
                # Get sensor label keys from config if available
                if hasattr(bioreactor.cfg, 'SENSOR_LABELS'):
                    co2_key = None
                    o2_key = None
                    for key, label in bioreactor.cfg.SENSOR_LABELS.items():
                        if 'co2' in key.lower():
                            co2_key = label
                        if 'o2' in key.lower():
                            o2_key = label
                    
                    if co2_value is not None:
                        row[co2_key if co2_key else 'CO2_ppm'] = co2_value
                    if o2_value is not None:
                        row[o2_key if o2_key else 'O2_percent'] = o2_value
                else:
                    # Use generic names if no config labels
                    if co2_value is not None:
                        row['CO2_ppm'] = co2_value
                    if o2_value is not None:
                        row['O2_percent'] = o2_value
                
                # Only write if row has data and matches fieldnames
                if row and all(k in bioreactor.fieldnames for k in row.keys()):
                    bioreactor.writer.writerow(row)
                    if hasattr(bioreactor, 'out_file'):
                        bioreactor.out_file.flush()
            except Exception as e:
                bioreactor.logger.warning(f"Error writing to CSV: {e}")
                
    except Exception as e:
        bioreactor.logger.error(f"Error in read_sensors_and_plot: {e}")

