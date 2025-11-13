from typing import Union

class Config:
    # GPIO pins
    PELTIER_PWM_PIN = 12
    PELTIER_DIR_PIN = 16
    PELTIER_PWM_FREQ = 1000

    # BCM Pin Mapping
    BCM_MAP: dict[int, int] = {
        7: 4, 11: 17, 12: 18, 13: 27, 15: 22, 16: 23, 18: 24, 22: 25,
        29: 5, 31: 6, 32: 12, 33: 13, 35: 19, 36: 16, 37: 26, 38: 20, 40: 21
    }
    
    # LED Configuration
    LED_PIN: int = 37
    LED_MODE: str = 'bcm'

    # Stirrer Configuration
    STIRRER_PIN: int = 19
    STIRRER_SPEED: int = 1000
    DUTY_CYCLE: int = 55

    # Relay Configuration
    RELAY_PINS: list[int] = [9,5,6,13]  # GPIO pins for relays
    RELAY_NAMES: list[str] = ['relay_1', 'relay_2', 'relay_3', 'relay_4']  # Names for each relay

    # Ring Light Configuration
    RING_LIGHT_COUNT: int = 32
    RING_LIGHT_BRIGHTNESS: float = 0.2

    # ADC Configuration
    ADC_1_ADDRESS: int = 0x48
    ADC_2_ADDRESS: int = 0x49
    ADC_1_REF_VOLTAGE: float = 4.7
    ADC_2_REF_VOLTAGE: float = 4.7
    ADC_1_135_CHANNELS: list[int] = [0,1,2,3]
    ADC_1_180_CHANNELS: list[int] = [4,5,6,7]
    ADC_2_REF_CHANNELS: list[int] = [0,1,2,3]
    ADC_1_IO_TEMP_CHANNELS: list[int] = []
    ADC_2_IO_TEMP_CHANNELS: list[int] = [4, 5]
    ADC_1_PHOTODIODE_CHANNELS: list[int] = [0,1,2,3,4,5,6,7]
    ADC_2_PHOTODIODE_CHANNELS: list[int] = [0,1,2,3]

    # Temperature Sensor Arrays
    VIAL_TEMP_SENSOR_ORDER: list[int] = [0, 3, 2, 1]

    # Logging Configuration
    LOG_LEVEL: str = 'INFO'
    LOG_FORMAT: str = '%(asctime)s - %(levelname)s - %(message)s'

    # Pump Configuration
    PUMPS: dict[str, dict[str, Union[str, float, dict]]] = {
        'A_in':  {
            'serial': '00473498',
            'direction': 'forward',  # user-set: 'forward' or 'reverse'
            'forward': {'gradient': 0.0000001, 'intercept': 0.0},
        },
        'A_out': {
            'serial': '00473497',
            'direction': 'forward',
            'forward': {'gradient': 0.0000001, 'intercept': 0.0},
        },
        'B_in':  {
            'serial': '00473504',
            'direction': 'forward',
            'forward': {'gradient': 0.0000001, 'intercept': 0.0},
        },
        'B_out': {
            'serial': '00473508',
            'direction': 'forward',
            'forward': {'gradient': 0.0000001, 'intercept': 0.0},
        },
        'C_in':  {
            'serial': '00473510',
            'direction': 'forward',
            'forward': {'gradient': 0.0000001, 'intercept': 0.0},
        },
        'C_out': {
            'serial': '00473517',
            'direction': 'forward',
            'forward': {'gradient': 0.0000001, 'intercept': 0.0},
        },
        'D_in':  {
            'serial': '00473491',
            'direction': 'forward',
            'forward': {'gradient': 0.0000001, 'intercept': 0.0},
        },
        'D_out': {
            'serial': '00473552',
            'direction': 'forward',
            'forward': {'gradient': 0.0000001, 'intercept': 0.0},
        },
    }

    # Initialization Components
    INIT_COMPONENTS: dict[str, bool] = {
        'leds': True,
        'pumps': True,
        'ring_light': True,
        'optical_density': True, # includes io_temp_1 and io_temp_2
        'temp': True,
        'ambient': True,  # Adafruit PCT2075 temperature sensor
        'peltier': True,
        'relays': True,
        'stirrer': True
    }

    LOG_FILE: str = 'bioreactor.log'

    SENSOR_LABELS: dict = {
        'photodiode_1': 'vial_A_135_degree',
        'photodiode_2': 'vial_B_135_degree',
        'photodiode_3': 'vial_C_135_degree',
        'photodiode_4': 'vial_D_135_degree',
        'photodiode_5': 'vial_A_180_degree',
        'photodiode_6': 'vial_B_180_degree',
        'photodiode_7': 'vial_C_180_degree',
        'photodiode_8': 'vial_D_180_degree',
        'photodiode_9': 'vial_A_reference',
        'photodiode_10': 'vial_B_reference',
        'photodiode_11': 'vial_C_reference',
        'photodiode_12': 'vial_D_reference',
        'io_temp_1': 'io_temp_in',
        'io_temp_2': 'io_temp_out',
        'vial_temp_1': 'vial_A_temp',
        'vial_temp_2': 'vial_B_temp',
        'vial_temp_3': 'vial_C_temp',
        'vial_temp_4': 'vial_D_temp',
        'ambient_temp': 'ambient_temp',
        'peltier_current': 'peltier_current',
    }
