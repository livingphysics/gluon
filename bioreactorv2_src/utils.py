import csv
import numpy as np
from .config import Config as cfg
import time

# Standalone utility functions

def measure_and_write_sensor_data(bioreactor, elapsed):
    """
    Get sensor measurements and log them to a CSV file.
    Args:
        bioreactor: Bioreactor object with .writer, .get_photodiodes(), .get_io_temp(), .get_vial_temp(), .get_ambient_temp(), .get_peltier_curr()
        elapsed: float, elapsed time in seconds
    """
    photodiodes = bioreactor.get_photodiodes()
    io_temps = bioreactor.get_io_temp()
    vial_temps = bioreactor.get_vial_temp()
    ambient_temp = bioreactor.get_ambient_temp()
    peltier_current = bioreactor.get_peltier_curr()

    # Pad lists to ensure correct length
    photodiodes += [float('nan')] * (12 - len(photodiodes))
    io_temps += [float('nan')] * (2 - len(io_temps))
    vial_temps += [float('nan')] * (4 - len(vial_temps))

    # Use user-friendly sensor names from config.SENSOR_LABELS
    data_row = {
        'time': elapsed,
        cfg.SENSOR_LABELS['photodiode_1']: photodiodes[0],
        cfg.SENSOR_LABELS['photodiode_2']: photodiodes[1],
        cfg.SENSOR_LABELS['photodiode_3']: photodiodes[2],
        cfg.SENSOR_LABELS['photodiode_4']: photodiodes[3],
        cfg.SENSOR_LABELS['photodiode_5']: photodiodes[4],
        cfg.SENSOR_LABELS['photodiode_6']: photodiodes[5],
        cfg.SENSOR_LABELS['photodiode_7']: photodiodes[6],
        cfg.SENSOR_LABELS['photodiode_8']: photodiodes[7],
        cfg.SENSOR_LABELS['photodiode_9']: photodiodes[8],
        cfg.SENSOR_LABELS['photodiode_10']: photodiodes[9],
        cfg.SENSOR_LABELS['photodiode_11']: photodiodes[10],
        cfg.SENSOR_LABELS['photodiode_12']: photodiodes[11],
        cfg.SENSOR_LABELS['io_temp_1']: io_temps[0],
        cfg.SENSOR_LABELS['io_temp_2']: io_temps[1],
        cfg.SENSOR_LABELS['vial_temp_1']: vial_temps[0],
        cfg.SENSOR_LABELS['vial_temp_2']: vial_temps[1],
        cfg.SENSOR_LABELS['vial_temp_3']: vial_temps[2],
        cfg.SENSOR_LABELS['vial_temp_4']: vial_temps[3],
        cfg.SENSOR_LABELS['ambient_temp']: ambient_temp,
        cfg.SENSOR_LABELS['peltier_current']: peltier_current
    }

    bioreactor.writer.writerow(data_row)
    bioreactor.out_file.flush()
    if hasattr(bioreactor, 'logger'):
        bioreactor.logger.info(f"Wrote sensor data: {data_row}")
        
    return data_row

def pid_controller(bioreactor, setpoint, current_temp=None, kp=10.0, ki=1.0, kd=0.0, dt=1.0, elapsed=None):
    """
    PID loop to maintain reactor temperature at `setpoint`.
    Args:
        bioreactor: Bioreactor instance
        setpoint: Desired temperature (°C)
        current_temp: Measured temp (°C). If None, reads from first vial sensor.
        kp, ki, kd: PID gains
        dt: Time elapsed since last call (s)
    """
    logger = getattr(bioreactor, 'logger', None)

    if current_temp is None:
        temps = bioreactor.get_vial_temp()
        current_temp = temps[3]
    error = setpoint - current_temp
    
    # Only update integral if error is not NaN
    if not np.isnan(error):
        bioreactor._temp_integral += error * dt
        derivative = (error - bioreactor._temp_last_error) / dt if dt > 0 else 0.0
        output = kp * error + ki * bioreactor._temp_integral + kd * derivative
    else:
        # If error is NaN, skip integral update and set output to NaN
        derivative = 0.0
        output = float('nan')

    if not np.isnan(output):
        duty = max(0, min(100, int(abs(output))))
        forward = (output >= 0)
        if hasattr(bioreactor, 'change_peltier'):
            bioreactor.change_peltier(duty, forward)
        bioreactor._temp_last_error = error

        if logger:
            logger.info(f"PID controller: setpoint={setpoint}, current_temp={current_temp}, output={output}, duty={duty}, forward={forward}")
    else:
        # Skip peltier update if output is NaN
        if logger:
            logger.warning(f"PID controller: NaN output detected, skipping peltier update. setpoint={setpoint}, current_temp={current_temp}")

def balanced_flow(bioreactor, pump_name, ml_per_sec, elapsed=None):
    """
    For a given pump, set its flow and automatically set the converse pump
    to the same volumetric rate in the opposite direction.
    Args:
        bioreactor: Bioreactor instance
        pump_name: e.g. 'tube_1_in' or 'tube_1_out'
        ml_per_sec: Desired flow rate in ml/sec (>= 0)
    """
    logger = getattr(bioreactor, 'logger', None)
    if not bioreactor._initialized.get('pumps'):
        return
    
    if pump_name.endswith('_in'):
        converse = pump_name[:-3] + 'out'
    elif pump_name.endswith('_out'):
        converse = pump_name[:-4] + 'in'
    else:
        raise ValueError("Pump name must end with '_in' or '_out'")
    
    bioreactor.change_pump(pump_name, ml_per_sec)
    bioreactor.change_pump(converse, ml_per_sec)

    if logger:
        logger.info(f"Balanced flow: {pump_name} and {converse} set to {ml_per_sec} ml/sec")

def compensated_flow(bioreactor, pump_name, ml_per_sec, duration, dt, elapsed=None):
    """
    For a given pump, set its flow and automatically set the converse pump
    to the same volumetric rate in the opposite direction.
    Args:
        bioreactor: Bioreactor instance
        pump_name: e.g. 'tube_1_in' or 'tube_1_out'
        ml_per_sec: Desired flow rate in ml/sec (>= 0)
    """
    logger = getattr(bioreactor, 'logger', None)
    if not bioreactor._initialized.get('pumps'):
        return
    
    if pump_name in ['A', 'B', 'C', 'D']:
        in_names = [pump_name + '_in']
        out_names = [pump_name + '_out']
    elif pump_name.endswith('_in'):
        in_names = [pump_name]
        out_names = [pump_name[:-3] + '_out']
    elif pump_name.endswith('_out'):
        in_names = [pump_name[:-4] + '_in']
        out_names = [pump_name]
    elif pump_name.startswith('All'):
        in_names = ['A_in', 'B_in', 'C_in', 'D_in']
        out_names = ['A_out', 'B_out', 'C_out', 'D_out']
    else:
        raise ValueError("Pump name must be A, B, C, D, end with '_in' or '_out', or contain 'All'")
    
    for in_name, out_name in zip(in_names, out_names):
        bioreactor.change_pump(in_name, ml_per_sec)
    time.sleep(duration)    
    for in_name, out_name in zip(in_names, out_names):
        bioreactor.change_pump(in_name, 0)
    
    # Turn on all relays during the flow operation
    if bioreactor._initialized.get('relays'):
        bioreactor.change_all_relays(True)
    
    time.sleep(dt-2*duration)
    
    # Turn off all relays after the flow operation
    if bioreactor._initialized.get('relays'):
        bioreactor.change_all_relays(False)
    
    for in_name, out_name in zip(in_names, out_names):
        bioreactor.change_pump(out_name, ml_per_sec*1.1)
    time.sleep(duration)
    for in_name, out_name in zip(in_names, out_names):
        bioreactor.change_pump(out_name, 0)
        
    if logger:
        for in_name, out_name in zip(in_names, out_names):
            logger.info(f"Compensated flow: {in_name} and {out_name} set to {ml_per_sec} ml/sec")

# --- Turbidostat/OD Control Utilities ---

class ExtendedKalmanFilter:
    """
    Extended Kalman Filter for growth rate estimation in a turbidostat.
    """
    def __init__(
        self,
        initial_biomass: float,
        initial_growth_rate: float,
        process_noise_biomass: float = 1e-6,
        process_noise_growth_rate: float = 1e-7,
        measurement_noise: float = 0.01,
        dt: float = 1.0
    ):
        self.x = np.array([initial_biomass, initial_growth_rate])
        self.P = np.array([[0.1, 0], [0, 0.1]])
        self.Q = np.array([
            [process_noise_biomass, 0],
            [0, process_noise_growth_rate]
        ])
        self.R = measurement_noise
        self.dt = dt / 3600.0
        self.biomass_history = [initial_biomass]
        self.growth_rate_history = [initial_growth_rate]
        self.time_history = [0.0]
        self.measurement_history = [initial_biomass]
        self.total_time = 0.0

    def predict(self, flow_rate: float) -> None:
        x = self.x[0]
        mu = self.x[1]
        x_next = x + (mu * x - flow_rate * x) * self.dt
        mu_next = mu
        self.x = np.array([x_next, mu_next])
        F = np.array([
            [1 + (mu - flow_rate) * self.dt, x * self.dt],
            [0, 1]
        ])
        self.P = F @ self.P @ F.T + self.Q
        self.total_time += self.dt * 3600.0

    def update(self, measurement: float) -> None:
        H = np.array([[1.0, 0.0]])
        y = measurement - self.x[0]
        S = H @ self.P @ H.T + self.R
        K = self.P @ H.T / S
        self.x = self.x + K * y
        I = np.eye(2)
        self.P = (I - K @ H) @ self.P
        self.biomass_history.append(self.x[0])
        self.growth_rate_history.append(self.x[1])
        self.time_history.append(self.total_time)
        self.measurement_history.append(measurement)

    def get_state(self):
        return self.x[0], self.x[1]

    def plot_history(self):
        import matplotlib.pyplot as plt
        fig, axes = plt.subplots(2, 1, figsize=(10, 8))
        ax1 = axes[0]  # type: ignore
        ax2 = axes[1]  # type: ignore
        time_hours = np.array(self.time_history) / 3600.0
        ax1.plot(time_hours, self.biomass_history, 'b-', label='Estimated Biomass')
        ax1.scatter(time_hours, self.measurement_history, c='r', marker='.', label='Measurements')
        ax1.set_ylabel('Optical Density (OD)')
        ax1.set_title('Estimated Biomass vs Measurements')
        ax1.grid(True)
        ax1.legend()
        ax2.plot(time_hours, self.growth_rate_history, 'g-', label='Estimated Growth Rate')
        ax2.set_xlabel('Time (hours)')
        ax2.set_ylabel('Growth Rate (h^-1)')
        ax2.set_title('Estimated Growth Rate')
        ax2.grid(True)
        ax2.legend()
        plt.tight_layout()
        plt.savefig('ekf_estimation.png')
        plt.show()


def turbidostat_od_controller(
    bioreactor,
    ekf,
    measure_od_func,
    pump_name,
    target_od,
    control_gain,
    flow_rate_max_ml_s,
    dead_zone,
    culture_volume_ml,
    state,
    elapsed=None
):
    """
    OD control logic for turbidostat mode. Call this in a job function, passing a state dict.
    The state dict must have keys 'flow_rate_ml_s' and 'dilution_rate_h'.
    """
    od = measure_od_func(bioreactor)
    ekf.predict(state['dilution_rate_h'])
    ekf.update(od)
    est_od, est_growth_rate = ekf.get_state()
    error = od - target_od
    if abs(error) > dead_zone:
        if error > 0:
            desired_dilution_rate_h = est_growth_rate + control_gain * error
            new_flow_rate_ml_s = (desired_dilution_rate_h * culture_volume_ml) / 3600
            state['flow_rate_ml_s'] = min(max(0, new_flow_rate_ml_s), flow_rate_max_ml_s)
        else:
            reduction_factor = 1.0 - control_gain * abs(error)
            state['flow_rate_ml_s'] = max(0, state['flow_rate_ml_s'] * reduction_factor)
        state['dilution_rate_h'] = (state['flow_rate_ml_s'] * 3600) / culture_volume_ml
        bioreactor.balanced_flow(pump_name, state['flow_rate_ml_s'])

