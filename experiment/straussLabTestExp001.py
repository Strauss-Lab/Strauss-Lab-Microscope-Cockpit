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

class SISingleZ(experiment.Experiment):
    def __init__(self, collectionOrder="Z, Color, Angle, Phase",
                 numAngle=3, numPhase=5, numZ=3,
                 stageTime=100.0, attTime=100.0, angleTime=100.0, phaseTime=100.0, stepTime=100.0,
                 lightTime=200.0, cameraTime=200.0, onlyCentre=False,
                 *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.lights = []
        for light in depot.getHandlersOfType(depot.LIGHT_TOGGLE):
            if light.getIsEnabled():
                self.lights.append(light)
        self.angleHandler = depot.getHandlerWithName('FPGA Angle')
        self.phaseHandler = depot.getHandlerWithName('FPGA Phase')
        self.attHandler = depot.getHandlerWithName('FPGA Attenuator')
        self.collectionOrder = collectionOrder
        self.numAngle = 1 if onlyCentre else numAngle
        self.numPhase = numPhase
        self.numZ = numZ
        self.stageTime = stageTime
        self.attTime = attTime
        self.angleTime = angleTime
        self.phaseTime = phaseTime
        self.stepTime = stepTime
        self.lightTime = lightTime
        self.cameraTime = cameraTime
        self.onlyCentre = onlyCentre

    def generateActions(self):
        table = actionTable.ActionTable()
        curTime = 0
        # Turn off all the lights.
        for light in self.lights:
            table.addAction(curTime, light, False)
            curTime += decimal.Decimal(self.stepTime)
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
            curTime = self.exposeSingle(curTime, self.cameras, self.lights[color], table)
            curTime += decimal.Decimal(self.stepTime)
        # print(f'Printing Generated Action Table:\n{table}')
        return table

    def exposeSingle(self, curTime, cameras, light, table):
        table.addAction(curTime, light, True)   # Turn on light
        table.addAction(curTime + decimal.Decimal(self.lightTime), light, False)
        for camera in cameras:
            cameraReadyTime = self.getTimeWhenCameraCanExpose(table, camera)
            exposureStartTime = max(curTime, cameraReadyTime)
            exposureEndTime = exposureStartTime + decimal.Decimal(self.cameraTime) # Some fixed exposure duration
            table.addAction(exposureStartTime, camera, True) # Start camera exposure
            table.addAction(exposureEndTime, camera, False) # End camera 

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
            z += self.zHeight / 15

## A consistent name to use to refer to the class itself.
EXPERIMENT_CLASS = SISingleZ

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
        self.createInput(num_val_sizer, "Number of z:", 'numZ', validator=IntValidator())

        main_sizer.Add(num_val_sizer, 0, wx.ALL, 5)

        # Time input controls in a flex grid sizer
        time_input_sizer = wx.FlexGridSizer(6, 5, 5)  # 6 columns (including text), 5px gap
        self.createInput(time_input_sizer, "Stage Time (ms):", 'stageTime')
        self.createInput(time_input_sizer, "Attenuator Time (ms):", 'attTime')
        self.createInput(time_input_sizer, "Angle Time (ms):", 'angleTime')
        self.createInput(time_input_sizer, "Phase Time (ms):", 'phaseTime')
        self.createInput(time_input_sizer, "Step Time (ms):", 'stepTime')
        self.createInput(time_input_sizer, "Light Time (ms):", 'lightTime')
        self.createInput(time_input_sizer, "Camera Time (ms):", 'cameraTime')

        main_sizer.Add(time_input_sizer, 0, wx.ALL, 5)
        self.SetSizerAndFit(main_sizer)

    def createInput(self, sizer, label, setting_name, validator=FloatValidator()):
        text = wx.StaticText(self, -1, label)
        sizer.Add(text, 0, wx.ALL, 5)
        value = self.settings.get(setting_name, "")
        setattr(self, setting_name, wx.TextCtrl(self, value=str(value), validator=validator))
        sizer.Add(getattr(self, setting_name), 0, wx.ALL, 5)

    def augmentParams(self, params):
        self.saveSettings()
        params['collectionOrder'] = self.collectionOrder.GetStringSelection()
        params['numAngle'] = int(self.numAngle.GetValue())
        params['numPhase'] = int(self.numPhase.GetValue())
        params['numZ'] = int(self.numZ.GetValue())
        params['stageTime'] = float(self.stageTime.GetValue())
        params['attTime'] = float(self.attTime.GetValue())
        params['angleTime'] = float(self.angleTime.GetValue())
        params['phaseTime'] = float(self.phaseTime.GetValue())
        params['stepTime'] = float(self.stepTime.GetValue())
        params['lightTime'] = float(self.lightTime.GetValue())
        params['cameraTime'] = float(self.cameraTime.GetValue())
        return params

    def _getDefaultSettings(self):
        return {
            'collectionOrder': "Z, Color, Angle, Phase",
            'numAngle': 3,
            'numPhase': 5,
            'numZ': 3,
            'stageTime': 100.0,
            'attTime': 100.0,
            'angleTime': 100.0,
            'phaseTime': 100.0,
            'stepTime': 100.0,
            'lightTime': 200.0,
            'cameraTime': 200.0,
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
        return {
            'collectionOrder': self.collectionOrder.GetStringSelection(),
            'numAngle': int(self.numAngle.GetValue()),
            'numPhase': int(self.numPhase.GetValue()),
            'numZ': int(self.numZ.GetValue()),
            'stageTime': float(self.stageTime.GetValue()),
            'attTime': float(self.attTime.GetValue()),
            'angleTime': float(self.angleTime.GetValue()),
            'phaseTime': float(self.phaseTime.GetValue()),
            'stepTime': float(self.stepTime.GetValue()),
            'lightTime': float(self.lightTime.GetValue()),
            'cameraTime': float(self.cameraTime.GetValue()),
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
