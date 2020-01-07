# Copyright (c) Microsoft. All rights reserved.
# Licensed under the MIT license. See LICENSE file in the project root for
# full license information.

# pylint: disable=F0401, E1101, E0611

import os
import random
import sys
import time
import json
import logging

import iothub_client
from iothub_client import (IoTHubModuleClient, IoTHubClientError, IoTHubError,
                           IoTHubMessage, IoTHubMessageDispositionResult,
                           IoTHubTransportProvider)

from VideoCapture import VideoCapture

import AppState

logging.basicConfig(format='%(asctime)s | %(message)s', level=logging.INFO)
#logging.basicConfig(format='%(asctime)s | %(threadName)s | %(message)s', level=logging.INFO)

def send_to_Hub_callback(strMessage):
    message = IoTHubMessage(bytearray(strMessage, 'utf8'))
    logging.info('>> ' + sys._getframe().f_code.co_name + '()')
    logging.info('   - message  : {}'.format(message))
    hubManager.send_event_to_output("output1", message, 0)

# Callback received when the message that we're forwarding is processed.
def send_confirmation_callback(message, result, user_context):
    logging.info('>> ' + sys._getframe().f_code.co_name + '()')
    logging.info('   - result  : {}'.format(result))

def module_twin_callback(update_state, payload, hubManager):

    logging.info('>> ' + sys._getframe().f_code.co_name + '()')

    if (update_state == iothub_client.IoTHubTwinUpdateState.PARTIAL):
        jsonData = json.loads(payload)
    else:
        jsonData = json.loads(payload).get('desired')

    logging.info('module_twin_callback()')
    logging.info('   - status  : {}'.format(update_state))
    logging.info('   - payload : {}'.format(json.dumps(jsonData, indent=4)))

    if "ConfidenceLevel" in jsonData:
        logging.info('   - ConfidenceLevel : {}'.format(jsonData['ConfidenceLevel']))
        hubManager.videoCapture.confidenceLevel = float(jsonData['ConfidenceLevel'])

    if "VerboseMode" in jsonData:
        logging.info('   - Verbose         : {}'.format(jsonData['VerboseMode']))
        if jsonData['VerboseMode'] == 0:
            hubManager.videoCapture.verbose = False
        else:
            hubManager.videoCapture.verbose = True

    if "Inference" in jsonData:
        logging.info('   - Inference       : {}'.format(jsonData['Inference']))
        if jsonData['Inference'] == 0:
            hubManager.videoCapture.runInference = False
        else:
            hubManager.videoCapture.runInference = True

    if "VideoSource" in jsonData:
        strUrl = str(jsonData['VideoSource'])
        logging.info('   - VideoSource     : {}'.format(strUrl))
        if strUrl.lower() != hubManager.videoCapture.videoPath.lower() and strUrl != "":
            hubManager.videoCapture.set_Video_Source(strUrl)

    hubManager.module_twin_send_reported()

def send_reported_state_callback(status_code, user_context):
    logging.info('>> ' + sys._getframe().f_code.co_name + '()')
    logging.info('   - status_code : [{}]'.format(status_code))

class HubManager(object):

    def __init__(
            self,
            messageTimeout,
            protocol,
            verbose,
            videoCapture):

        # Communicate with the Edge Hub

        self.messageTimeout = messageTimeout
        self.client_protocol = protocol
        self.client = IoTHubModuleClient()
        self.client.create_from_environment(protocol)
        self.client.set_option("messageTimeout", self.messageTimeout)
        self.client.set_option("product_info","iotedge-jetson-nano-yolov3")
        self.videoCapture = videoCapture

        if verbose:
            self.client.set_option("logtrace", 1)#enables MQTT logging

        self.client.set_module_twin_callback(
            module_twin_callback, self)
        
    def send_reported_state(self, reported_state, size, user_context):
        self.client.send_reported_state(
            reported_state, size,
            send_reported_state_callback, user_context)

    def send_event_to_output(self, outputQueueName, event, send_context):
        self.client.send_event_async(outputQueueName, event, send_confirmation_callback, send_context)

    def module_twin_send_reported(self):

        jsonTemplate = "{\"ConfidenceLevel\": \"%s\",\"VerboseMode\": %d,\"Inference\": %d, \"VideoSource\":\"%s\"}"

        videoCapture = hubManager.videoCapture
        strUrl = videoCapture.videoPath

        jsonData = jsonTemplate % (
            str(videoCapture.confidenceLevel),
            videoCapture.verbose,
            videoCapture.runInference,
            strUrl)

        logging.info('device_twin_send_reported()')
        logging.info('   - payload : {}'.format(json.dumps(jsonData, indent=4)))

        hubManager.send_reported_state(jsonData, len(jsonData), 1002)

def main(
        videoPath ="",
        verbose = False,
        videoWidth = 1280,
        videoHeight = 720,
        fontScale = 1.0,
        inference = False,
        confidenceLevel = 0.8
        ):

    global hubManager

    try:
        logging.info('Python {}'.format(sys.version))
        logging.info('Yolo Capture Azure IoT Edge Module. Press Ctrl-C to exit.' )

        with VideoCapture(videoPath, 
                         verbose,
                         videoWidth,
                         videoHeight,
                         fontScale,
                         inference,
                         confidenceLevel) as videoCapture:

            try:
                videoCapture.set_Wallpaper(videoCapture._frame_wp_init_iothub)
                hubManager = HubManager(messageTimeout = 10000, 
                                        protocol = IoTHubTransportProvider.MQTT,
                                        verbose = False, 
                                        videoCapture = videoCapture)

                AppState.init(hubManager)
            except IoTHubError as iothub_error:
                logging.error("Unexpected error %s from IoTHub" % iothub_error )
                return

            videoCapture.start()

    except KeyboardInterrupt:
        logging.info('Video capture module stopped')


def __convertStringToBool(env):
    if env in ['True', 'TRUE', '1', 'y', 'YES', 'Y', 'Yes']:
        return True
    elif env in ['False', 'FALSE', '0', 'n', 'NO', 'N', 'No']:
        return False
    else:
        raise ValueError('Could not convert string to bool.')

if __name__ == '__main__':
    try:
        VIDEO_PATH = os.environ['VIDEO_PATH']
        VERBOSE = __convertStringToBool(os.getenv('VERBOSE', 'True'))
        VIDEO_WIDTH = int(os.getenv('VIDEO_WIDTH', 1920))
        VIDEO_HEIGHT = int(os.getenv('VIDEO_HEIGHT', 1080))
        FONT_SCALE = os.getenv('FONT_SCALE', 1)
        INFERENCE = __convertStringToBool(os.getenv('INFERENCE', 'False'))
        CONFIDENCE_LEVEL = float(os.getenv('CONFIDENCE_LEVEL', "0.8"))

    except ValueError as error:
        logging.error(error )
        sys.exit(1)

    main(VIDEO_PATH, VERBOSE, VIDEO_WIDTH, VIDEO_HEIGHT, FONT_SCALE, INFERENCE, CONFIDENCE_LEVEL)



