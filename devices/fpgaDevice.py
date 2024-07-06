#!/usr/bin/env python
# -*- coding: utf-8 -*-

## Copyright (C) 2021 University of Oxford
##
## This file is part of Cockpit.
##
## Cockpit is free software: you can redistribute it and/or modify
## it under the terms of the GNU General Public License as published by
## the Free Software Foundation, either version 3 of the License, or
## (at your option) any later version.
##
## Cockpit is distributed in the hope that it will be useful,
## but WITHOUT ANY WARRANTY; without even the implied warranty of
## MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
## GNU General Public License for more details.
##
## You should have received a copy of the GNU General Public License
## along with Cockpit.  If not, see <http://www.gnu.org/licenses/>.

from cockpit import depot
import cockpit.handlers.fpgaLightPower
import cockpit.handlers.fpgaLightSource
import cockpit.handlers.lightSource
import cockpit.handlers.fpgaLineHandler
from cockpit.devices import device

class AnalogueDevice(device.Device):
    """Analogue Device connected to NI cRIO FPGA for SI Experiment.

    The device name must be name with [FPGA ...]
    e.g. [FPGA Angle], [FPGA Phase], [FPGA Polarizer]

    In depot.ini: 
        [FPGA Angle]
        type: cockpit.devices.fpgaDevice.AnalogueDevice
        analogSource: NI FPGA
        analogLine: 0
        offset: 0
        gain: 1
    """

    _config_types = {
        'idlevoltage': float,
        'offset': float,
        'gain': float,
    }

    def __init__(self, name, config={}):
        super().__init__(name, config)
        self.handlers = []
        self.panel = None

    def getHandlers(self):
        aSource = self.config.get('analogsource', None)
        trigLine = int(self.config.get('analogline', None))
        trigHandler = depot.getHandler(aSource, depot.EXECUTOR)
        if trigHandler is None:
            raise Exception(f'No control source for {self.__class__}.')
        gain = self.config.get('gain', 1) # WARNING: might be problematic here. (type)
        offset = self.config.get('offset', 0)
        minValue = int(self.config.get('minvalue', 0))
        maxValue = int(self.config.get('maxvalue', 10))

        self.handlers.append(cockpit.handlers.fpgaLineHandler.fpgaAnalogueLineHandler(
            self.name, # name
            self.name + ' ' + str(trigLine) + ' Analogue Line', # groupName
            {},
            curValue=0,
            isEnabled=True,
            trigHandler=trigHandler,
            trigLine=trigLine,
            offset=offset,
            gain=gain,
            minValue=minValue,
            maxValue=maxValue))
        return self.handlers
    
class fpgaLaser(device.Device):
    """Laser device connected to NI cRIO for SI Experiment. 

    In depot.ini:
        [Cobolt Skyra]
        type: cockpit.devices.fpgaDevice.fpgaLaser
        wavelength: 532, 638, 488, 405
        triggerSource: NI FPGA
        digitalLine: 0, 1, 2, 3
        analogLine: 3, 4, 5, 6
    """
    def __init__(self, name, config):
        super().__init__(name, config)
        self.handlers = []
        self.panel = None

    def initialize(self):
        # Convert comma-separated string values from config into lists of integers
        if 'wavelength' in self.config:
            self.wavelengths = [int(w.strip()) for w in self.config['wavelength'].split(',')]
        else:
            self.wavelengths = []

        if 'digitalline' in self.config:
            self.toggles = [int(d.strip()) for d in self.config['digitalline'].split(',')]
        else:
            self.toggles = []

        if 'analogline' in self.config:
            self.trigLines = [int(a.strip()) for a in self.config['analogline'].split(',')]
        else:
            self.trigLines = []

    def getHandlers(self):
        for i in range(len(self.wavelengths)):
            wavelength = self.wavelengths[i]
            toggle = self.toggles[i]
            trigLine = self.trigLines[i]
            trigHandler = depot.getHandler(self.config['triggersource'], depot.EXECUTOR)
            self.handlers.append(cockpit.handlers.fpgaLightPower.fpgaLightPowerHandler(
                self.name + ' ' + str(wavelength) + ' power',  # name
                self.name + ' ' + str(wavelength) + ' light source',  # groupName
                {},
                wavelength,
                curPower=.2,
                isEnabled=True,
                trigHandler=trigHandler,
                trigLine=trigLine))
            self._exposureTime = 100
            self.handlers.append(cockpit.handlers.fpgaLightSource.fpgaLightHandler(
                self.name + ' ' + str(wavelength) + ' nm',  # name; this is the name displayed on light panels
                self.name + ' ' + str(wavelength) + ' light source',  # groupName
                {
                    'setExposureTime': lambda name, value: setattr(self, '_exposureTime', value),
                    'getExposureTime': lambda name: self._exposureTime
                },
                wavelength,
                100,
                trigHandler,
                toggle))
            
        return self.handlers