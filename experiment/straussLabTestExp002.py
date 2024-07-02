"""Simple Color Rotation Test"""

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

## Provided so the UI knows what to call this experiment.
EXPERIMENT_NAME = 'Strauss Lab Test 002'
REPETITION = 5

class LaserColorRotation(experiment.Experiment):
    def generateActions(self):
        table = actionTable.ActionTable()
        curTime = 0
        for _ in range(REPETITION):
            for light in self.lights:
                curTime = self.exposeSingle(curTime, self.cameras, light, table)
                curTime += decimal.Decimal('1.0')
        # # DEBUG
        # print(f'In {EXPERIMENT_NAME}, printing generated action table: \n{table}')
        return table

    def exposeSingle(self, curTime, cameras, light, table):
        table.addAction(curTime, light, True)   # Turn on light
        table.addAction(curTime + decimal.Decimal('0.1'), light, False)

        for camera in cameras:
            cameraReadyTime = self.getTimeWhenCameraCanExpose(table, camera)
            exposureStartTime = max(curTime, cameraReadyTime)
            exposureEndTime = exposureStartTime + decimal.Decimal('0.1') # Some fixed exposure duration
            table.addAction(exposureStartTime, camera, True) # Start camera exposure
            table.addAction(exposureEndTime, camera, False) # End camera 

        return exposureEndTime

## A consistent name to use to refer to the class itself.
EXPERIMENT_CLASS = LaserColorRotation