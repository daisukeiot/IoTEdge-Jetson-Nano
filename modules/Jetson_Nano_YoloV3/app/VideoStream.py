# pylint: disable=F0401, E1101, E0611
import sys
import cv2
import logging
import time
import numpy as np
from threading import Thread
from queue import Queue
from config import CaptureDeviceState

#This class reads all the video frames in a separate thread and always has the keeps only the latest frame in its queue to be grabbed by another thread
class VideoStream(object):

    def __init__(self, videoCapture, path, queue_size=3):
        logging.info('>> ' + self.__class__.__name__ + "." + sys._getframe().f_code.co_name + '() : {}'.format(path))

        try:
            self.running = False
            self.videoCaptureClass = videoCapture
            self.videoCapture = cv2.VideoCapture(path)
            self.Q = Queue(maxsize=queue_size)

            if (self.videoCapture.isOpened()):
                self.thread = Thread(target=self.update, args=())
                self.thread.daemon = True
            else:
                self.videoCapture.release()
                self.videoCapture = None
                logging.error("Video Stream failed to open")
        
        except Exception as ex:
            logging.error('>> Exception : {}'.format(ex))

    def start(self):
        logging.info('>> ' + self.__class__.__name__ + "." + sys._getframe().f_code.co_name + '()')

        if self.running:
            return True

        if not self.videoCapture.isOpened():
            logging.warn('>> ' + self.__class__.__name__ + "." + sys._getframe().f_code.co_name + '() : Failed to open Video Stream')
            return False

        time.sleep(1.0)

        # read one frame to make sure we can read from capture source
        (grabbed, frame) = self.videoCapture.read()

        if grabbed:
            logging.info('>> Successfully read from video capture device')

        self.running = True
        self.thread.start()
        return True

    def update(self):
        try:
            while True:

                if not self.running:
                    break

                if self.Q.full():
                    self.Q.get()

                if not self.Q.full():
                    (grabbed, frame) = self.videoCapture.read()

                    if not grabbed:
                        logging.error('>> VideoStream:update() : Failed Read VideovideoCapture')
                        self.videoCaptureClass.set_status(CaptureDeviceState.ErrorRead)
                        self.running = False
                        break

                    self.Q.put(frame)
        except Exception as e:
            logging.error("Exception : VideoStream:update() " + str(e))

    def read(self):
        try:
            return True, self.Q.get()
        except Queue.Empty:
            logging.error("Q empty")
            return False, np.array([])

    def more(self):
        tries = 0
        while self.Q.qsize() == 0 and self.running and tries < 5:
            time.sleep(0.1)
            tries += 1

        return self.Q.qsize() > 0

    def stop(self):
        logging.info('>> ' + self.__class__.__name__ + "." + sys._getframe().f_code.co_name + '()')
        self.running = False
        while self.Q.empty() == False:
            self.Q.get()

    def close(self):
        logging.info('>> ' + self.__class__.__name__ + "." + sys._getframe().f_code.co_name + '()')
        if self.running:
            self.stop()
        if self.videoCapture:
            self.videoCapture.release()
            self.videoCapture = None