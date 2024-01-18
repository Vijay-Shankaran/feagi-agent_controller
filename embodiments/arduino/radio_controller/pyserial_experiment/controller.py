from time import sleep
import time
import json
from configuration import *
from feagi_agent import feagi_interface as feagi
from feagi_agent import retina as retina
from feagi_agent import pns_gateway as pns
from feagi_agent.version import __version__
from feagi_agent import actuators
import serial
import requests
import cv2
import threading
from datetime import datetime

camera_data = {"vision": {}}


def process_video(path):
    cam = cv2.VideoCapture(path) # Update {camera: video_device_index} in configuration.py
    while True:
        check, pixels = cam.read()
        camera_data["vision"] = pixels
    cam.release()
    cv2.destroyAllWindows()


def initialization_port(port):
    return serial.Serial(port,
                         baudrate=9600,
                         timeout=2.5,
                         parity=serial.PARITY_NONE,
                         bytesize=serial.EIGHTBITS,
                         stopbits=serial.STOPBITS_ONE)


if __name__ == "__main__":
    threading.Thread(target=process_video, args=(capabilities['camera']['video_device_index'],), daemon=True).start()
    print("Ready...")
    ser = initialization_port(capabilities['arduino']['port'])
    feagi_flag = False
    previous_data_frame = {}
    runtime_data = {"cortical_data": {}, "current_burst_id": None,
                    "stimulation_period": 0.01, "feagi_state": None,
                    "feagi_network": None}

    # # # FEAGI registration # # # - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
    feagi_settings, runtime_data, api_address, feagi_ipu_channel, feagi_opu_channel = \
        feagi.connect_to_feagi(feagi_settings, runtime_data, agent_settings, capabilities,
                               __version__)
    # - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
    msg_counter = runtime_data["feagi_state"]['burst_counter']
    rgb = dict()
    rgb['camera'] = dict()
    previous_frame_data = {}
    raw_frame = []
    response = requests.get(api_address + '/v1/feagi/genome/cortical_area/geometry')
    size_list = retina.obtain_cortical_vision_size(capabilities['camera']["index"], response)
    default_capabilities = {}  # It will be generated in update_region_split_downsize. See the overwrite manual
    default_capabilities = pns.create_runtime_default_list(default_capabilities, capabilities) #  Generated dictionary for controller. Mostly for vision
    threading.Thread(target=pns.feagi_listener, args=(feagi_opu_channel,), daemon=True).start() # To update the message_from_feagi in real time
    threading.Thread(target=retina.vision_progress,
                     args=(default_capabilities, feagi_opu_channel, api_address, feagi_settings,
                           camera_data['vision'],), daemon=True).start() # Update vision in real time based on opu activated
    time.sleep(5)  # To give ardiuno some time to open serial. It's required
    while True:
        message_from_feagi = pns.message_from_feagi
        obtained_data = pns.obtain_opu_data(message_from_feagi)
        recieved_servo_data = actuators.get_servo_data(obtained_data)  # Get servo data only
        if recieved_servo_data:
            one_hot_encoded = [0, 0, 0, 0, 0, 0, 0, 0]
            for x in recieved_servo_data:
                one_hot_encoded[x] = recieved_servo_data[x]
                data_str = ','.join(map(str, one_hot_encoded)) + '\n'
                if ser.isOpen():
                    ser.write(data_str.encode())
            print("sent data to arduino: ", data_str)

        # Vision sending to FEAGI SECTION starts #
        if camera_data['vision'] is not None:
            raw_frame = camera_data[
                'vision']  # This will be updated by process_video function in here
        default_capabilities['camera']['blink'] = []  # Clear the stored data.
        if 'camera' in default_capabilities:
            if default_capabilities['camera']['blink'] != []:  # This will be activated if you  used the blink opu in the FEAGI's brain visualizer
                raw_frame = default_capabilities['camera']['blink']
        previous_frame_data, rgb, default_capabilities, \
        size_list = retina.update_region_split_downsize(raw_frame,
                                                        default_capabilities,
                                                        size_list,
                                                        previous_frame_data,
                                                        rgb, capabilities)
        if rgb:
            message_to_feagi = pns.generate_feagi_data(rgb, msg_counter, datetime.now(),
                                                       message_to_feagi)
        # Vision sending to FEAGI SECTION ends #
        time.sleep(feagi_settings['feagi_burst_speed'])

        pns.signals_to_feagi(message_to_feagi, feagi_ipu_channel, agent_settings)
        message_to_feagi.clear()
        for i in rgb['camera']:
            rgb['camera'][i].clear()
