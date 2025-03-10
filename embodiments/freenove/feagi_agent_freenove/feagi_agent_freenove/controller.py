import sys
import cv2
import time
import asyncio
import requests
import threading
import traceback
import RPi.GPIO as GPIO
from time import sleep
from collections import deque
from datetime import datetime
from feagi_agent_freenove.Led import *
from feagi_agent_freenove.ADC import *
from feagi_agent import retina as retina
from feagi_agent import sensors as sensors
from feagi_agent import pns_gateway as pns
from feagi_agent import actuators as actuators
from feagi_agent import feagi_interface as FEAGI
from feagi_agent_freenove.PCA9685 import PCA9685
from feagi_agent_freenove.version import __version__

ir_data = deque()
ultrasonic_data = deque()
feagi_dict = deque()
feagi_settings = dict()


def window_average(sequence):
    return sum(sequence) // len(sequence)


class LED:
    def __init__(self):
        self.led = Led()

    def LED_on(self, led_ID, Red_Intensity, Blue_Intensity, Green_intensity):
        """
        Parameters
        ----------
        led_ID: This is the ID of leds. It can be from 1 to 8
        Red_Intensity: 1 to 255, from dimmest to brightest
        Blue_Intensity: 1 to 255, from dimmest to brightest
        Green_intensity: 1 to 255, from dimmest to brightest
        -------
        """
        try:
            self.led.ledIndex(led_ID, Red_Intensity, Blue_Intensity, Green_intensity)
        except KeyboardInterrupt:
            self.led.colorWipe(led.strip, Color(0, 0, 0))  ##This is to turn all leds off/

    def test_led(self):
        """
        This is to test all leds and do several different leds.
        """
        try:
            self.led.ledIndex(0x01, 255, 0, 0)  # Red
            self.led.ledIndex(0x02, 255, 125, 0)  # orange
            self.led.ledIndex(0x04, 255, 255, 0)  # yellow
            self.led.ledIndex(0x08, 0, 255, 0)  # green
            self.led.ledIndex(0x10, 0, 255, 255)  # cyan-blue
            self.led.ledIndex(0x20, 0, 0, 255)  # blue
            self.led.ledIndex(0x40, 128, 0, 128)  # purple
            self.led.ledIndex(0x80, 255, 255, 255)  # white'''
            print("The LED has been lit, the color is red orange yellow green cyan-blue blue white")
            # time.sleep(3)  # wait 3s
            self.led.colorWipe("", Color(0, 0, 0))  # turn off the light
            print("\nEnd of program")
        except KeyboardInterrupt:
            self.led.colorWipe("", Color(0, 0, 0))  # turn off the light
            print("\nEnd of program")

    def leds_off(self):
        self.led.colorWipe("", Color(0, 0, 0))  # This is to turn all leds off/


class Servo:
    """
    Functions: head_UP_DOWN and head_RIGHT_LEFT only. Other functions are just a support and defined system for Servo
    class to work with functions.
    """

    def __init__(self):
        self.PwmServo = PCA9685(0x40, debug=True)
        self.PwmServo.setPWMFreq(50)
        self.device_position = float()
        self.servo_ranges = {i: [78, 160] for i in range(13)}

    def setServoPwm(self, channel, angle, error=10):
        angle = float(angle)
        if channel == '0':
            self.PwmServo.setServoPulse(8, 2500 - float((angle + error) / 0.09))
        elif channel == '1':
            self.PwmServo.setServoPulse(9, 500 + float((angle + error) / 0.09))
        elif channel == '2':
            self.PwmServo.setServoPulse(10, 500 + float((angle + error) / 0.09))
        elif channel == '3':
            self.PwmServo.setServoPulse(11, 500 + float((angle + error) / 0.09))
        elif channel == '4':
            self.PwmServo.setServoPulse(12, 500 + float((angle + error) / 0.09))
        elif channel == '5':
            self.PwmServo.setServoPulse(13, 500 + float((angle + error) / 0.09))
        elif channel == '6':
            self.PwmServo.setServoPulse(14, 500 + float((angle + error) / 0.09))
        elif channel == '7':
            self.PwmServo.setServoPulse(15, 500 + float((angle + error) / 0.09))

    def set_default_position(self, runtime_data):
        try:
            # Setting the initial position for the servo
            servo_0_initial_position = 90
            runtime_data['servo_status'][0] = servo_0_initial_position
            self.setServoPwm(str(0), runtime_data['servo_status'][0])
            print("Servo 0 was moved to its initial position")

            servo_1_initial_position = 90
            runtime_data['servo_status'][1] = servo_1_initial_position
            self.setServoPwm(str(1), runtime_data['servo_status'][0])
        except Exception as e:
            print("Error while setting initial position for the servo:", e)

    def move(self, feagi_device_id, power, capabilities, feagi_settings, runtime_data):
        try:
            if feagi_device_id > 2 * capabilities['servo']['count']:
                print("Warning! Number of servo channels from FEAGI exceed available Motor count!")
            # Translate feagi_motor_id to motor backward and forward motion to individual motors
            device_index = feagi_device_id // 2
            if feagi_device_id % 2 == 1:
                power *= 1
            else:
                power *= -1
            if device_index not in runtime_data['servo_status']:
                runtime_data['servo_status'][device_index] = device_index

            device_current_position = runtime_data['servo_status'][device_index]
            self.device_position = float((power * feagi_settings['feagi_burst_speed'] /
                                          capabilities["servo"][
                                              "power_amount"]) + device_current_position)

            self.device_position = self.keep_boundaries(device_id=device_index,
                                                        current_position=self.device_position)

            runtime_data['servo_status'][device_index] = self.device_position
            # print("device index, position, power = ", device_index, self.device_position, power)
            # self.servo_node[device_index].publish(self.device_position)
            self.setServoPwm(str(device_index), self.device_position)
        except Exception:
            exc_info = sys.exc_info()
            traceback.print_exception(*exc_info)

    def keep_boundaries(self, device_id, current_position):
        """
        Prevent Servo position to go beyond range
        """
        if current_position > self.servo_ranges[device_id][1]:
            adjusted_position = float(self.servo_ranges[device_id][1])
        elif current_position < self.servo_ranges[device_id][0]:
            adjusted_position = float(self.servo_ranges[device_id][0])
        else:
            adjusted_position = float(current_position)
        return adjusted_position

    @staticmethod
    def servo_id_converter(servo_id):
        """
        This will convert from godot to motor's id. Let's say, you have 4x10 (width x depth from static_genome).
        So, you click 2 (actually 4 but 2 for one servo on backward/forward) to go forward. It will be like this:
        o__ser': {'1-0-9': 1, '3-0-9': 1}
        which is 1,3. So this code will convert from 1,3 to 0,1 on motor id.

        Since 0-1 is servo 0, 2-3 is servo 1 and so on. In this case, 0 and 2 is for forward and 1 and 3 is for backward
        """
        if servo_id <= 1:
            return 0
        elif servo_id <= 3:
            return 1
        else:
            print("Input has been refused. Please put motor ID.")

    @staticmethod
    def power_convert(motor_id, power):
        if motor_id % 2 == 0:
            return -1 * power
        else:
            return abs(power)

    @staticmethod
    def motor_converter(motor_id):
        """
        This will convert from godot to motor's id. Let's say, you have 8x10 (width x depth from
        static_genome). So, you click 4 to go forward. It will be like this: o__mot': {'1-0-9':
        1, '5-0-9': 1, '3-0-9': 1, '7-0-9': 1} which is 1,3,5,7. So this code will convert from
        1,3,5,7 to 0,1,2,3 on motor id.

        Since 0-1 is motor 1, 2-3 is motor 2 and so on. In this case, 0 is for forward and 1 is
        for backward.
        """
        # motor_total = capabilities['motor']['count'] #be sure to update your motor total in
        # configuration.py increment = 0 for motor in range(motor_total): if motor_id <= motor +
        # 1: print("motor_id: ", motor_id) increment += 1 return increment
        if motor_id <= 1:
            return 0
        elif motor_id <= 3:
            return 3
        elif motor_id <= 5:
            return 1
        elif motor_id <= 7:
            return 2
        else:
            print("Input has been refused. Please put motor ID.")


class Motor:
    def __init__(self):
        self.pwm = PCA9685(0x40, debug=True)
        self.pwm.setPWMFreq(50)
        self.motor_channels = [[0, 1], [3, 2], [4, 5], [6, 7]]

    @staticmethod
    def duty_range(duty1, duty2, duty3, duty4):
        if duty1 > 4095:
            duty1 = 4095
        elif duty1 < -4095:
            duty1 = -4095

        if duty2 > 4095:
            duty2 = 4095
        elif duty2 < -4095:
            duty2 = -4095

        if duty3 > 4095:
            duty3 = 4095
        elif duty3 < -4095:
            duty3 = -4095

        if duty4 > 4095:
            duty4 = 4095
        elif duty4 < -4095:
            duty4 = -4095
        return duty1, duty2, duty3, duty4

    def left_Upper_Wheel(self, duty):
        if duty > 0:
            self.pwm.setMotorPwm(0, 0)
            self.pwm.setMotorPwm(1, duty)
        elif duty < 0:
            self.pwm.setMotorPwm(1, 0)
            self.pwm.setMotorPwm(0, abs(duty))
        else:
            self.pwm.setMotorPwm(0, 4095)
            self.pwm.setMotorPwm(1, 4095)

    def left_Lower_Wheel(self, duty):
        if duty > 0:
            self.pwm.setMotorPwm(3, 0)
            self.pwm.setMotorPwm(2, duty)
        elif duty < 0:
            self.pwm.setMotorPwm(2, 0)
            self.pwm.setMotorPwm(3, abs(duty))
        else:
            self.pwm.setMotorPwm(2, 4095)
            self.pwm.setMotorPwm(3, 4095)

    def right_Upper_Wheel(self, duty):
        if duty > 0:
            self.pwm.setMotorPwm(6, 0)
            self.pwm.setMotorPwm(7, duty)
        elif duty < 0:
            self.pwm.setMotorPwm(7, 0)
            self.pwm.setMotorPwm(6, abs(duty))
        else:
            self.pwm.setMotorPwm(6, 4095)
            self.pwm.setMotorPwm(7, 4095)

    def right_Lower_Wheel(self, duty):
        if duty > 0:
            self.pwm.setMotorPwm(4, 0)
            self.pwm.setMotorPwm(5, duty)
        elif duty < 0:
            self.pwm.setMotorPwm(5, 0)
            self.pwm.setMotorPwm(4, abs(duty))
        else:
            self.pwm.setMotorPwm(4, 4095)
            self.pwm.setMotorPwm(5, 4095)

    def move(self, motor_index, speed):
        if speed > 0:
            # print("from move(): ", motor_index)
            self.pwm.setMotorPwm(self.motor_channels[motor_index][0], 0)
            self.pwm.setMotorPwm(self.motor_channels[motor_index][1], speed)
        elif speed < 0:
            self.pwm.setMotorPwm(self.motor_channels[motor_index][1], 0)
            self.pwm.setMotorPwm(self.motor_channels[motor_index][0], abs(speed))
        elif speed == 0:
            self.pwm.setMotorPwm(self.motor_channels[motor_index][0], 0)
            self.pwm.setMotorPwm(self.motor_channels[motor_index][1], 0)

    def setMotorModel(self, duty1, duty2, duty3, duty4):
        duty1, duty2, duty3, duty4 = self.duty_range(duty1, duty2, duty3, duty4)
        self.left_Upper_Wheel(duty1)
        self.left_Lower_Wheel(duty2)
        self.right_Upper_Wheel(duty3)
        self.right_Lower_Wheel(duty4)

    def stop(self):
        self.setMotorModel(0, 0, 0, 0)

    @staticmethod
    def motor_converter(motor_id):
        """
        This will convert from godot to motor's id. Let's say, you have 8x10 (width x depth from static_genome).
        So, you click 4 to go forward. It will be like this:
        o__mot': {'1-0-9': 1, '5-0-9': 1, '3-0-9': 1, '7-0-9': 1}
        which is 1,3,5,7. So this code will convert from 1,3,5,7 to 0,1,2,3 on motor id.

        Since 0-1 is motor 1, 2-3 is motor 2 and so on. In this case, 0 is for forward and 1 is for backward.
        """
        # motor_total = capabilities['motor']['count'] #be sure to update your motor total in
        # configuration.py increment = 0 for motor in range(motor_total): if motor_id <= motor +
        # 1: print("motor_id: ", motor_id) increment += 1 return increment
        if motor_id <= 1:
            return 0
        elif motor_id <= 3:
            return 3
        elif motor_id <= 5:
            return 1
        elif motor_id <= 7:
            return 2
        else:
            print("Input has been refused. Please put motor ID.")

    @staticmethod
    def power_convert(motor_id, power):
        if motor_id % 2 == 0:
            return -1 * power
        else:
            return abs(power)


class IR:
    def __init__(self):
        self.IR01 = 14
        self.IR02 = 15
        self.IR03 = 23
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        GPIO.setup(self.IR01, GPIO.IN)
        GPIO.setup(self.IR02, GPIO.IN)
        GPIO.setup(self.IR03, GPIO.IN)

    def read(self):
        gpio_state = []
        ir_sensors = [self.IR01, self.IR02, self.IR03]
        for idx, sensor in enumerate(ir_sensors):
            if GPIO.input(sensor):
                gpio_state.append(idx)
        return gpio_state


class Ultrasonic:
    def __init__(self):
        GPIO.setwarnings(False)
        self.trigger_pin = 27
        self.echo_pin = 22
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(self.trigger_pin, GPIO.OUT)
        GPIO.setup(self.echo_pin, GPIO.IN)

    def send_trigger_pulse(self):
        GPIO.output(self.trigger_pin, True)
        # time.sleep(0.00015)
        GPIO.output(self.trigger_pin, False)

    def wait_for_echo(self, value, timeout):
        count = timeout
        while GPIO.input(self.echo_pin) != value and count > 0:
            count = count - 1

    def get_distance(self):
        distance_cm = [0, 0, 0]
        for i in range(3):
            self.send_trigger_pulse()
            self.wait_for_echo(True, 1000)
            start = time.time()
            self.wait_for_echo(False, 1000)
            finish = time.time()
            pulse_len = finish - start
            distance_cm[i] = pulse_len / 0.000058
        distance_cm = sorted(distance_cm)
        distance_meter = (distance_cm[1] * 0.01) * 2
        return distance_meter


class Battery:
    def battery_total(self):
        adc = Adc()
        Power = adc.recvADC(2) * 3
        return Power


def action(obtained_data, led_flag, feagi_settings, capabilities, motor_data,
           rolling_window, motor, servo, led, runtime_data):
    motor_count = capabilities['motor']['count']
    if 'led' in obtained_data:
        if obtained_data['led'] != {}:
            for data_point in obtained_data['led']:
                led_flag = True
                if data_point not in data_point_status:
                    data_point_status[data_point] = True
                if data_point_status[data_point]:
                    led.LED_on(
                        data_point,
                        int((obtained_data['led'][data_point] / 100) * 255),
                        0, 0)
                data_point_status[data_point] = not data_point_status[data_point]
        else:
            if led_flag:
                for i in range(8):
                    led.LED_on(i, 0, 0, 0)
                led_flag = False
    if 'motor' in obtained_data:
        if obtained_data['motor'] is not {}:
            for data_point in obtained_data['motor']:
                device_power = obtained_data['motor'][data_point]
                device_power = motor.power_convert(data_point, device_power)
                device_id = motor.motor_converter(data_point)
                if device_id not in motor_data:
                    motor_data[device_id] = dict()
                rolling_window[device_id].append(device_power)
                rolling_window[device_id].popleft()
    else:
        for _ in range(motor_count):
            rolling_window[_].append(0)
            rolling_window[_].popleft()
    if capabilities['servo']['disabled'] is not True:
        if 'servo' in obtained_data:
            for data_point in obtained_data['servo']:
                device_id = data_point
                device_power = obtained_data['servo'][data_point]
                servo.move(feagi_device_id=device_id, power=device_power,
                           capabilities=capabilities, feagi_settings=feagi_settings,
                           runtime_data=runtime_data)
    return led_flag


async def read_background(feagi_settings):
    ir = IR()
    while True:
        if len(ir_data) > 2:
            ir_data.popleft()
        ir_data.append(ir.read())
        sleep(feagi_settings['feagi_burst_speed'])


def start_IR(feagi_settings):
    asyncio.run(read_background(feagi_settings))


async def read_ultrasonic(feagi_settings):
    ultrasonic = Ultrasonic()
    while True:
        if len(ultrasonic_data) > 2:
            ultrasonic_data.popleft()
        ultrasonic_data.append(ultrasonic.get_distance())
        sleep(feagi_settings['feagi_burst_speed'])


def start_ultrasonic(feagi_settings):
    asyncio.run(read_ultrasonic(feagi_settings))


async def move_control(motor, feagi_settings, capabilities, rolling_window):
    motor_count = capabilities['motor']['count']
    while True:
        for id in range(motor_count):
            motor_power = window_average(rolling_window[id])
            motor_power = motor_power * capabilities["motor"]["power_amount"]
            motor.move(id, motor_power)
        sleep(feagi_settings['feagi_burst_speed'])


def start_motor(motor, feagi_settings, capabilities, rolling_window):
    asyncio.run(move_control(motor, feagi_settings, capabilities, rolling_window))


async def listening_feagi(feagi_dict, feagi_opu_channel, feagi_settings):
    while True:
        if len(feagi_dict) > 2:
            feagi_dict.popleft()
        feagi_dict.append(pns.efferent_signaling(feagi_opu_channel))


def start_feagi_bridge(feagi_dict, feagi_opu_channel, feagi_settings):
    asyncio.run(listening_feagi(feagi_dict, feagi_opu_channel, feagi_settings))


def main(feagi_auth_url, feagi_settings, agent_settings, capabilities):
    GPIO.cleanup()
    # # FEAGI REACHABLE CHECKER # #
    feagi_flag = False
    print("retrying...")
    print("Waiting on FEAGI...")
    # while not feagi_flag:
    #     print("ip: ", os.environ.get('FEAGI_HOST_INTERNAL', feagi_settings["feagi_host"]))
    #     print("here: ", int(os.environ.get('FEAGI_OPU_PORT', "30000")))
    #     feagi_flag = FEAGI.is_FEAGI_reachable(
    #         os.environ.get('FEAGI_HOST_INTERNAL', feagi_settings["feagi_host"]),
    #         int(os.environ.get('FEAGI_OPU_PORT', "30000")))
    #     sleep(2)

    runtime_data = {
        "current_burst_id": 0,
        "feagi_state": None,
        "cortical_list": (),
        "battery_charge_level": 1,
        "host_network": {},
        'motor_status': {},
        'servo_status': {}
    }
    # # FEAGI REACHABLE CHECKER COMPLETED # #

    # # # FEAGI registration # # # - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
    # - - - - - - - - - - - - - - - - - - #
    feagi_settings, runtime_data, api_address, feagi_ipu_channel, feagi_opu_channel = \
        FEAGI.connect_to_feagi(feagi_settings, runtime_data, agent_settings, capabilities,
                               __version__)
    # - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

    # - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
    # --- Initializer section ---
    motor = Motor()
    servo = Servo()
    led = LED()
    battery = Battery()  # Commented out, not currently in use

    # --- Variables ---
    rolling_window_len = capabilities['motor']['rolling_window_len']
    motor_count = capabilities['motor']['count']
    msg_counter = 0
    led_flag = False
    rgb = dict()
    rgb['camera'] = dict()

    # --- Data Containers ---
    motor_data = dict()
    previous_genome_timestamp = dict()
    # Status for data points
    data_point_status = {}
    previous_frame_data = {}
    message_to_feagi = {}
    # Rolling windows for each motor
    rolling_window = {}

    # Initialize rolling window for each motor
    for motor_id in range(motor_count):
        rolling_window[motor_id] = deque([0] * rolling_window_len)

    threading.Thread(target=start_IR, args=(feagi_settings,), daemon=True).start()
    # threading.Thread(target=start_feagi_bridge, args=(feagi_dict, feagi_opu_channel,
    #                                                   feagi_settings,), daemon=True).start()
    threading.Thread(target=start_motor, args=(motor, feagi_settings, capabilities,
                                               rolling_window,), daemon=True).start()
    # threading.Thread(target=start_ultrasonic, args=(feagi_settings,), daemon=True).start()
    ultrasonic = Ultrasonic()
    cam = cv2.VideoCapture(0)  # you need to do sudo rpi-update to be able to use this
    motor.stop()
    servo.set_default_position(runtime_data)
    device_list = pns.generate_OPU_list(capabilities)
    response = requests.get(api_address + '/v1/feagi/genome/cortical_area/geometry')
    size_list= retina.obtain_cortical_vision_size(capabilities['camera']["index"], response)
    raw_frame = []
    default_capabilities = {}  # It will be generated in update_region_split_downsize. See the
    # overwrite manual
    camera_data = {"vision": {}}
    default_capabilities = pns.create_runtime_default_list(default_capabilities, capabilities)
    threading.Thread(target=pns.feagi_listener, args=(feagi_opu_channel,), daemon=True).start()
    threading.Thread(target=retina.vision_progress, args=(default_capabilities, feagi_opu_channel, api_address, feagi_settings,
                                       camera_data['vision'],), daemon=True).start()
    while True:
        try:
            print(default_capabilities['camera'])
            if default_capabilities['camera']['disabled'] is not True:
                ret, raw_frame = cam.read()
                if len(default_capabilities['camera']['blink']) > 0:
                    raw_frame = default_capabilities['camera']['blink']
                # Post image into vision
                previous_frame_data, rgb, default_capabilities = retina.update_region_split_downsize(
                    raw_frame,
                    default_capabilities,
                    size_list,
                    previous_frame_data,
                    rgb, capabilities)
                default_capabilities['camera']['blink'] = []
                message_to_feagi = pns.generate_feagi_data(rgb, msg_counter, datetime.now(),
                                                           message_to_feagi)
            message_from_feagi = pns.message_from_feagi

            # Fetch data such as motor, servo, etc and pass to a function (you make ur own action.
            obtained_signals = pns.obtain_opu_data(device_list, message_from_feagi)
            led_flag = action(obtained_signals, led_flag, feagi_settings,
                              capabilities, motor_data, rolling_window, motor, servo, led,
                              runtime_data)
            # add IR data into feagi data
            ir_list = ir_data[0] if ir_data else []
            message_to_feagi = sensors.add_infrared_to_feagi_data(ir_list, message_to_feagi,
                                                                  capabilities)
            # add ultrasonic data into feagi data
            ultrasonic_list = ultrasonic.get_distance()
            message_to_feagi = sensors.add_ultrasonic_to_feagi_data(ultrasonic_list,
                                                                    message_to_feagi)
            # add battery data into feagi data
            message_to_feagi = sensors.add_battery_to_feagi_data(battery.battery_total(),
                                                                 message_to_feagi)
            # Wrapping camera data into a frame for FEAGI
            message_to_feagi = pns.generate_feagi_data(rgb, msg_counter, datetime.now(),
                                                       message_to_feagi)
            sleep(feagi_settings['feagi_burst_speed'])
            # Send the data contains IR, Ultrasonic, and camera
            pns.signals_to_feagi(message_to_feagi, feagi_ipu_channel, agent_settings)
        except KeyboardInterrupt as ke:  # Keyboard error
            motor.stop()
            cam.release()
            print("ke: ", ke)
            led.leds_off()
            break
        except Exception as e:
            print("ERROR: ", e)
            traceback.print_exc()
            motor.stop()
            cam.release()
            led.leds_off()
            break
