"""Test Experiment."""

from cockpit.experiment import actionTable
from cockpit import depot
from cockpit.experiment import experiment
from cockpit.gui import guiUtils
import cockpit.util.Mrc
import cockpit.util.datadoc
import cockpit.util.userConfig

import decimal
import math
import numpy as np
import os
import tempfile
import shutil
import wx
import time

from cockpit.gui.guiUtils import IntValidator
from cockpit.gui.guiUtils import FloatValidator

## Provided so the UI knows what to call this experiment.
EXPERIMENT_NAME = 'Strauss Lab Experiment 001'

COLLECTION_ORDERS = {
    "Z, Color, Angle, Phase": (3, 2, 0, 1),
    "Z, Color, Phase, Angle": (3, 2, 1, 0),
}

#TODO: Stage mover handling, get the optimal time for movement; hint for users about 
#      the meanings of the time variables.

class StraussSI(experiment.Experiment):
    def __init__(self, collectionOrder="Z, Color, Angle, Phase",
                 numAngle=3, numPhase=5,
                 stageTime=100.0, attTime=100.0, angleTime=100.0, phaseTime=100.0, stepTime=100.0,
                 cameraTime=200.0, onlyCentre=False,
                 power_settings=[],
                 startup_settings=[],
                 *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.lights = []
        self.lightPower = []
        self.startup = []
        for light in depot.getHandlersOfType(depot.LIGHT_TOGGLE):
            if light.getIsEnabled():
                self.lights.append(light)   # Get all enabled light sources

        for power in depot.getHandlersOfType(depot.LIGHT_POWER):
            if power.getIsEnabled():
                self.lightPower.append(power) # Get all enabled light power handlers

        # Ensure all power handlers have a value of 0
        for power in self.lightPower:
            p = power.getPower()
            assert p == 0, f"Laser {power.name} has a non-zero power: {p}"

        # Ensure power settings match the number of light powers
        assert len(power_settings) == len(self.lightPower), f'Power settings list len = {len(power_settings)}, but there are {len(self.lightPower)} lasers'
        assert len(startup_settings) == len(power_settings), f'Startup settings list len = {len(startup_settings)}, but there are {len(self.lightPower)} lasers'

        self.angleHandler = depot.getHandlerWithName('FPGA Angle')
        self.phaseHandler = depot.getHandlerWithName('FPGA Phase')
        self.attHandler = depot.getHandlerWithName('FPGA Attenuator')

        self.collectionOrder = collectionOrder
        self.numAngle = 1 if onlyCentre else numAngle
        self.numPhase = numPhase
        self.numZ = int(self.zHeight/self.sliceHeight)
        self.stageTime = stageTime
        self.attTime = attTime
        self.angleTime = angleTime
        self.phaseTime = phaseTime
        self.stepTime = stepTime
        self.cameraTime = cameraTime
        self.onlyCentre = onlyCentre
        self.power_settings = power_settings
        self.startup_settings = startup_settings

    def generateActions(self):
        print(f'exposure settings: {self.exposureSettings} type: {type(self.exposureSettings)}')
        table = actionTable.ActionTable()
        curTime = 0
        # Turn off all the lights.
        for light in self.lights:
            table.addAction(curTime, light, False)
        curTime += decimal.Decimal(self.stepTime)

        for i in range(len(self.lightPower)):
            table.addAction(curTime, self.lightPower[i], self.power_settings[i])
        curTime += decimal.Decimal(self.stepTime)

        # Mask the startup settings
        lights = depot.getHandlersOfType(depot.LIGHT_TOGGLE)
        for i in range(len(lights)):
            if lights[i].getIsEnabled():
                self.startup.append(self.startup_settings[i])

        prev_z = -1
        prev_angle = -1
        prev_color = -1
        prev_phase = -1
        
        for angle, phase, color, z in self.genSIPositions():
            if z != prev_z:
                prev_z = z
                table.addAction(curTime, self.zPositioner, z)  # Move to new z
                curTime += decimal.Decimal(self.stageTime)
            if color != prev_color:
                prev_color = color
                table.addAction(curTime, self.attHandler, color)
                curTime += decimal.Decimal(self.attTime)
            if angle != prev_angle:
                prev_angle = angle
                table.addAction(curTime, self.angleHandler, angle)  # Change angle
                curTime += decimal.Decimal(self.angleTime)
            if phase != prev_phase:
                prev_phase = phase
                table.addAction(curTime, self.phaseHandler, phase)
                curTime += decimal.Decimal(self.phaseTime)
            curTime = self.expose(curTime, self.cameras, self.lights[color], color, table)
            curTime += decimal.Decimal(self.stepTime)

        # Restore the light toggle states
        for light in self.lights:
            table.addAction(curTime, light, True)
        curTime += decimal.Decimal(self.stepTime)

        # Restore the light power states (0 mW)
        for power in self.lightPower:
            table.addAction(curTime, power, 0)
        return table

    def expose(self, curTime, cameras, light, color, table):
        # First, determine which cameras are not ready to be exposed, because
        # they may have seen light they weren't supposed to see (due to
        # bleedthrough from other cameras' exposures). These need to be
        # triggered (and we need to record that we want to throw away those
        # images) before we can proceed with the real exposure.
        camsToReset = set()
        for camera in cameras:
            if not self.cameraToIsReady[camera]:
                camsToReset.add(camera)
        if camsToReset:
            curTime = self.resetCams(curTime, camsToReset, table)
            
        # Determine when we can start the exposure, based on camera readiness
        exposureStartTime = curTime
        for camera in cameras:
            camExposureReadyTime = self.getTimeWhenCameraCanExpose(table, camera)
            exposureStartTime = max(exposureStartTime, camExposureReadyTime)
        
        # Determine the end time of the exposure
        exposureEndTime = exposureStartTime + decimal.Decimal(self.cameraTime) # Some user-configurable duration
        
        # Add actions to turn on the light and then turn it off after the specified duration
        table.addAction(exposureStartTime, light, True)  # Turn on light
        table.addAction(exposureStartTime + self._get_exposure_time(camera, light) + decimal.Decimal(self.startup[color]), light, False)  # Turn off light
    
        # Trigger the cameras
        usedCams = set()
        for camera in cameras:
            usedCams.add(camera)
            mode = camera.getExposureMode()
            if mode == cockpit.handlers.camera.TRIGGER_AFTER:
                table.addToggle(exposureEndTime, camera)
            elif mode == cockpit.handlers.camera.TRIGGER_DURATION:
                table.addAction(exposureStartTime + decimal.Decimal(self.startup[color]), camera, True)
                table.addAction(exposureEndTime, camera, False)
            elif mode == cockpit.handlers.camera.TRIGGER_DURATION_PSEUDOGLOBAL:
                # We added some security time to the readout time that
                # we have to remove now
                cameraExposureStartTime = (exposureStartTime
                                        - self.cameraToReadoutTime[camera]
                                        - decimal.Decimal(0.005))
                table.addAction(cameraExposureStartTime + decimal.Decimal(self.startup[color]), camera, True)
                table.addAction(exposureEndTime, camera, False)
            elif mode == cockpit.handlers.camera.TRIGGER_BEFORE:
                table.addToggle(exposureStartTime + decimal.Decimal(self.startup[color]), camera)
            elif mode == cockpit.handlers.camera.TRIGGER_SOFT:
                table.addAction(exposureStartTime + decimal.Decimal(self.startup[color]), camera, True)
            else:
                raise Exception ('%s has no trigger mode set.' % camera)
            self.cameraToImageCount[camera] += 1
        
        for camera in self.cameras:
            if (camera not in usedCams and
                camera.getExposureMode() == cockpit.handlers.camera.TRIGGER_AFTER):
                # Camera is a continuous-exposure/frame-transfer camera
                # and therefore saw light it shouldn't have; invalidate it.
                self.cameraToIsReady[camera] = False

        return exposureEndTime

    def genSIPositions(self):
        ordering = COLLECTION_ORDERS[self.collectionOrder]
        maxVals = (self.numAngle, self.numPhase, len(self.lights), self.numZ)  # angle, phase, color, z
        z = self.zStart
        for i in range(maxVals[ordering[0]]):
            for j in range(maxVals[ordering[1]]):
                for k in range(maxVals[ordering[2]]):
                    for l in range(maxVals[ordering[3]]):
                        vals = (i, j, k, l)
                        angle = vals[ordering.index(0)]
                        phase = vals[ordering.index(1)]
                        color = vals[ordering.index(2)]
                        yield (angle, phase, color, z)
            z += self.sliceHeight # Increment the z step

    def _get_exposure_time(self, camera, light_source_name):
        for camera_group, light_sources in self.exposureSettings:
            for light_source, decimal_value in light_sources:
                if light_source_name==light_source and camera_group==[camera]:
                    return decimal_value
        raise RuntimeError()   

## A consistent name to use to refer to the class itself.
EXPERIMENT_CLASS = StraussSI

class BaseTestExperimentUI(wx.Panel):
    """Base Experiment UI for Test experiments.

    Subclasses must implement class property `_CONFIG_KEY_SUFFIX`.
    """
    def __init__(self, parent, configKey):
        super().__init__(parent=parent)

        self.configKey = configKey + self._CONFIG_KEY_SUFFIX
        self.settings = self.loadSettings()

        main_sizer = wx.BoxSizer(wx.VERTICAL)

        # Collection order choice
        rowSizer = wx.BoxSizer(wx.HORIZONTAL)
        text = wx.StaticText(self, -1, "Collection Order:")
        rowSizer.Add(text, 0, wx.ALL, 5)
        self.collectionOrder = wx.Choice(self, choices=list(COLLECTION_ORDERS.keys()))
        # Ensure the selection matches the settings or sets the default
        collection_order_value = str(self.settings.get('collectionOrder', "Z, Color, Angle, Phase"))
        self.collectionOrder.SetStringSelection(collection_order_value)
        rowSizer.Add(self.collectionOrder, 0, wx.ALL, 5)
        main_sizer.Add(rowSizer)

        # Number of values controls in a flex grid sizer
        num_val_sizer = wx.FlexGridSizer(6, 5, 5)  # 6 columns (including text), 5px gap
        self.createInput(num_val_sizer, "Number of angles:", 'numAngle', validator=IntValidator())
        self.createInput(num_val_sizer, "Number of phases:", 'numPhase', validator=IntValidator())

        # Time input controls in a flex grid sizer
        time_input_sizer = wx.FlexGridSizer(6, 5, 5)  # 6 columns (including text), 5px gap
        power_input_sizer = wx.FlexGridSizer(6, 5, 5)
        startup_input_sizer = wx.FlexGridSizer(6, 5, 5)
        self.createInput(time_input_sizer, "Stage Time (ms):", 'stageTime')
        self.createInput(time_input_sizer, "Attenuator Time (ms):", 'attTime')
        self.createInput(time_input_sizer, "Angle Time (ms):", 'angleTime')
        self.createInput(time_input_sizer, "Phase Time (ms):", 'phaseTime')
        self.createInput(time_input_sizer, "Step Time (ms):", 'stepTime')
        self.createInput(time_input_sizer, "Camera Time (ms):", 'cameraTime')

        self.lightPower = []
        for power in depot.getHandlersOfType(depot.LIGHT_POWER):
            if power.getIsEnabled():
                self.lightPower.append(power)
        for power in self.lightPower:
            power_input_sizer.Add(wx.StaticText(self, -1, str(power.name)+' (mW):'))
            setattr(self, str(power.name), wx.TextCtrl(self, value='0', validator=IntValidator(), size=(50, -1)))
            power_input_sizer.Add(getattr(self, str(power.name)), 0, wx.ALL, 5)

        self.lights = [] 
        for light in depot.getHandlersOfType(depot.LIGHT_TOGGLE):
            self.lights.append(light)   # Get all enabled light sources
        for light in self.lights:
            startup_input_sizer.Add(wx.StaticText(self, -1, str(light.name)+' startup (ms):'))
            setattr(self, str(light.name), wx.TextCtrl(self, value='0', validator=IntValidator(), size=(50, -1)))
            startup_input_sizer.Add(getattr(self, str(light.name)), 0, wx.ALL, 5)
        
        main_sizer.Add(self.createSubtitle(' Standard Configuration:'))
        main_sizer.Add(num_val_sizer, 0, wx.ALL, 5)
        main_sizer.Add(self.createSubtitle(' Step Time (ms):'))
        main_sizer.Add(time_input_sizer, 0, wx.ALL, 5)
        main_sizer.Add(self.createSubtitle(' Laser Power (mW):'))
        main_sizer.Add(power_input_sizer, 0, wx.ALL, 5)
        main_sizer.Add(self.createSubtitle(' Laser Startup Time (ms):'))
        main_sizer.Add(startup_input_sizer, 0, wx.ALL, 5)

        self.SetSizerAndFit(main_sizer)

    def createSubtitle(self, text, size=11):
        subtitle = wx.StaticText(self, -1, text)
        subtitle.SetFont(wx.Font(size, family=wx.DECORATIVE, style=wx.NORMAL, weight=wx.BOLD))
        return subtitle

    def createInput(self, sizer, label, setting_name, validator=FloatValidator()):
        text = wx.StaticText(self, -1, label)
        sizer.Add(text, 0, wx.ALL, 5)
        value = self.settings.get(setting_name, "")
        setattr(self, setting_name, wx.TextCtrl(self, value=str(value), validator=validator, size=(50, -1)))
        sizer.Add(getattr(self, setting_name), 0, wx.ALL, 5)

    def augmentParams(self, params):
        self.saveSettings()
        params['collectionOrder'] = self.collectionOrder.GetStringSelection()
        params['numAngle'] = int(self.numAngle.GetValue())
        params['numPhase'] = int(self.numPhase.GetValue())
        params['stageTime'] = float(self.stageTime.GetValue())
        params['attTime'] = float(self.attTime.GetValue())
        params['angleTime'] = float(self.angleTime.GetValue())
        params['phaseTime'] = float(self.phaseTime.GetValue())
        params['stepTime'] = float(self.stepTime.GetValue())
        params['cameraTime'] = float(self.cameraTime.GetValue())
        power_settings = []
        for power in self.lightPower:
            power_settings.append(int(getattr(self, str(power.name)).GetValue()))
        params['power_settings'] = power_settings

        startup_settings = []
        for light in self.lights:
            startup_settings.append(int(getattr(self, str(light.name)).GetValue()))
        params['startup_settings'] = startup_settings
        return params

    def _getDefaultSettings(self):
        return {
            'collectionOrder': "Z, Color, Angle, Phase",
            'numAngle': 3,
            'numPhase': 5,
            'stageTime': 100.0,
            'attTime': 100.0,
            'angleTime': 100.0,
            'phaseTime': 100.0,
            'stepTime': 100.0,
            'cameraTime': 200.0,
            'power_settings': 4*[0],
            'startup_settings': 4*[0], 
        }

    def loadSettings(self):
        default_settings = self._getDefaultSettings()
        result = cockpit.util.userConfig.getValue(self.configKey, default=default_settings)
        # Ensure result has all keys from default_settings
        for key, value in default_settings.items():
            if key not in result:
                result[key] = value
        return result

    def getSettingsDict(self):
        power_settings = []
        startup_settings = [] 
        for power in self.lightPower:
            power_settings.append(int(getattr(self, str(power.name)).GetValue()))

        for light in self.lights:
            startup_settings.append(int(getattr(self, str(light.name)).GetValue()))

        return {
            'collectionOrder': self.collectionOrder.GetStringSelection(),
            'numAngle': int(self.numAngle.GetValue()),
            'numPhase': int(self.numPhase.GetValue()),
            'stageTime': float(self.stageTime.GetValue()),
            'attTime': float(self.attTime.GetValue()),
            'angleTime': float(self.angleTime.GetValue()),
            'phaseTime': float(self.phaseTime.GetValue()),
            'stepTime': float(self.stepTime.GetValue()),
            'cameraTime': float(self.cameraTime.GetValue()),
            'power_settings': power_settings, 
            'startup_settings': startup_settings,
        }

    def saveSettings(self, settings=None):
        if settings is None:
            settings = self.getSettingsDict()
        cockpit.util.userConfig.setValue(self.configKey, settings)

class ExperimentUI(BaseTestExperimentUI):
    _CONFIG_KEY_SUFFIX = 'TestExperimentSettings'

    def __init__(self, parent, configKey):
        super().__init__(parent, configKey)

        self.onlyCentre = wx.CheckBox(self, label="Do Centre Only")
        self.onlyCentre.SetValue(self.settings.get('onlyCentre', False))

        top_row_sizer = self.Sizer.GetItem(0).Sizer
        top_row_sizer.Prepend(self.onlyCentre, 0, wx.ALL, 5)
        self.Sizer.SetSizeHints(self)

    def augmentParams(self, params):
        params = super().augmentParams(params)
        params['onlyCentre'] = self.onlyCentre.GetValue()
        return params

    def _getDefaultSettings(self):
        default = super()._getDefaultSettings()
        default.update({
            'onlyCentre': False,
        })
        return default

    def getSettingsDict(self):
        all_settings = super().getSettingsDict()
        all_settings.update({
            'onlyCentre': self.onlyCentre.GetValue(),
        })
        return all_settings

    def loadSettings(self):
        result = super().loadSettings()
        result.update({
            'onlyCentre': result.get('onlyCentre', False),
        })
        return result
