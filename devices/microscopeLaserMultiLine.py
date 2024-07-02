import cockpit.handlers.lightPower
import cockpit.handlers.lightSource
from cockpit import depot
from cockpit.devices.microscopeDevice import MicroscopeBase

class MicroscopeLaserMultiLine(MicroscopeBase):
    def __init__(self, name, config):
        super().__init__(name, config)
        # Directly parse the 'wavelength' entry from the config.
        self.wavelength = int(self.config.get('wavelength', '0'))

    def getHandlers(self):
        # Now, the creation of handlers can use self.wavelength directly,
        # since each instance of MicroscopeLaserMultiLine represents a single wavelength
        power_handler = cockpit.handlers.lightPower.LightPowerHandler(
            f"{self.name} {self.wavelength} nm power", # name
            f"{self.name} {self.wavelength} nm light source", # groupName
            {'setPower': self._setPower,
             'getPower': self._getPower,},
            self.wavelength,
            curPower=.2,
            isEnabled=True)
        trigsource = self.config.get('triggersource', None)
        trigline = self.config.get('triggerline', None)
        if trigsource:
            trighandler = depot.getHandler(trigsource, depot.EXECUTOR)
        else:
            trighandler = None
        self._exposureTime = 100
        light_handler = cockpit.handlers.lightSource.LightHandler(
            f"{self.name} {self.wavelength} nm",
            f"{self.name} {self.wavelength} nm light source",
            {'setEnabled': lambda name, on: self._setEnabled(on),
             'setExposureTime': lambda name, value: setattr(self, '_exposureTime', value),
             'getExposureTime': lambda name: self._exposureTime},
            self.wavelength,
            100,
            trighandler,  # Assuming no trigger handler for simplicity
            trigline)

        self.handlers.extend([power_handler, light_handler])
        return self.handlers

    def _setEnabled(self, on):
        if on:
            self._proxy.enable(self.wavelength)
        else:
            self._proxy.disable(self.wavelength)

    @cockpit.util.threads.callInNewThread
    def _setPower(self, power: float) -> None:
        self._proxy.set_power(power, self.wavelength)

    def _getPower(self) -> float:
        # Adjust to retrieve power based on wavelength
        return self._proxy.get_power(self.wavelength)

    def finalizeInitialization(self):
        # This should probably work the other way around:
        # after init, the handlers should query for the current state,
        # rather than the device pushing state info to the handlers as
        # we currently do here.
        ph = self.handlers[0] # powerhandler
        ph.powerSetPoint = self._proxy.get_set_power()
        # Set lightHandler to enabled if light source is on.
        lh = self.handlers[-1]
        lh.state = int(self._proxy.get_is_on())