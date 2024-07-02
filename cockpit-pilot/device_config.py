from microscope.device_server import device
from microscope.cameras.pco import pcoPandaCamera
from microscope.lights.coboltskyra import CoboltSkyra
from microscope.stages.asi import ASIStage
from microscope.simulators import SimulatedCamera
from microscope.simulators import SimulatedLightSource

HOST = "172.22.11.1"

DEVICES = [
    # device(pcoPandaCamera, host=host, port=7701),
    # device(CoboltSkyra, host=HOST, port=7702, conf={"com": "COM4"}),
    device(SimulatedCamera, host=HOST, port=8000),
    # device(ASIStage, host=HOST, port=7701,
    # conf={"which_port": "COM3", "axes": ('X', 'Y', 'Z'), "lead_screws": ('S','S','S'), "axes_min_mm": (-23,-23,-0.08), "axes_max_mm": ( 25,23,0.06)})
]

# [pco camera]
# type: cockpit.devices.microscopeCamera.MicroscopeCamera
# uri: PYRO:pcoPandaCamera@127.0.0.1:7701
