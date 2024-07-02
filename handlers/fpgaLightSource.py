#!/usr/bin/env python
# -*- coding: utf-8 -*-

from cockpit import depot
from cockpit.handlers import deviceHandler
from cockpit import events

import cockpit.util.threads

class fpgaLightHandler(deviceHandler.DeviceHandler):
    """
    Light Handler for NI FPGA controlled laser source.
    """

    reset_cache = deviceHandler.DeviceHandler.reset_cache
    cached = deviceHandler.DeviceHandler.cached

    ## Keep track of shutters class variables.
    __shutterToLights = {}
    __lightToShutter = {}
    @classmethod
    def addShutter(cls, shutter, lights={}):
        cls.__shutterToLights[shutter] = set(lights)
        for l in lights:
            cls.__lightToShutter[l] = shutter

    def __init__(self, name, groupName, callbacks, wavelength, exposureTime,
                 trigHandler=None, trigLine=None):
        
        if not (trigHandler or trigHandler):
            e = Exception('%s %s missing trigger Source and trigger Line.' %
                          (self.__class__.__name__,
                           name))
        super().__init__(name, groupName, True, callbacks, depot.LIGHT_TOGGLE)
        self.wavelength = float(wavelength or 0)
        self.defaultExposureTime = exposureTime
        self.exposureTime = exposureTime
        # Current enabled state
        self.state = deviceHandler.STATES.disabled
        # Set up trigger handling, which is required
        self.h = trigHandler.registerDigital(self, trigLine)
        self.triggerNow = self.h.triggerNow
        self.trigHandler = trigHandler
        self.trigLine = trigLine
        self.wavelength = wavelength

        if 'setExposing' not in callbacks:
            callbacks['setExposing'] = lambda name, state: trigHandler.setDigital(trigLine, state)
        
        onAbort = lambda *args: trigHandler.setDigital(trigLine, False)
        events.subscribe(events.USER_ABORT, onAbort)

    def makeInitialPublications(self):
        # Send state event to set initial state of any controls.
        events.publish(events.DEVICE_STATUS, self, self.state)

    def onSaveSettings(self):
        return {
            "isEnabled": self.getIsEnabled(),
            "exposureTime": self.getExposureTime(),
        }
    
    def onLoadSettings(self, settings):
        # Only change settings if needed.
        if self.getExposureTime() != settings["exposureTime"]:
            self.setExposureTime(settings["exposureTime"])
        if self.getIsEnabled() != settings["isEnabled"]:
            self.toggleState()

    def setEnabled(self, setState):
        if self.state == deviceHandler.STATES.constant != setState:
            if 'setExposing' in self.callbacks:
                self.callbacks['setExposing'](self.name, False)

        if setState == deviceHandler.STATES.constant:
            if self.state == setState:
                # Turn off the light
                self.trigHandler.setDigital(self.trigLine, False)
                # Update setState since used to set self.state later
                setState = deviceHandler.STATES.disabled
                events.publish(events.LIGHT_SOURCE_ENABLE, self, False)
            else:
                # Turn on the light continously. 
                self.trigHandler.setDigital(self.trigLine, True)
                if 'setExposing' in self.callbacks:
                    self.callbacks['setExposing'](self.name, True)
                # We indicate that the light source is disabled to prevent
                # it being switched off by an exposure, but this event is
                # used to update controls, so we need to chain it with a
                # manual update.
                events.oneShotSubscribe(events.LIGHT_SOURCE_ENABLE,
                                        lambda *args: self.notifyListeners(self, setState))
                events.publish(events.LIGHT_SOURCE_ENABLE, self, False)
        elif setState == deviceHandler.STATES.enabled:
            self.trigHandler.setDigital(self.trigLine, True)
            events.publish(events.LIGHT_SOURCE_ENABLE, self, True)
        else:
            self.trigHandler.setDigital(self.trigLine, False)
            events.publish(events.LIGHT_SOURCE_ENABLE, self, False)
        self.state = setState

    ## Return True if we are enabled, False otherwise
    def getIsEnabled(self):
        return self.state == deviceHandler.STATES.enabled
    
    ## Set the light source to continuous exposure, if we have that option
    @cockpit.util.threads.callInNewThread
    def setExposing(self, args):
        if not self.enableLock.acquire(False):
            return
        self.notifyListeners(self, deviceHandler.STATES.enabling)
        try:
            self.setEnabled(deviceHandler.STATES.constant)
        except Exception as e:
            self.notifyListeners(self, deviceHandler.STATES.error)
            raise Exception('Problem encountered en/disabling %s:\n%s' % (self.name, e))
        finally:
            self.enableLock.release()

    ## Set a new exposure time, in milliseconds.
    @reset_cache
    def setExposureTime(self, value, outermost=True):
        ## Set the exposure time on self and update that on lights
        # that share the same shutter if this is the outermost call.
        # \param value: new exposure time
        # \param outermost: flag indicating that we should update others.
        self.callbacks['setExposureTime'](self.name, value)
        # Publish event to update control labels.
        events.publish(events.LIGHT_EXPOSURE_UPDATE, self)
        # Update exposure times for lights that share the same shutter.
        s = self.__class__.__lightToShutter.get(self, None)
        self.exposureTime = value
        if s and outermost:
            if hasattr(s, 'setExposureTime'):
                s.setExposureTime(value)
            for other in self.__class__.__shutterToLights[s].difference([self]):
                other.setExposureTime(value, outermost=False)
                events.publish(events.LIGHT_EXPOSURE_UPDATE, other)

    ## Get the current exposure time, in milliseconds.
    @cached
    def getExposureTime(self):
        return self.callbacks['getExposureTime'](self.name)


    ## Simple getter.
    @cached
    def getWavelength(self):
        return self.wavelength


    ## Let them know what wavelength we are.
    def getSavefileInfo(self):
        return str(self.wavelength)
