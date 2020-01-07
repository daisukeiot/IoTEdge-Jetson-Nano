
from enum import Enum

class CaptureDevice(Enum):
    Unknown = 0
    Webcam = 1
    Rtsp = 2
    Hololens = 3

class CaptureDeviceState(Enum):
    Unknown = 0
    ErrorOpen = 1
    ErrorRead = 2
    ErrorNotSupported = 3
    ErrorNoNetwork = 4
    Init = 5
    Running = 6
    Stop = 7