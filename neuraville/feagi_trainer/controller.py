#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Copyright 2016-2022 The FEAGI Authors. All Rights Reserved.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
==============================================================================
"""

from time import sleep
from datetime import datetime
from feagi_agent import pns_gateway as pns
from feagi_agent import retina as retina
from feagi_agent.version import __version__
from feagi_agent import feagi_interface as feagi
from feagi_agent import testing_mode
from feagi_agent import trainer as feagi_trainer
from configuration import *
import requests
import os
import cv2

def change_detector_grayscale(previous, current, capabilities):
    """
    Detects changes between previous and current frames and checks against a threshold.

    Compares the previous and current frames to identify differences. If the difference
    exceeds a predefined threshold (iso), it records the change in a dictionary for Feagi.

    Inputs:
    - previous: Dictionary with 'cortical' keys containing NumPy ndarray frames.
    - current: Dictionary with 'cortical' keys containing NumPy ndarray frames.

    Output:
    - Dictionary containing changes in the ndarray frames.
    """
    # Using cv2.absdiff for optimized difference calculation
    difference = current
    thresholded = cv2.threshold(difference, capabilities['camera']['threshold_default'][0],
                                capabilities['camera']['threshold_default'][1],
                                cv2.THRESH_TOZERO)[1]
    thresholded = retina.effect(thresholded, capabilities)
    # print(check_brightness(current))
    cv2.imshow("difference", difference)
    cv2.imshow("center only", thresholded)
    cv2.imshow("current", current)
    cv2.imshow("previous", previous)
    if cv2.waitKey(30) & 0xFF == ord('q'):
        pass
    # Convert to boolean array for significant changes
    # significant_changes = thresholded > 0

    feagi_data = retina.create_feagi_data_grayscale(thresholded, current,
                                                    previous.shape)
    return feagi_data


def change_detector(previous, current, capabilities):
    """
    Detects changes between previous and current frames and checks against a threshold.

    Compares the previous and current frames to identify differences. If the difference
    exceeds a predefined threshold (iso), it records the change in a dictionary for Feagi.

    Inputs:
    - previous: Dictionary with 'cortical' keys containing NumPy ndarray frames.
    - current: Dictionary with 'cortical' keys containing NumPy ndarray frames.

    Output:
    - Dictionary containing changes in the ndarray frames.
    """

    # Using cv2.absdiff for optimized difference calculation
    difference = current
    thresholded = cv2.threshold(difference, capabilities['camera']['threshold_default'][0],
                                capabilities['camera']['threshold_default'][1],
                                cv2.THRESH_BINARY)[1]
    cv2.imshow("difference", difference)
    cv2.imshow("center only", thresholded)
    cv2.imshow("current", current)
    cv2.imshow("previous", previous)
    if cv2.waitKey(30) & 0xFF == ord('q'):
        pass
    # significant_changes = thresholded > 0

    feagi_data = retina.create_feagi_data(thresholded, current, previous.shape)
    return dict(feagi_data)


if __name__ == "__main__":
    # Generate runtime dictionary
    runtime_data = {"vision": {}, "current_burst_id": None, "stimulation_period": None,
                    "feagi_state": None,
                    "feagi_network": None}
    print("retrying...")
    FEAGI_FLAG = False
    print("Waiting on FEAGI...")
    while not FEAGI_FLAG:
        FEAGI_FLAG = feagi.is_FEAGI_reachable(
            os.environ.get('FEAGI_HOST_INTERNAL', feagi_settings["feagi_host"]),
            int(os.environ.get('FEAGI_OPU_PORT', "3000")))
        sleep(2)
    # # # FEAGI registration # # # - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
    # - - - - - - - - - - - - - - - - - - #
    feagi_settings, runtime_data, api_address, feagi_ipu_channel, feagi_opu_channel = \
        feagi.connect_to_feagi(feagi_settings, runtime_data, agent_settings, capabilities,
                               __version__)
    # - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
    msg_counter = runtime_data["feagi_state"]['burst_counter']
    if not pns.full_list_dimension:
        pns.full_list_dimension = pns.fetch_full_dimensions()
    rgb = dict()
    rgb['camera'] = dict()
    previous_frame_data = {}
    response = requests.get(api_address + '/v1/feagi/genome/cortical_area/geometry')
    size_list = retina.obtain_cortical_vision_size("00", response)  # Temporarily
    start_timer = 0
    raw_frame = []
    continue_loop = True
    total = 0
    success = 0
    success_rate = 0
    while continue_loop:
        image_obj = feagi_trainer.scan_the_folder(capabilities['image_reader']['path'])
        for image in image_obj:
            raw_frame = image[0]
            name_id = image[1]
            message_to_feagi = feagi_trainer.id_training_with_image(message_to_feagi, name_id)
            # Post image into vision
            # CUSTOM MADE ONLY #############################
            if size_list:
                region_coordinates = retina.vision_region_coordinates(raw_frame.shape[1],
                                                                      raw_frame.shape[0],
                                                                      abs(capabilities['camera'][
                                                                              'gaze_control'][0]),
                                                                      abs(capabilities[
                                                                              'camera'][
                                                                              'gaze_control'][1]),
                                                                      abs(capabilities['camera'][
                                                                              'pupil_control'][
                                                                              0]),
                                                                      abs(capabilities['camera'][
                                                                              'pupil_control'][
                                                                              1]),
                                                                      "00",
                                                                      size_list)
                segmented_frame_data = retina.split_vision_regions(
                    coordinates=region_coordinates, raw_frame_data=raw_frame)
                compressed_data = dict()
                for cortical in segmented_frame_data:
                    compressed_data[cortical] = retina.downsize_regions(segmented_frame_data[
                                                                            cortical],
                                                                        size_list[cortical])
                vision_dict = dict()
                for get_region in compressed_data:
                    if size_list[get_region][2] == 3:
                        if previous_frame_data != {}:
                            vision_dict[get_region] = change_detector(
                                previous_frame_data[get_region],
                                compressed_data[get_region],
                                capabilities)
                    else:
                        if previous_frame_data != {}:
                            vision_dict[get_region] = change_detector_grayscale(
                                previous_frame_data[get_region],
                                compressed_data[get_region],
                                capabilities)
                previous_frame_data = {}
                rgb['camera'] = vision_dict

            # previous_frame_data, rgb = retina.update_region_split_downsize(raw_frame, capabilities, "00",
            #                                                      size_list, previous_frame_data,
            #                                                      rgb)

            capabilities, feagi_settings['feagi_burst_speed'] = retina.vision_progress(
                capabilities, feagi_opu_channel, api_address, feagi_settings, raw_frame)
            message_to_feagi = pns.generate_feagi_data(rgb, msg_counter, datetime.now(),
                                                       message_to_feagi)
            # Vision process ends
            if start_timer == 0:
                start_timer = datetime.now()
            while capabilities['image_reader']['pause'] >= int(
                    (datetime.now() - start_timer).total_seconds()):
                # Testing mode section
                if capabilities['image_reader']['test_mode']:
                    success_rate, success, total = testing_mode.mode_testing(name_id,
                                                                             feagi_opu_channel,
                                                                             total, success,
                                                                             success_rate)
                else:
                    success_rate, success, total = 0, 0, 0
                pns.signals_to_feagi(message_to_feagi, feagi_ipu_channel, agent_settings)
            start_timer = 0
            message_to_feagi.clear()

        continue_loop = capabilities['image_reader']['loop']
