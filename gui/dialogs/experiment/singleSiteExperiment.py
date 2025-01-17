#!/usr/bin/env python
# -*- coding: utf-8 -*-

## Copyright (C) 2018 Mick Phillips <mick.phillips@gmail.com>
## Copyright (C) 2018 Ian Dobbie <ian.dobbie@bioch.ox.ac.uk>
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

## Copyright 2013, The Regents of University of California
##
## Redistribution and use in source and binary forms, with or without
## modification, are permitted provided that the following conditions
## are met:
##
## 1. Redistributions of source code must retain the above copyright
##   notice, this list of conditions and the following disclaimer.
##
## 2. Redistributions in binary form must reproduce the above copyright
##   notice, this list of conditions and the following disclaimer in
##   the documentation and/or other materials provided with the
##   distribution.
##
## 3. Neither the name of the copyright holder nor the names of its
##   contributors may be used to endorse or promote products derived
##   from this software without specific prior written permission.
##
## THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
## "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
## LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS
## FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE
## COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT,
## INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING,
## BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
## LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
## CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT
## LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN
## ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
## POSSIBILITY OF SUCH DAMAGE.

import wx
from cockpit.gui.dialogs.experiment import experimentConfigPanel
from cockpit.gui.guiUtils import EVT_COCKPIT_VALIDATION_ERROR

class SingleSiteExperimentDialog(wx.Dialog):
    def __init__(self, parent):
        super().__init__(parent, title="Strauss Lab Single-Site Experiment", style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.SetExtraStyle(wx.WS_EX_VALIDATE_RECURSIVELY)
        self.Bind(EVT_COCKPIT_VALIDATION_ERROR, self.onValidationError)

        self.sizer = wx.BoxSizer(wx.VERTICAL)

        self.panel = experimentConfigPanel.ExperimentConfigPanel(self, resizeCallback=self.onExperimentPanelResize, resetCallback=self.onReset)
        self.sizer.Add(self.panel)

        self.buttonBox = wx.BoxSizer(wx.HORIZONTAL)

        button = wx.Button(self, -1, "Reset")
        button.SetToolTip(wx.ToolTip("Reload this window with all default values"))
        button.Bind(wx.EVT_BUTTON, self.onReset)
        self.buttonBox.Add(button, 0, wx.ALIGN_LEFT | wx.ALL, 5)

        self.buttonBox.Add((1, 1), 1, wx.EXPAND)

        button = wx.Button(self, wx.ID_CANCEL, "Cancel")
        self.buttonBox.Add(button, 0, wx.ALL, 5)

        preview_button = wx.Button(self, -1, "Preview Action Table")
        preview_button.SetToolTip(wx.ToolTip("Generate and preview the action table"))
        preview_button.Bind(wx.EVT_BUTTON, self.onPreview)
        self.buttonBox.Add(preview_button, 0, wx.ALL, 5)

        button = wx.Button(self, wx.ID_OK, "Start")
        button.SetToolTip(wx.ToolTip("Start the experiment"))
        button.Bind(wx.EVT_BUTTON, self.onStart)
        self.buttonBox.Add(button, 0, wx.ALL, 5)

        self.sizer.Add(self.buttonBox, 1, wx.EXPAND)

        self.statusbar = wx.StaticText(self, -1, name="status bar", style=wx.ALIGN_RIGHT | wx.ST_NO_AUTORESIZE)
        self.sizer.Add(self.statusbar, 0, wx.EXPAND)

        self.SetSizerAndFit(self.sizer)

    def onValidationError(self, evt):
        if getattr(evt, 'empty', False):
            self.statusbar.SetLabel("Missing value for %s." % evt.control.GetName())
        else:
            self.statusbar.SetLabel("Invalid value for %s." % evt.control.GetName())
        evt.control.SetBackgroundColour('red')
        evt.control.Refresh()
        ctrl = evt.control
        ctrl.Bind(wx.EVT_SET_FOCUS, lambda null: [ctrl.SetBackgroundColour(''), ctrl.Unbind(wx.EVT_SET_FOCUS)])

    def onExperimentPanelResize(self, panel):
        self.SetSizerAndFit(self.sizer)

    def onStart(self, event=None):
        self.statusbar.SetLabel('')
        if not self.Validate():
            return
        if self.panel.runExperiment():
            self.Hide()

    def onReset(self, event=None):
        self.sizer.Remove(self.panel)
        self.panel.Destroy()
        self.panel = experimentConfigPanel.ExperimentConfigPanel(self, resizeCallback=self.onExperimentPanelResize, resetCallback=self.onReset)
        self.sizer.Prepend(self.panel)
        self.sizer.Layout()
        self.Refresh()
        self.SetSizerAndFit(self.sizer)
        return self.panel

    def onPreview(self, event=None):
        self.statusbar.SetLabel('')
        if not self.Validate():
            return

        try:
            action_table = self.panel.runExperiment(generate_only=True)  # Generate actions without running the experiment
            preview_dialog = wx.Dialog(self, title="Action Table Preview", style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
            preview_sizer = wx.BoxSizer(wx.VERTICAL)

            action_text = wx.TextCtrl(preview_dialog, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.HSCROLL)
            action_text.SetValue(str(action_table))
            preview_sizer.Add(action_text, 1, wx.EXPAND | wx.ALL, 5)

            close_button = wx.Button(preview_dialog, wx.ID_OK, "Close")
            preview_sizer.Add(close_button, 0, wx.ALIGN_CENTER | wx.ALL, 5)

            preview_dialog.SetSizer(preview_sizer)
            preview_dialog.SetSize((300,600))
            preview_dialog.Centre()
            preview_dialog.ShowModal()
            preview_dialog.Destroy()
        except Exception as e:
            wx.MessageBox(f"Error generating action table: {e}", "Error", wx.OK | wx.ICON_ERROR)

dialog = None

def showDialog(parent):
    global dialog
    if not dialog:
        dialog = SingleSiteExperimentDialog(parent)
    dialog.Show()
