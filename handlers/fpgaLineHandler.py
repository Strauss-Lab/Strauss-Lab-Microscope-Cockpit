#!/usr/bin/env python
# -*- coding: utf-8 -*-

from cockpit import depot
from cockpit.handlers import deviceHandler
import cockpit.util.logger
import cockpit.util.userConfig

## This handler is for FPGA analogue lines where the value of the line can be
# directly controlled through software.

class fpgaAnalogueLineHandler(deviceHandler.DeviceHandler):
    ## callbacks should fill in the following functions: 
    # - setValue(value): Set value to line.
    # - getValue(): Get current value of the line.
    # \param trigLine analogueLine number
    # \param curValue Initial output value
    # \param isEnabled True iff the handler can be interacted with

    def __init__(self, name, groupName, callbacks, curValue: int,
                 isEnabled=True, trigHandler=None, trigLine=None, offset=0, gain=1, 
                 minValue=0, maxValue=10) -> None:
        # Validation:
        if not (trigHandler or trigLine):
            e = Exception('%s %s missing trigger Source and trigger Line.' %
                          (self.__class__.__name__,
                           name))
            raise e
        
        super().__init__(name, groupName, False, callbacks, depot.FPGA_ANALOG)
        self.name = name
        self.h = trigHandler.registerAnalog(self, trigLine, offset, gain)
        self.trigHandler = trigHandler
        self.trigLine = trigLine
        self.lastValue = curValue
        self.valueSetPoint = None
        self.isEnabled = isEnabled
        self.minValue = minValue
        self.maxValue = maxValue

    def finalizeInitialization(self):
        super().finalizeInitialization()
        self._applyUserConfig()

    def _applyUserConfig(self):
        targetValue = cockpit.util.userConfig.getValue(self.name + '-value', default = 0)
        try:
            self.setValue(targetValue)
        except Exception as e:
            cockpit.util.logger.log.warning("Failed to set prior value %s for %s: %s" % (targetValue, self.name, e))

    def onSaveSettings(self):
        return self.valueSetPoint
    
    def onLoadSettings(self, settings):
        try: 
            self.setValue(settings)
        except Exception as e:
            # Invalid Value; just ignore it.
            print("Invalid value for %s: %s" % (self.name, settings))

    ## Toggle Accessibility of the handler.
    def setEnabled(self, isEnabled):
        self.isEnabled = isEnabled

    ## Return True iff we're currently enabled (i.e. GUI is active).
    def getIsEnabled(self):
        return self.isEnabled
    
    ## Fetch the current line value.
    def getValue(self):
        return self.trigHandler.getAnalogLine(self.trigLine)
    
    ## Handle the user selecting a new power level.
    def setValue(self, value):
        self.trigHandler.setAnalogLine(self.trigLine, value)
        self.valueSetPoint = value
        cockpit.util.userConfig.setValue(self.name + '-value', value)
    
    def getTrigLine(self):
        return self.trigLine

    ## Experiments should include the line info.
    def getSavefileInfo(self):
        return "%s: %d" % (self.name, self.lastValue)