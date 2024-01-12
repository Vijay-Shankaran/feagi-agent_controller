from time import sleep
import time
import json
from configuration import *
from feagi_agent import feagi_interface as feagi
from feagi_agent import retina as retina
from feagi_agent import pns_gateway as pns
from feagi_agent.version import __version__
from feagi_agent import actuators
import requests
import cv2
import threading
from datetime import datetime

camera_data = {"vision": {}}


def process_video(path, capabilities):
    cam = cv2.VideoCapture(0)
    while True:
        check, pixels = cam.read()
        camera_data["vision"] = pixels
    cam.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    threading.Thread(target=process_video, args=(capabilities['camera']['video_device_index'],
                                                 capabilities), daemon=True).start()
    print("Ready...")
    ser = actuators.initialization_port(capabilities['arduino']['port'])
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
    response = requests.get(api_address + '/v1/feagi/genome/cortical_area/geometry')
    capabilities['camera']['size_list'] = retina.obtain_cortical_vision_size(capabilities['camera']["index"], response)
    previous_frame_data = {}
    raw_frame = []
    device_list = pns.generate_OPU_list(capabilities)

    # Experimenting...delete this
    data = dict()
    data[1] = 1
    data[2] = 1
    # Ends

    # To give ardiuno some time to open serial. It's required
    time.sleep(5)
    cam = cv2.VideoCapture(0)
    while True:
        message_from_feagi = pns.signals_from_feagi(feagi_opu_channel)

        # Fetch data such as motor, servo, etc and pass to a function (you make ur own action.
        if message_from_feagi is not None:
            obtained_signals = pns.obtain_opu_data(device_list, message_from_feagi)
            new_dict = dict()
            if 'servo' in obtained_signals:
                if obtained_signals['servo']:
                    print("recieved")
                    one_hot_encoded = [0, 0, 0, 0, 0, 0, 0, 0]
                    for x in obtained_signals['servo']:
                        # if x in [0, 1, 2, 3]:
                            # new_dict[x] = obtained_signals['servo'][x]
                            # new_data = actuators.keep_boundaries([0, 180], obtained_signals['servo'][x])
                        one_hot_encoded[x] = obtained_signals['servo'][x]
                    # no judge

                    data_str = ','.join(map(str, one_hot_encoded)) + '\n'
                    print(data_str)
                    # json_data = actuators.convert_dict_to_json(new_dict)
                    # print (json_data)

                    if ser.isOpen():
                        ser.write(data_str.encode())
                        print("sent")
        if camera_data['vision'] is not None:
            raw_frame = camera_data['vision']
        if capabilities['camera']['blink'] != []:
            raw_frame = capabilities['camera']['blink']
        previous_frame_data, rgb = retina.detect_change_edge(raw_frame, capabilities,
                                                             capabilities['camera']["index"],
                                                             capabilities['camera']['size_list'],
                                                             previous_frame_data, rgb)
        # capabilities['camera']['effect'].clear()
        capabilities['camera']['blink'] = []
        capabilities, feagi_settings['feagi_burst_speed'] = \
            retina.vision_progress(capabilities, feagi_opu_channel, api_address, feagi_settings,
                                   raw_frame)

        message_to_feagi = pns.generate_feagi_data(rgb, msg_counter, datetime.now(),
                                                   message_to_feagi)

        sleep(0.01)
        pns.signals_to_feagi(message_to_feagi, feagi_ipu_channel, agent_settings)
        # print('sent')
        message_to_feagi.clear()
        for i in rgb['camera']:
            rgb['camera'][i].clear()
            # actuators.send_serial(ser, json_data)
            # time.sleep(1)
            # ser.readline()
            # time.sleep(2)


