import wx
import threading
import socket
import configparser
import queue
import subprocess
import psutil
import time
import os
import importlib.util

MAIN_SIZE = (600, 250)
DIALOG_SIZE = (700, 120)
COUNTDOWN = 3

# Fetch the root path dynamically
package_name = 'cockpit'
module_name = 'cockpit-pilot'

# Find the package path
spec = importlib.util.find_spec(package_name)
if spec is None:
    raise ImportError(f"Package '{package_name}' not found")

package_path = os.path.dirname(spec.origin)
pilot_path = os.path.join(package_path, module_name)

CONFIG_PATH = os.path.join(pilot_path, 'device_config.py')
DEPOT_PATH = os.path.join(pilot_path, 'depot.conf')
ICON_PATH = os.path.join(pilot_path, 'strauss_lab_logo_red.ico')

# Apply the task bar icon fix
import ctypes
myappid = 'Strauss Lab Cockpit v1.0'
ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)

class CockpitPilotApp(wx.App):
    def OnInit(self):
        self.frame = MainFrame(None, title="Strauss Lab", size=(400, 180))
        self.frame.Show()
        return True

class MainFrame(wx.Frame):
    def __init__(self, *args, **kw):
        super(MainFrame, self).__init__(*args, **kw)
        
        self.config_path = CONFIG_PATH
        self.depot_path = DEPOT_PATH
        self.output_queue = queue.Queue()
        self.is_window_open = True  # Track if the window is still open

        # Set the application icon
        icon = wx.Icon(ICON_PATH, wx.BITMAP_TYPE_ICO)
        self.SetIcon(icon)

        self.InitUI()
        self.SetSize(MAIN_SIZE)
        self.Centre()
        
    def InitUI(self):
        panel = wx.Panel(self)
        vbox = wx.BoxSizer(wx.VERTICAL)
        
        welcome_label = wx.StaticText(panel, label="\n Welcome to Cockpit! \n", style=wx.ALIGN_CENTER)
        welcome_label.SetFont(my_font(18))
        vbox.Add(welcome_label, flag=wx.ALL | wx.EXPAND, border=10)
        
        info_label = wx.StaticText(panel, label=" Get ready to explore the microscopic world! \n", style=wx.ALIGN_CENTER)
        info_label.SetFont(my_font(12))
        vbox.Add(info_label, flag=wx.ALL | wx.EXPAND, border=10)
        
        button_sizer = wx.BoxSizer(wx.HORIZONTAL)
        config_button = wx.Button(panel, label=" Change Config File Path... ")
        config_button.Bind(wx.EVT_BUTTON, self.OnChangeConfigPath)
        button_sizer.Add(config_button, flag=wx.RIGHT, border=10)

        depot_button = wx.Button(panel, label=" Open Depot Configuration ")
        depot_button.Bind(wx.EVT_BUTTON, self.OnOpenDepotFile)
        button_sizer.Add(depot_button, flag=wx.RIGHT, border=10)
        
        launch_button = wx.Button(panel, label="    Launch Cockpit    ")
        launch_button.Bind(wx.EVT_BUTTON, self.OnPrepareCockpit)
        button_sizer.Add(launch_button)
        
        vbox.Add(button_sizer, flag=wx.ALIGN_CENTER | wx.TOP | wx.BOTTOM, border=10)
        
        panel.SetSizer(vbox)

    def OnChangeConfigPath(self, event):
        dialog = DialogFrame(self, "Configuration Paths", size=DIALOG_SIZE)
        dialog.Show()

    def OnOpenDepotFile(self, event):
        process = subprocess.Popen(['notepad.exe', self.depot_path])
        # Monitor the Notepad process
        notepad_process = psutil.Process(process.pid)
        try:
            while not notepad_process.is_running() and not notepad_process.status() == psutil.STATUS_ZOMBIE:
                time.sleep(0.5)
        except psutil.NoSuchProcess:
            pass

    def CheckDependency(self, callback) -> None:
        def worker():
            result = self._check_dependency()
            wx.CallAfter(callback, result)
        
        threading.Thread(target=worker, daemon=True).start()

    def _check_dependency(self) -> bool:
        def show_warning(message):
            dialog = wx.MessageDialog(None, message, "Warning", wx.OK | wx.CANCEL | wx.ICON_WARNING)
            dialog.Centre()
            response = dialog.ShowModal()
            dialog.Destroy()
            return response == wx.ID_OK

        # Verify the presence of NI FPGA Host
        conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        config = configparser.ConfigParser()
        config.read(self.depot_path)
        ni_fpga_section = None
        for section in config.sections():
            if section.startswith('NI FPGA'):
                ni_fpga_section = section
                break

        if not ni_fpga_section:
            if not show_warning(f"The configuration file does not contain a section for 'NI FPGA'. Continuing without this may lead to incomplete or incorrect functionality.\n\nDo you wish to continue?"):
                return False

        try:
            ipaddress = config.get(ni_fpga_section, 'ipaddress')
            sendport = config.get(ni_fpga_section, 'sendport')
        except configparser.NoOptionError as e:
            if not show_warning(f"There is an issue with the configuration: {e}. This may prevent proper communication with the FPGA device.\n\nDo you wish to continue?"):
                return False

        try:
            conn.settimeout(0.1)  # Set timeout to avoid blocking
            conn.connect((ipaddress, int(sendport)))
            conn.close()
        except Exception as e:
            if not show_warning(f"Failed to connect to the NI FPGA at {ipaddress}: {sendport}. Ensure that the LabVIEW Host is running and that the IP address and port are correctly configured. Continuing without resolving this issue may lead to unexpected behavior.\n\nDo you wish to continue?"):
                return False

        return True

    
    def OnPrepareCockpit(self, event):
        def on_dependency_checked(result):
            if result:
                self.Hide()
                self.OpenOutputWindow()
                threading.Thread(target=self.LaunchDeviceServer, daemon=True).start()
                countdown_frame = CountdownFrame(self, "Countdown", COUNTDOWN, self, self.depot_path)  # Pass 'self' to CountdownFrame
                countdown_frame.Show(True)
        self.CheckDependency(on_dependency_checked)

    def OpenOutputWindow(self):
        self.output_window = OutputWindow(self, "Device Server Logging")
        self.PollOutputQueue()

    def PollOutputQueue(self):
        try:
            while not self.output_queue.empty():
                line = self.output_queue.get_nowait()
                if line:
                    wx.CallAfter(self.output_window.AppendText, line)
        except queue.Empty:
            pass
        finally:
            # Keep polling
            if self.is_window_open:
                wx.CallLater(100, self.PollOutputQueue)

    def LaunchDeviceServer(self):
        command = f"python -m microscope.device_server {self.config_path}"
        proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
        for line in iter(proc.stdout.readline, ''):
            self.output_queue.put(line)
            
        proc.stdout.close()
        proc.wait() 

class DialogFrame(wx.Frame):
    def __init__(self, parent, title, size):
        super(DialogFrame, self).__init__(parent, title=title, size=size)
        
        self.parent = parent

        # Set the application icon
        icon = wx.Icon(ICON_PATH, wx.BITMAP_TYPE_ICO)
        self.SetIcon(icon)

        self.InitUI()
        self.Centre()
        
    def InitUI(self):
        panel = wx.Panel(self)
        vbox = wx.BoxSizer(wx.VERTICAL)
        
        hbox1 = wx.BoxSizer(wx.HORIZONTAL)
        hbox2 = wx.BoxSizer(wx.HORIZONTAL)
        label1 = wx.StaticText(panel, label=" Enter Device Config Path: ")
        label2 = wx.StaticText(panel, label=" Enter Depot Config Path:  ")
        hbox1.Add(label1, flag=wx.RIGHT, border=8)
        hbox2.Add(label2, flag=wx.RIGHT, border=8)
        
        self.txtCtrl = wx.TextCtrl(panel, value=self.parent.config_path, style=wx.TE_RICH2)
        self.depotCtrl = wx.TextCtrl(panel, value=self.parent.depot_path, style=wx.TE_RICH2)
        
        # Ensure the text is fully visible
        self.txtCtrl.SetInsertionPointEnd()
        self.txtCtrl.SetSelection(-1, -1)  # Deselect text
        self.txtCtrl.ShowPosition(self.txtCtrl.GetLastPosition())
        
        self.depotCtrl.SetInsertionPointEnd()
        self.depotCtrl.SetSelection(-1, -1)  # Deselect text
        self.depotCtrl.ShowPosition(self.depotCtrl.GetLastPosition())

        hbox1.Add(self.txtCtrl, proportion=1)
        hbox2.Add(self.depotCtrl, proportion=1)
        
        vbox.Add(hbox1, flag=wx.EXPAND | wx.ALL, border=10)
        vbox.Add(hbox2, flag=wx.EXPAND | wx.ALL, border=10)
        
        # Create OK and Cancel buttons
        btnSizer = wx.BoxSizer(wx.HORIZONTAL)
        okBtn = wx.Button(panel, wx.ID_OK, "OK")
        cancelBtn = wx.Button(panel, wx.ID_CANCEL, "Cancel")
        btnSizer.Add(okBtn)
        btnSizer.Add(cancelBtn, flag=wx.LEFT, border=5)
        
        vbox.Add(btnSizer, flag=wx.ALIGN_CENTER | wx.TOP | wx.BOTTOM, border=10)

        panel.SetSizer(vbox)
        
        self.Bind(wx.EVT_BUTTON, self.OnOk, id=wx.ID_OK)
        self.Bind(wx.EVT_BUTTON, self.OnCancel, id=wx.ID_CANCEL)

    def OnOk(self, event):
        _config_path = self.txtCtrl.GetValue()
        _depot_path = self.depotCtrl.GetValue()
        self.parent.config_path = _config_path
        self.parent.depot_path = _depot_path
        self.Destroy()

    def OnCancel(self, event):
        self.Destroy()

class OutputWindow(wx.Frame):
    def __init__(self, parent, title):
        super(OutputWindow, self).__init__(parent, title=title, size=(500, 300))

        # Set the application icon
        icon = wx.Icon(ICON_PATH, wx.BITMAP_TYPE_ICO)
        self.SetIcon(icon)

        self.InitUI()
        self.Centre()
        self.Show()
        self.Bind(wx.EVT_CLOSE, self.OnClose)

    def InitUI(self):
        panel = wx.Panel(self)
        vbox = wx.BoxSizer(wx.VERTICAL)
        
        self.outputTxtCtrl = wx.TextCtrl(panel, style=wx.TE_MULTILINE | wx.TE_READONLY)
        vbox.Add(self.outputTxtCtrl, proportion=1, flag=wx.EXPAND | wx.ALL, border=10)
        
        panel.SetSizer(vbox)

    def AppendText(self, text):
        self.outputTxtCtrl.AppendText(text)

    def OnClose(self, event):
        # This method is called when the window is closed.
        # TERMINATE the entire application.
        parent = self.GetParent()
        parent.is_window_open = False  # Update the state to indicate the window is closed
        self.Destroy()
        wx.CallAfter(wx.GetApp().ExitMainLoop)

class CountdownFrame(wx.Frame):
    def __init__(self, parent, title, countdown_duration, main_frame_ref, depot_path):
        super(CountdownFrame, self).__init__(parent, title=title, size=(400, 180))
        self.main_frame_ref = main_frame_ref  # Store the reference to MainFrame
        self.countdown_duration = countdown_duration
        self.depot_path = depot_path
        self.InitUI()
        self.Centre()
        self.StartCountdown()
        
        # Set the application icon
        icon = wx.Icon(ICON_PATH, wx.BITMAP_TYPE_ICO)
        self.SetIcon(icon)

    def InitUI(self):
        self.panel = wx.Panel(self)
        self.timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.UpdateCountdown, self.timer)

        self.countdown_label = wx.StaticText(self.panel, label="", pos=(50, 50))
        font = wx.Font(14, wx.FONTFAMILY_SWISS, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD)
        self.countdown_label.SetFont(font)

    def StartCountdown(self):
        self.UpdateCountdown(None)
        self.timer.Start(1000)

    def UpdateCountdown(self, event):
        if self.countdown_duration > 0:
            self.countdown_label.SetLabel(f"Starting in {self.countdown_duration} seconds...")
            self.countdown_duration -= 1
        else:
            self.timer.Stop()
            self.Close(True)
            wx.CallAfter(self.LaunchCockpitMain)

    def LaunchCockpitMain(self):
        threading.Thread(target=self.cockpit_main, daemon=True).start()
        
    
    def cockpit_main(self):
        command = f"python -m cockpit --depot-file {self.depot_path}"
        proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
        
        for line in iter(proc.stdout.readline, ''):
            if self.main_frame_ref.is_window_open:  # Check if the window is still open
                wx.CallAfter(self.main_frame_ref.output_window.AppendText, line)
        
        proc.stdout.close()
        proc.wait()
        if proc.returncode != 0 and self.main_frame_ref.is_window_open:  # Check if the window is still open
            wx.CallAfter(wx.MessageBox, "Cockpit exited with an error.", "Error", wx.OK | wx.ICON_ERROR)

def my_font(size=10):
    '''             Example of USE: 

    text = wx.StaticText(panel, -1, 'my text', (20, 100))
    font = wx.Font(18, wx.DECORATIVE, wx.ITALIC, wx.NORMAL)
    text.SetFont(font)
    wx.Font has the following signature:
        x.Font(pointSize, family, style, weight, underline=False, faceName="", encoding=wx.FONTENCODING_DEFAULT)
        1: family can be:

            wx.DECORATIVE, wx.DEFAULT,wx.MODERN, wx.ROMAN, wx.SCRIPT or wx.SWISS.

        2: style can be:

            wx.NORMAL, wx.SLANT or wx.ITALIC.

        3: weight can be:

            wx.NORMAL, wx.LIGHT, or wx.BOLD
    '''
    return wx.Font(size, family=wx.DECORATIVE, style=wx.NORMAL, weight=wx.BOLD)

if __name__ == "__main__":
    app = CockpitPilotApp(False)
    app.MainLoop()
