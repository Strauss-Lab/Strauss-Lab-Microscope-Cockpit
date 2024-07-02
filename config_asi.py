"""Configuration file for deviceserver.
"""
# The 'device' function creates device definitions.
from microscope.device_server import device

# Import required device classes
from microscope.stages.asi import ASIStage

# Import required device classes
from microscope.cameras.pco import pcoPandaCamera

# host is the IP address (or hostname) from where the device will be
# accessible.  If everything is on the same computer, then host will
# be '127.0.0.1'.  If devices are to be available on the network,
# then it will be the IP address on that network.
host = '127.0.0.1'

# Each element in the DEVICES list identifies a device that will be
# served on the network.  Each device is defined like so:
#
# device(cls, host, port, conf)
#     cls: class of the device that will be served
#     host: ip or hostname where the device will be accessible.
#         This will be the same value for all devices.
#     port: port number where the device will be accessible.
#         Each device must have its own port.
#     conf: a dict with the arguments to construct the device
#         instance.  See the individual class documentation.
#
# This list, initialises two cobolt lasers and one Andor camera.
"""DEVICES = [
    device(ASIStage, host, 7701,
           {"which_port": "COM3", "axes": ('X', 'Y'), "lead_screws": ('S','S'), "axes_min_mm": (-50,-25), "axes_max_mm": ( 50, 25)})
]"""

# AXIS LIMITS ARE IN MM
# LEAD SCREW FOR Z AXIS IS MEANINGLESS WHEN Z IS PIEZO

DEVICES = [
    device(ASIStage, host, 7702,
           {"which_port": "COM1", "axes": ('X', 'Y', 'Z'), "lead_screws": ('S','S','S'), "axes_min_mm": (-23,-23,-0.08), "axes_max_mm": ( 25,23,0.06)}),
    device(pcoPandaCamera, host, 7701)
]