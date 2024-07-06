#!/usr/bin/env python
# -*- coding: utf-8 -*-

import concurrent.futures as futures
import time

from cockpit import depot
from cockpit.handlers import deviceHandler
from cockpit import events
import cockpit.util.logger
import cockpit.util.userConfig
import cockpit.util.threads

class fpgaLightPowerHandler(deviceHandler.DeviceHandler):
    """
    Light Power Handler for NI FPGA controlled laser source, with proper instance management
    and error handling.
    """
    ## A list of instances. Light persist until exit, so don't need weakrefs.
    _instances = []

    @classmethod
    @cockpit.util.threads.callInNewThread
    def _updater(cls):
        """Monitor output power and tell controls to update their display.
        Querying power status can block while I/O is pending, so we use a
        threadpool to manage asynchronous queries."""
        queries = {}
        with futures.ThreadPoolExecutor() as executor:
            while True:
                time.sleep(0.1)
                for light in cls._instances:
                    if light not in queries.keys():
                        queries[light] = executor.submit(light.getPower)
                    elif queries[light].done():
                        light.lastPower = queries[light].result()
                        queries[light] = executor.submit(light.getPower)

    def __init__(self, name, groupName, callbacks, wavelength, curPower: float, 
                 isEnabled=True, trigHandler=None, trigLine=None) -> None:
        # Validation: 
        if not (trigHandler and trigLine):
            raise Exception(f'{self.__class__.__name__} {name} missing trigger Source and trigger Line.')

        super().__init__(name, groupName, False, callbacks, depot.LIGHT_POWER)
        self.h = trigHandler.registerAnalog(self, trigLine)
        self.trigHandler = trigHandler
        self.trigLine = trigLine
        self.wavelength = wavelength
        self.lastPower = curPower
        self.powerSetPoint = None
        self.isEnabled = isEnabled
        self.callbacks['getPower'] = self.getPower
        
        fpgaLightPowerHandler._instances.append(self)  # Add instance to the list

    def finalizeInitialization(self):
        super().finalizeInitialization()
        self._applyUserConfig()

    def _applyUserConfig(self):
        targetPower = cockpit.util.userConfig.getValue(self.name + '-lightPower', default=0.01)
        try:
            self.setPower(targetPower)
        except Exception as e:
            cockpit.util.logger.log.warning(f"Failed to set prior power level {targetPower} for {self.name}: {e}")

    def onSaveSettings(self):
        return self.powerSetPoint

    def onLoadSettings(self, settings):
        try:
            self.setPower(settings)
        except Exception as e:
            print(f"Invalid power for {self.name}: {settings}")

    def setEnabled(self, isEnabled):
        self.isEnabled = isEnabled

    def getIsEnabled(self):
        return self.isEnabled

    def getPower(self):
        return float(self.trigHandler.getAnalogLine(self.trigLine)/100.0) # Compensate for SpinGauge
    
    def setPower(self, power):
        if power < 0.0 or power > 1.0:
            raise RuntimeError(f"Tried to set invalid power {power} for light {self.name}")
        self.trigHandler.setAnalogLine(self.trigLine, int(power*100))
        self.powerSetPoint = power
        cockpit.util.userConfig.setValue(self.name + '-lightPower', power)

    def getWavelength(self):
        return self.wavelength

    def getSavefileInfo(self):
        return f"{self.name}: {self.lastPower:.1f}" 
     
# Initialize the status updater thread.
# fpgaLightPowerHandler._updater()