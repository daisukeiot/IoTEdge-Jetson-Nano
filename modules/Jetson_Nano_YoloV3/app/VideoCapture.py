# pylint: disable=F0401, E1101, E0611
import sys
import logging
import cv2
import numpy as np
import time
import json
import os
import subprocess
import signal
from threading import Event
from ImageServer import ImageServer
from VideoStream import VideoStream
from YoloInference import YoloInference
from urllib.parse import urlparse
from config import CaptureDeviceState, CaptureDevice
from fps import FPS

class VideoCapture(object):

    def __init__(self,
                 videoPath = "",
                 verbose = True,
                 displayW = 1920,
                 displayH = 1080,
                 fontScale = 1.0,
                 inference = True,
                 confidenceLevel = 0.5):

        self.verbose = verbose
        self._debug = False

        self.videoPath = videoPath
        self._videoSourceType = CaptureDevice.Unknown
        self._videoSourceState = CaptureDeviceState.Unknown
        self.videoStream = None

        self._videoReadyEvent = Event()

        self._capture_in_progress = False

        # Display Resolution
        # Will try to set camera's resolution to the specified resolution
        self._displayW = displayW
        self._displayH = displayH

        self._cameraW = 0
        self._cameraH = 0

        # Camera's FPS
        self._cameraFPS = 30

        # Font Scale for putText
        self._fontScale = float(fontScale)

        # turn inference on/off
        self.runInference = inference

        # confidence level threshold
        self.confidenceLevel = confidenceLevel

        # various frame data

        # frame data for UI
        self._displayFrame = None

        # wallpapers for UI
        self._frame_wp_init_system = cv2.imread("./www/WP-InitializingSystem.png")
        self._frame_wp_no_video    = cv2.imread("./www/WP-NoVideoData.png")
        self._frame_wp_init_iothub = cv2.imread("./www/WP-InitializeIotHub.png")

        if self.verbose:
            logging.info('>> ' + self.__class__.__name__ + "." + sys._getframe().f_code.co_name + '()')

        logging.info('===============================================================')
        logging.info('Initializing Video Capture with the following parameters:')
        logging.info('   - OpenCV Version     : {}'.format(cv2.__version__))
        logging.info('   - Video path         : {}'.format(self.videoPath))
        logging.info('   - Display Resolution : {} x {}'.format(self._displayW, self._displayH))
        logging.info('   - Font Scale         : {}'.format(self._fontScale))
        logging.info('   - Inference?         : {}'.format(self.runInference))
        logging.info('   - ConfidenceLevel    : {}'.format(self.confidenceLevel))
        logging.info('===============================================================')

        # set wallpaper
        self.set_Wallpaper(self._frame_wp_init_system)

        # set FPS
        self.fps = FPS()

        self.imageStreamHandler = None

        # Start Web Server for View
        self.imageServer = ImageServer(80, self)
        self.imageServer.start()

        # Set Video Source
        self.set_Video_Source(self.videoPath)

        self.set_Wallpaper(cv2.imread("./www/WP-InitializeAIEngine.png"))
        # logging.info('Yolo Inference Initializing\r\n')
        self.yoloInference = YoloInference(self._fontScale, sendMessage=False)
        # logging.info('Yolo Inference Initialized\r\n')

    def __enter__(self):

        if self.verbose:
            logging.info('>> ' + self.__class__.__name__ + "." + sys._getframe().f_code.co_name + '()')

        # self.set_Video_Source(self.videoPath)

        return self

    def videoStreamReadTimeoutHandler(self, signum, frame):
        raise Exception("VideoStream Read Timeout") 

    #
    # Video Source Management
    #
    def _set_Video_Source_Type(self, videoPath):

        if self.verbose:
            logging.info('>> ' + self.__class__.__name__ + "." + sys._getframe().f_code.co_name + '() : {}'.format(videoPath))

        self._reset_Video_Source()

        if '/dev/video' in videoPath.lower():
            self._videoSourceType = CaptureDevice.Webcam

        elif 'rtsp:' in videoPath.lower():
            self._videoSourceType = CaptureDevice.Rtsp

        elif '/api/holographic/stream' in videoPath.lower():
            self._videoSourceType = CaptureDevice.Hololens

        if self.verbose:
            logging.info('<< ' + self.__class__.__name__ + "." + sys._getframe().f_code.co_name + '() : {}'.format(self._videoSourceType))

    def _get_Video_Source_Type(self, videoPath):

        videoType = CaptureDevice.Unknown

        if self.verbose:
            logging.info('>> ' + self.__class__.__name__ + "." + sys._getframe().f_code.co_name + '() : {}'.format(videoPath))

        if '/dev/video' in videoPath.lower():
            videoType = CaptureDevice.Webcam

        elif 'rtsp:' in videoPath.lower():
            videoType = CaptureDevice.Rtsp

        elif '/api/holographic/stream' in videoPath.lower():
            videoType = CaptureDevice.Hololens

        return videoType
    #
    # Resets video capture/stream settings
    #
    def _reset_Video_Source(self):

        if self.verbose:
            logging.info('>> ' + self.__class__.__name__ + "." + sys._getframe().f_code.co_name + '()')

        if self.videoStream:
            self.videoStream.stop()
        #    self.videoStream.close()
        #     self.videoStream = None

        self._videoSourceType = CaptureDevice.Unknown
        self._videoSourceState = CaptureDeviceState.Unknown

    def set_Video_Source(self, newVideoPath):

        if self.verbose:
            logging.info('>> ' + self.__class__.__name__ + "." + sys._getframe().f_code.co_name + '()')

        retVal = False
        realVideoPath = newVideoPath

        if self.videoPath == newVideoPath and self._videoSourceState == CaptureDeviceState.Running:
            return True

        if self.imageStreamHandler != None:
            statusMsg = '{{\"DeviceStatus\":\"Connecting to {}\",\"isSuccess\":{}}}'.format(self._remove_credential(newVideoPath), 1)
            self.imageStreamHandler.submit_write(statusMsg)

        self._videoSourceState = CaptureDeviceState.Stop

        if self._capture_in_progress:
            # wait for queue to drain and loop to exit
            time.sleep(1.0)

        self._capture_in_progress = False

        self._set_Video_Source_Type(realVideoPath)

        if self._videoSourceType == CaptureDevice.Unknown:
            self._videoSourceState = CaptureDeviceState.ErrorNotSupported
            logging.error('>> ' + self.__class__.__name__ + "." + sys._getframe().f_code.co_name + '() : Unsupported Video Source {}'.format(self._videoSourceType))
        else:
            self._videoSourceState = CaptureDeviceState.Init

            if self._videoSourceType == CaptureDevice.Hololens:
                strHololens = realVideoPath.split('?')
                # disable audio
                realVideoPath = '{}?holo=true&pv=true&mic=false&loopback=false'.format(strHololens[0])

            self.videoStream = VideoStream(videoCapture = self, path=realVideoPath)

            fps_override = 30

            if not self.videoStream.videoCapture == None:

                # get resolution
                cameraH1 = int(self.videoStream.videoCapture.get(cv2.CAP_PROP_FRAME_HEIGHT))
                cameraW1 = int(self.videoStream.videoCapture.get(cv2.CAP_PROP_FRAME_WIDTH))
                cameraFPS1 = int(self.videoStream.videoCapture.get(cv2.CAP_PROP_FPS))

                if self._videoSourceType == CaptureDevice.Webcam:

                    if not cameraH1 == self._displayH:
                        self.videoStream.videoCapture.set(cv2.CAP_PROP_FRAME_HEIGHT, self._displayH)
                    if not cameraW1 == self._displayW:
                        self.videoStream.videoCapture.set(cv2.CAP_PROP_FRAME_WIDTH, self._displayW)

                elif self._videoSourceType == CaptureDevice.Rtsp:

                    if not cameraH1 == self._displayH:
                        self.videoStream.videoCapture.set(cv2.CAP_PROP_FRAME_HEIGHT, self._displayH)
                    if not cameraW1 == self._displayW:
                        self.videoStream.videoCapture.set(cv2.CAP_PROP_FRAME_WIDTH, self._displayW)

                elif self._videoSourceType == CaptureDevice.Hololens:

                    holo_w = 1280
                    holo_h = 720

                    if 'live_med.mp4' in realVideoPath:
                        holo_w = 854
                        holo_h = 480
                    elif 'live_low.mp4' in realVideoPath:
                        holo_w = 428
                        holo_h = 240
                        fps_override = 15

                    self.videoStream.videoCapture.set(cv2.CAP_PROP_FRAME_HEIGHT, holo_h)
                    self.videoStream.videoCapture.set(cv2.CAP_PROP_FRAME_WIDTH, holo_w)

                self.videoStream.videoCapture.set(cv2.CAP_PROP_FPS, fps_override)

                self._cameraH = int(self.videoStream.videoCapture.get(cv2.CAP_PROP_FRAME_HEIGHT))
                self._cameraW = int(self.videoStream.videoCapture.get(cv2.CAP_PROP_FRAME_WIDTH))
                self._cameraFPS = int(self.videoStream.videoCapture.get(cv2.CAP_PROP_FPS))

                logging.info('===============================================================')
                logging.info('Setting Video Capture with the following parameters:')
                logging.info('   - Video Source Type  : {}'.format(self._videoSourceType))
                logging.info('   - Display Resolution : {} x {}'.format(self._displayW, self._displayH))
                logging.info('   Original             : {} x {} @ {}'.format(cameraW1, cameraH1, cameraFPS1))
                logging.info('   New                  : {} x {} @ {}'.format(self._cameraW, self._cameraH, self._cameraFPS))
                logging.info('===============================================================')

                if self.videoStream.start():
                    self._videoSourceState = CaptureDeviceState.Running
                    retVal = True
                else:
                    self._videoSourceState = CaptureDeviceState.ErrorRead
            else:

                if self._videoSourceType == CaptureDevice.Hololens or self._videoSourceType == CaptureDevice.Rtsp:
                    url_parsed = urlparse(realVideoPath)

                    if url_parsed.password != None or url_parsed.username != None:
                        url_parsed = url_parsed._replace(netloc="{}".format(url_parsed.hostname))

                    ipAddress = url_parsed.netloc

                    ping_ret = subprocess.call(['ping', '-c', '5', '-W', '3', ipAddress],
                                               stdout=open(os.devnull, 'w'),
                                               stderr=open(os.devnull, 'w'))

                    if ping_ret == 0:
                        self._videoSourceState = CaptureDeviceState.ErrorOpen
                    else:
                        self._videoSourceState = CaptureDeviceState.ErrorNoNetwork

                logging.error('>> ' + self.__class__.__name__ + "." + sys._getframe().f_code.co_name + '() : Failed to open Video Capture')

        self.videoPath = realVideoPath

        if retVal == False:
            self.set_Wallpaper(self._frame_wp_no_video)
        else:
            self._videoReadyEvent.set()

        self.sendCurrentVideoPath(realVideoPath)

        return retVal

    def get_display_frame(self):
        return self.displayFrame

    def set_status(self, device_status):
        self._videoSourceState = device_status

        if self._videoSourceState != CaptureDeviceState.Running:
            self.sendCurrentVideoPath("")

    def sendCurrentVideoPath(self, videoPath):

        if videoPath == "":
            video_path = self._remove_credential(self.videoPath)
        else:
            video_path = self._remove_credential(videoPath)

        logging.info('>> Current Video Status {}'.format(self._videoSourceState))

        if self.imageStreamHandler != None:
            if self._videoSourceState == CaptureDeviceState.Running:
                strUserName = ""
                strPassword = ""

                videoType = self._get_Video_Source_Type(videoPath)

                if videoType == CaptureDevice.Rtsp or videoType == CaptureDevice.Hololens:
                    url_parsed = urlparse(videoPath)

                    if url_parsed.password != None:
                        strPassword = url_parsed.password
                    if url_parsed.username != None:
                        strUserName = url_parsed.username

                statusMsg = '{{\"DevicePath\":\"{}\",\"isSuccess\":{},\"UserName\":\"{}\",\"Password\":\"{}\"}}'.format(video_path, 1,strUserName, strPassword )
            else:
                statusMsg = '{{\"DeviceStatus\":\"Error ({}): {}\",\"isSuccess\":{},\"UserName\":\"\",\"Password\":\"\"}}'.format(self._videoSourceState, video_path, 0)
            self.imageStreamHandler.submit_write(statusMsg)

    def setVideoPathFromUI(self, json_Data):

        videoPath = ""
        json_Data = json.loads(json_Data)
        logging.info('>> ' + self.__class__.__name__ + "." + sys._getframe().f_code.co_name + '() : {}'.format(json_Data["VideoPath"]))
        logging.info('>> {}'.format(json_Data["VideoPath"]))
        logging.info('>> {}'.format(json_Data["UserName"]))
        logging.info('>> {}'.format(json_Data["Password"]))

        videoType = self._get_Video_Source_Type(json_Data["VideoPath"])

        if videoType == CaptureDevice.Webcam:
            videoPath = json_Data["VideoPath"].strip()
        elif videoType == CaptureDevice.Rtsp or videoType == CaptureDevice.Hololens:
            url_parsed = urlparse(json_Data["VideoPath"].strip())

            if '@' in url_parsed.netloc or len(json_Data["UserName"]) == 0:
                # already contains password or user name not specified
                videoPath = json_Data["VideoPath"]
            else:
                url_parsed = url_parsed._replace(netloc='{}:{}@{}'.format(json_Data["UserName"], json_Data["Password"], url_parsed.netloc))
                videoPath = url_parsed.geturl()

        self.set_Video_Source(videoPath)

    def _remove_credential(self, videoPath):

        logging.info('>> ' + self.__class__.__name__ + "." + sys._getframe().f_code.co_name + '()')

        ret_Path = ""
        videoType = self._get_Video_Source_Type(videoPath)

        if videoType == CaptureDevice.Webcam:
            ret_Path = videoPath
        elif videoType == CaptureDevice.Rtsp or videoType == CaptureDevice.Hololens:

            url_parsed = urlparse(videoPath)

            if url_parsed.password != None or url_parsed.username != None:
                url_parsed = url_parsed._replace(netloc="{}".format(url_parsed.hostname))

            ret_Path = url_parsed.geturl()

        return ret_Path

    def set_Wallpaper(self, image):

        if self.verbose:
            logging.info('>> ' + self.__class__.__name__ + "." + sys._getframe().f_code.co_name + '()')

        self.displayFrame = cv2.imencode( '.jpg', image )[1].tobytes()

    def start(self):

        if self.verbose:
            logging.info('>> ' + self.__class__.__name__ + "." + sys._getframe().f_code.co_name + '()')

        while True:
            if self._videoSourceState == CaptureDeviceState.Running:
                self._capture_in_progress = True
                self.__Run__()
                self._capture_in_progress = False
            else:

                if self._videoSourceState == CaptureDeviceState.ErrorOpen or self._videoSourceState == CaptureDeviceState.ErrorRead:
                    self.set_Wallpaper(self._frame_wp_no_video)

                if self._videoSourceType == CaptureDevice.Unknown:
                    if self._debug:
                        logging.info('>> ' + self.__class__.__name__ + "." + sys._getframe().f_code.co_name + '() : Unknown Device')
                    time.sleep(1.0)
                else:
                    if self._debug:
                        logging.info('>> ' + self.__class__.__name__ + "." + sys._getframe().f_code.co_name + '() : Device Not Running')
                    # time.sleep(1.0)
                    logging.info('>> Video Ready Event Enter ---------------')
                    self._videoReadyEvent.wait()
                    logging.info('<< Video Ready Event Exit  ---------------')
                    self._videoReadyEvent.clear()

    def __Run__(self):

        if self.verbose:
            logging.info('===============================================================')
            logging.info('>> ' + self.__class__.__name__ + "." + sys._getframe().f_code.co_name + '()')

        # Check camera's FPS
        if self._cameraFPS == 0:
            logging.error('Error : Could not read FPS')
            # raise Exception("Unable to acquire FPS for Video Source")
            return

        logging.info('>> Frame rate (FPS)     : {}'.format(self._cameraFPS))
        logging.info('>> Run Inference {}'.format(self.runInference))

        perFrameTimeInMs = 1000 / self._cameraFPS

        self.fps.start()
        self.fps.reset()

        while True:

            # Get current time before we capture a frame
            tFrameStart = time.time()
            frame = np.array([])
            captureRet = False

            if not self._videoSourceState == CaptureDeviceState.Running:
                break

            captureRet, frame = self.videoStream.read()

            if captureRet == False:
                self._videoSourceState = CaptureDeviceState.ErrorRead
                logging.error("ERROR : Failed to read from video source")
                break

            if frame.size > 0:

                # Run Object Detection
                if self.runInference:
                    self.yoloInference.runInference(frame, self._cameraW, self._cameraH, self.confidenceLevel)

                # Calculate FPS
                currentFPS = self.fps.fps()

                if (currentFPS > self._cameraFPS):
                    # Cannot go faster than Camera's FPS
                    currentFPS = self._cameraFPS

                # Add FPS Text to the frame
                cv2.putText( frame, "FPS " + str(currentFPS), (10, int(30 * self._fontScale)), cv2.FONT_HERSHEY_SIMPLEX, self._fontScale, (0,0,255), 2)

                self.displayFrame = cv2.imencode( '.jpg', frame )[1].tobytes()

            timeElapsedInMs = (time.time() - tFrameStart) * 1000

            if perFrameTimeInMs > timeElapsedInMs:
                # This is faster than image source (e.g. camera) can feed.  
                waitTimeBetweenFrames = perFrameTimeInMs - timeElapsedInMs
                time.sleep(waitTimeBetweenFrames/1000.0)

    def __exit__(self, exception_type, exception_value, traceback):

        self.imageServer.close()
        cv2.destroyAllWindows()
