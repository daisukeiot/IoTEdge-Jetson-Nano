# pylint: disable=F0401, E1101, E0611

import asyncio
import tornado.ioloop
import tornado.web
import tornado.websocket
from tornado import gen
from tornado.platform.asyncio import AnyThreadEventLoopPolicy
from tornado.concurrent import run_on_executor

from threading import Thread
import base64
import os
import logging
import sys

#####################################################################################
# Class to run Tornado web app in a new thread
#####################################################################################
class ImageServer(Thread):

    #
    # initialize a thread as a daemon
    #
    def __init__(self, 
                 port,
                 videoCapture):

        logging.info('>> ' + self.__class__.__name__ + "." + sys._getframe().f_code.co_name + '()')

        Thread.__init__(self)
        self.setDaemon(True)
        self.port = port
        self.videoCapture = videoCapture

    #
    # start tornado web app
    #
    def run(self):

        logging.info('>> ' + self.__class__.__name__ + "." + sys._getframe().f_code.co_name + '() : Starting Image Server')

        try:
            asyncio.set_event_loop_policy(AnyThreadEventLoopPolicy())
            asyncio.set_event_loop(asyncio.new_event_loop())
            indexPath = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'www')

            app = tornado.web.Application([
                (r"/stream", ImageStreamHandler, {'videoCapture': self.videoCapture}),
                (r"/(.*)", tornado.web.StaticFileHandler, {'path': indexPath, 'default_filename': 'index.html'})
            ])
            app.listen(self.port)
            tornado.ioloop.IOLoop.instance().start()

        except Exception as e:
            logging.info('ImageServer::exited run loop. Exception - '+ str(e))

    def close(self):
        logging.info('>> ' + self.__class__.__name__ + "." + sys._getframe().f_code.co_name + '() : Closing Image Server')

#####################################################################################
# Class to handle websocket connections/events
#####################################################################################
from concurrent.futures import ThreadPoolExecutor

class ImageStreamHandler(tornado.websocket.WebSocketHandler):

    executor = ThreadPoolExecutor(max_workers=4)

    def initialize(self, videoCapture):
        logging.info('>> ' + self.__class__.__name__ + "." + sys._getframe().f_code.co_name + '()')
        self.clients = []
        self.videoCapture = videoCapture
        self.videoCapture.imageStreamHandler = self
        self.loop = asyncio.get_event_loop()

    def check_origin(self, origin):
        logging.info('>> ' + self.__class__.__name__ + "." + sys._getframe().f_code.co_name + '() : {}'.format(self.request.remote_ip))
        # self.clients[origin] = self
        return True

    #
    # Websocket event handler for connection open
    # https://developer.mozilla.org/en-US/docs/Web/API/WebSocket/onopen
    #
    def open(self):
        logging.info('>> ' + self.__class__.__name__ + "." + sys._getframe().f_code.co_name + '() : {}'.format(self.request.remote_ip))
        self.clients.append(self)
        self.videoCapture.sendCurrentVideoPath("")

    #
    # Websocket event handler for received messages
    # https://developer.mozilla.org/en-US/docs/Web/API/WebSocket/onmessage
    #
    def on_message(self, msg):
        if msg == 'nextFrame':
            #
            # Return a frame to display
            #
            self.send_Display_Frame()

        elif 'VideoPath' in msg:
            logging.info(">> VideoPath " + msg)
            self.videoCapture.setVideoPathFromUI(msg)
        else:
            logging.info(">> on_message " + msg)

    def on_close(self):
        logging.info('>> ' + self.__class__.__name__ + "." + sys._getframe().f_code.co_name + '() : {}'.format(self.request.remote_ip))
        self.clients.remove(self)

    def send_Display_Frame(self):
        try:
            frame = self.videoCapture.get_display_frame()
            if not frame == None:
                encoded = base64.b64encode(frame)
                self.write_message("{\"Image\":\""+ encoded.decode() +"\"}", binary=False)
            else:
                logging.warn('>> ' + self.__class__.__name__ + "." + sys._getframe().f_code.co_name + '() : Empty Frame')
        except Exception as ex:
            logging.error('Exception in send_Display_Frame : {}'.format(ex))

    def submit_write(self, json_data):
        logging.info(">> Image Server submit_write {}".format(json_data))
        for client in self.clients:
            if client.ws_connection.stream.socket:
                client.write_message(json_data)
            else:
                self.clients.remove(client)
