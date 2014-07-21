#!/usr/bin/env python
import sys, os, subprocess, psutil, json, socket, tempfile
from PySide.QtGui import QApplication, QFileDialog, QWidget, QMessageBox, QIcon, QPixmap
from PySide.QtCore import QFile, Qt
from PySide.QtUiTools import QUiLoader

class Globals:
    mainWindow = None
    redPixmap = None
    redIcon = None
    greenPixmap = None
    greenIcon = None
    tangeloProcessCommands = set(['start', 'restart'])
    tangeloDefaultConfigPaths = [
        '/etc/tangelo.conf',
        os.path.expanduser('~/.config/tangelo/tangelo.conf'),
        '/usr/share/tangelo/conf/tangelo.conf.local'
    ]
    tangeloPath = None
    pythonPath = None
    
    @staticmethod
    def load():
        Globals.redPixmap = QPixmap('ui/images/indicators/red.png')
        Globals.redIcon = QIcon('ui/images/indicators/red.png')
        Globals.greenPixmap = QPixmap('ui/images/indicators/green.png')
        Globals.greenIcon = QIcon('ui/images/indicators/green.png')
        Globals.findTangelo()
    
    @staticmethod
    def criticalError(message):
        msgBox = QMessageBox()
        msgBox.setIcon(QMessageBox.Critical)
        msgBox.setText(message)
        return msgBox.exec_()
    
    @staticmethod
    def findTangelo():
        infile = QFile('ui/find_tangelo.ui')
        infile.open(QFile.ReadOnly)
        loader = QUiLoader()
        dialog = loader.load(infile, None)
        infile.close()
        
        if sys.platform.startswith('win'):
            Globals.pythonPath = subprocess.Popen(['where', 'python'], stdout=subprocess.PIPE).communicate()[0].strip()
            Globals.tangeloPath = subprocess.Popen(['where', 'tangelo'], stdout=subprocess.PIPE).communicate()[0].strip()
        else:
            Globals.pythonPath = subprocess.Popen(['which', 'python'], stdout=subprocess.PIPE).communicate()[0].strip()
            Globals.tangeloPath = subprocess.Popen(['which', 'tangelo'], stdout=subprocess.PIPE).communicate()[0].strip()
        
        if os.path.exists(Globals.pythonPath):
            dialog.pythonPathBox.setText(Globals.pythonPath)
        if os.path.exists(Globals.tangeloPath):
            dialog.tangeloPathBox.setText(Globals.tangeloPath)
        
        def pythonBrowse():
            path = QFileDialog.getOpenFileName(dialog, u"Find python", dialog.pythonPathBox.text())[0]
            if path != '':
                dialog.pythonPathBox.setText(path)
        
        def tangeloBrowse():
            path = QFileDialog.getOpenFileName(dialog, u"Find tangelo", dialog.tangeloPathBox.text())[0]
            if path != '':
                dialog.tangeloPathBox.setText(path)
        
        def cancel():
            dialog.hide()
            sys.exit()
        
        def ok():
            Globals.pythonPath = os.path.expanduser(dialog.pythonPathBox.text())
            Globals.tangeloPath = os.path.expanduser(dialog.tangeloPathBox.text())
            
            if not os.path.exists(Globals.pythonPath):
                Globals.criticalError("Sorry, that python interpreter doesn't exist.")
                return
            if not os.path.exists(Globals.tangeloPath):
                Globals.criticalError("Sorry, that tangelo executable doesn't exist.")
                return
            
            Globals.mainWindow = Overview()
            Globals.mainWindow.refresh()
            dialog.hide()
        dialog.show()
        
        dialog.tangeloBrowse.clicked.connect(tangeloBrowse)
        dialog.pythonBrowse.clicked.connect(pythonBrowse)
        dialog.cancelButton.clicked.connect(cancel)
        dialog.okButton.clicked.connect(ok)

class ManagerHelper(QWidget):
    # Sneaky way to override a virtual function on a loaded .ui widget
    # ... according to the docs, this is how it should be done, but
    # it still isn't working...
    def closeEvent(self, event):
        pid = self.windowTitle()
        print self, 'hi', pid
        '''self.manager = None
        
        # If no process is running, remove our widget from the overview as well;
        # we're done
        if self.pid == None:
            Globals.mainWindow.removeDeadProcess(self)'''
        
        event.accept()

class Process:
    def __init__(self, pid=None, configPath=None, nonDaemonProcess=None):
        self.pid = pid
        self.configPath = configPath
        assert self.pid != None or self.configPath != None
        self.nonDaemonProcess = nonDaemonProcess
        self.widget = None
        self.manager = None
        self.err = None
        
        self.createWidget()
    
    def createWidget(self):
        # Override the existing widget
        # TODO: Do I need to delete anything explicitly?
        infile = QFile('ui/process_widget.ui')
        infile.open(QFile.ReadOnly)
        loader = QUiLoader()
        self.widget = loader.load(infile, Globals.mainWindow.window)
        infile.close()
        
        self.updateWidget(True)
    
    def updateWidget(self, wireConnections=False):
        if self.pid == None:
            # We're not running...
            self.runningStatus = 'not running'
            self.widget.indicator.setPixmap(Globals.redPixmap)
            
            # Close my temporary log file if they exist
            if self.err != None:
                self.err.close()
            
            # Load up my configuration file
            self.config = Globals.mainWindow.loadConfig(self.configPath)
            
            # Set the widget fields to blank except configLabel
            self.widget.groupBox.setTitle('(process not running)')
            self.widget.pidLabel.setText('---')
            self.widget.statusLabel.setText(self.runningStatus)
            self.widget.interfaceLabel.setText('---')
            self.widget.logLabel.setText('---')
            self.widget.rootLabel.setText('---')
        else:
            # Collect info about the process:
            
            # Ask tangelo where our config file is
            if self.configPath == None:
                self.configPath = subprocess.Popen( \
                    [Globals.pythonPath, Globals.tangeloPath, 'status', '--pid', str(self.pid), '--attr', 'config'], \
                    stdout=subprocess.PIPE).communicate()[0].strip()
                if not os.path.exists(self.configPath):
                    # This is the odd scenario where a non-daemonized
                    # instance was running before tangelo-wrapper started...
                    # see if a config file was specified:
                    cmdline = psutil.Process(pid=int(self.pid)).cmdline()
                    if '-c' in cmdline:
                        self.configPath = cmdline[cmdline.index('-c') + 1]
                    else:
                        for p in Globals.tangeloDefaultConfigPaths:
                            if os.path.exists(p):
                                self.configPath = p
                                break
                assert os.path.exists(self.configPath)
                        
            # Load the configuration stored in the file
            self.config = Globals.mainWindow.loadConfig(self.configPath)
            
            # How are we running?
            if self.nonDaemonProcess == None:
                self.config['daemonize'] = True
                self.runningStatus = (subprocess.Popen( \
                [Globals.pythonPath, Globals.tangeloPath, 'status', '--pid', str(self.pid), '--attr', 'status'], \
                stdout=subprocess.PIPE).communicate()[0].strip())
                
                # Override any other fields with the current state
                interface = subprocess.Popen( \
                    [Globals.pythonPath, Globals.tangeloPath, 'status', '--pid', str(self.pid), '--attr', 'interface'], \
                    stdout=subprocess.PIPE).communicate()[0].split(':')
                
                self.config['hostname'] = interface[0].strip()
                self.config['port'] = int(interface[1])
                
                self.config['logdir'] = os.path.split(subprocess.Popen( \
                    [Globals.pythonPath, Globals.tangeloPath, 'status', '--pid', str(self.pid), '--attr', 'log'], \
                    stdout=subprocess.PIPE).communicate()[0].strip())[0]
                self.config['root'] = subprocess.Popen( \
                    [Globals.pythonPath, Globals.tangeloPath, 'status', '--pid', str(self.pid), '--attr', 'root'], \
                    stdout=subprocess.PIPE).communicate()[0].strip()
                
                self.err = None
            else:
                assert not sys.platform.startswith('win')
                self.config['daemonize'] = False
                self.runningStatus = 'running (not daemonized)'
                
                if self.err == None:
                    self.err = tempfile.NamedTemporaryFile('wb')
            
            if self.runningStatus.startswith('running'):
                self.widget.indicator.setPixmap(Globals.greenPixmap)
            else:
                self.widget.indicator.setPixmap(Globals.redPixmap)
            
            # Display info in our widget
            self.widget.groupBox.setTitle(str(self.pid))
            self.widget.pidLabel.setText(str(self.pid))
            self.widget.statusLabel.setText(self.runningStatus)
            self.widget.interfaceLabel.setText(self.config['hostname'] + ":" + str(self.config['port']))
            self.widget.configLabel.setText(self.configPath)
            self.widget.logLabel.setText(os.path.join(self.config['logdir'], 'tangelo.log'))
            self.widget.rootLabel.setText(self.config['root'])
        
        # Connect button events
        if wireConnections:
            self.widget.manageButton.clicked.connect(self.createManager)
            # TODO: Button to wrap as standalone app or VM
        
        # Update our manager if it exists
        if self.manager != None:
            self.updateManager()
        
    def createManager(self):
        if self.manager != None:
            self.manager.show()
            self.updateManager()
        else:
            # Create the window
            infile = QFile('ui/process_manager.ui')
            infile.open(QFile.ReadOnly)
            loader = QUiLoader()
            # This isn't working...
            loader.registerCustomWidget(ManagerHelper)
            self.manager = loader.load(infile, None)
            infile.close()
            
            self.updateManager(True)
    
    def updateManager(self, wireConnections=False):
        if self.pid == None:
            self.manager.setWindowTitle(self.configPath + " (pid: ---)")
            self.manager.setWindowIcon(Globals.redIcon)
            # leave all the fields as they are, but change the button text
            self.manager.restartButton.setText("Save and Start")
            self.manager.stopButton.setEnabled(False)
        else:
            # Populate the fields from our config object
            self.manager.setWindowTitle(self.configPath + " (pid: " + str(self.pid) + ")")
            if self.runningStatus.startswith('running'):
                self.manager.setWindowIcon(Globals.greenIcon)
            else:
                self.manager.setWindowIcon(Globals.redIcon)
            self.manager.hostnameField.setText(self.config['hostname'])
            self.manager.portField.setValue(self.config['port'])
            self.manager.rootField.setText(self.config['root'])
            self.manager.logdirField.setText(self.config['logdir'])
            self.manager.vtkField.setText(self.config['vtkpython'])
            if self.config['drop_privileges']:
                self.manager.drop_privilegesCheckBox.setChecked(Qt.Checked)
                self.manager.drop_privilegesExtras.setEnabled(True)
            else:
                self.manager.drop_privilegesCheckBox.setChecked(Qt.Unchecked)
                self.manager.drop_privilegesExtras.setEnabled(False)
            self.manager.userField.setText(self.config['user'])
            self.manager.groupField.setText(self.config['group'])
            self.manager.daemonizeCheckBox.setChecked(Qt.Checked if self.config['daemonize'] else Qt.Unchecked)
            if sys.platform.startswith('win'):
                assert not self.config['daemonize']
                self.manager.daemonizeCheckBox.setEnabled(False)
            self.manager.access_authCheckBox.setChecked(Qt.Checked if self.config['access_auth'] else Qt.Unchecked)
            self.manager.restartButton.setText("Save and Restart")
            self.manager.stopButton.setEnabled(True)
            
            # Show the relevant log file (just the console output if not a daemon)
            logText = ""
            if self.nonDaemonProcess != None:
                logText += "stderr:\n-------\n"
                infile = open(self.err.name, 'rb')
                logText += infile.read()
                infile.close()
            else:
                logPath = os.path.join(self.config['logdir'], 'tangelo.log')
                logText += logPath + ":\n" + "".join("-" for x in xrange(len(logPath) + 1)) + "\n"
                infile = open(logPath, 'rb')
                logText += infile.read()
                infile.close()
            self.manager.logBrowser.setPlainText(logText)
        
        if wireConnections:
            self.manager.drop_privilegesCheckBox.stateChanged.connect(self.togglePrivileges)
            self.manager.browseRoot.clicked.connect(self.browseRoot)
            self.manager.browseLogdir.clicked.connect(self.browseLogdir)
            self.manager.browseVtk.clicked.connect(self.browseVtk)
            
            self.manager.stopButton.clicked.connect(self.stop)
            self.manager.restartButton.clicked.connect(self.restart)
            self.manager.cancelButton.clicked.connect(self.manager.close)
        self.manager.show()
    
    def updateConfig(self):
        assert self.manager != None
        self.config['hostname'] = self.manager.hostnameField.text()
        self.config['port'] = self.manager.portField.value()
        self.config['root'] = self.manager.rootField.text()
        self.config['logdir'] = self.manager.logdirField.text()
        self.config['vtkpython'] = self.manager.vtkField.text()
        self.config['drop_privileges'] = self.manager.drop_privilegesCheckBox.checkState() == Qt.Checked
        self.config['user'] = self.manager.userField.text()
        self.config['group'] = self.manager.groupField.text()
        self.config['daemonize'] = self.manager.daemonizeCheckBox.checkState() == Qt.Checked
        assert not sys.platform.startswith('win') or not self.config['daemonize']
        self.config['access_auth'] = self.manager.access_authCheckBox.checkState() == Qt.Checked
        Globals.mainWindow.saveConfig(self.config, self.configPath)
    
    def togglePrivileges(self):
        if self.manager.drop_privilegesCheckBox.checkState() == Qt.Checked:
            self.manager.drop_privilegesExtras.setEnabled(True)
        else:
            self.manager.drop_privilegesExtras.setEnabled(False)
    
    def browseRoot(self):
        path = QFileDialog.getExistingDirectory(self.manager, u"Choose the root directory", self.manager.rootField.text())[0]
        if path != '':
            self.manager.rootField.setText(path)
    
    def browseLogdir(self):
        path = QFileDialog.getExistingDirectory(self.manager, u"Choose the log directory", self.manager.logdirField.text())[0]
        if path != '':
            self.manager.logdirField.setText(path)
    
    def browseVtk(self):
        path = QFileDialog.getOpenFileName(self.manager, u"Where is vtkpython?", self.manager.vtkField.text())[0]
        if path != '':
            self.manager.vtkField.setText(path)
    
    def stop(self):
        self.updateConfig()
        Globals.mainWindow.issueTangeloCommand([Globals.pythonPath, Globals.tangeloPath, 'stop', '--pid', str(self.pid), '--verbose'], self)
    
    def restart(self):
        # Corner case: we can't change the daemonize flag while a daemon is
        # running, or tangelo enters a weird state. If we're trying to do this,
        # we need to stop it separately before we mess with anything
        if not self.config['daemonize'] and self.pid != None:
            Globals.mainWindow.issueTangeloCommand([Globals.pythonPath, Globals.tangeloPath, 'stop', '--pid', str(self.pid), '--verbose'], self)
        
        self.updateConfig()
        
        # handles start or restart
        if self.pid == None:
            Globals.mainWindow.issueTangeloCommand([Globals.pythonPath, Globals.tangeloPath, 'start', '-c', self.configPath, '--verbose'], self)
        else:
            Globals.mainWindow.issueTangeloCommand([Globals.pythonPath, Globals.tangeloPath, 'restart', '--pid', str(self.pid), '-c', self.configPath, '--verbose'], self)

class Overview:
    def __init__(self):
        # Load UI files
        infile = QFile("ui/overview.ui")
        infile.open(QFile.ReadOnly)
        loader = QUiLoader()
        self.window = loader.load(infile, None)
        infile.close()
        
        self.processes = {}
        
        # Events
        self.window.refreshButton.clicked.connect(self.refresh)
        self.window.startButton.clicked.connect(self.findOrSaveConfig)
        self.window.show()
    
    def refresh(self, clearOutputOnSuccess=True):
        layout = self.window.scrollContents.layout()
        
        knownPids = set(self.processes.keys())
        daemonPids = set(self.getDaemonPids())
        allProcesses = self.getAllTangeloProcesses()
        nonDaemonPids = set(allProcesses.keys()).difference(daemonPids)
        
        # remove widgets for processes that aren't running
        # and don't have dialogs open
        for pid in knownPids.difference(daemonPids, nonDaemonPids):
            if self.processes[pid].manager == None or not self.processes[pid].manager.isVisible():
                self.removeDeadProcess(self.processes[pid])
                del self.processes[pid]
        
        # add widgets for daemon processes that we haven't seen before
        for pid in daemonPids.difference(knownPids):
            self.processes[pid] = Process(pid)
            layout.addWidget(self.processes[pid].widget)
        
        # add widgets for non-daemon processes that we haven't seen before
        for pid in nonDaemonPids.difference(knownPids):
            self.processes[pid] = Process(pid, nonDaemonProcess=allProcesses[pid])
            layout.addWidget(self.processes[pid].widget)
        
        if len(self.processes) == 0:
            self.window.consoleOutput.setPlainText('No tangelo instances are running.')
        elif clearOutputOnSuccess:
            self.window.consoleOutput.setPlainText('')
    
    def getDaemonPids(self):
        try:
            status = subprocess.Popen([Globals.pythonPath, Globals.tangeloPath,'status','--pids'], stderr=subprocess.PIPE).communicate()[1]
            
            if status.startswith('no tangelo instances'):
                return []
            else:
                return [x.strip() for x in status.split('\n')[0].split(':')[1].split(',')]
        except OSError as e:
            self.communicationAlert(e.strerror)
    
    def getAllTangeloProcesses(self):
        byPid = {}
        for p in psutil.process_iter():
            try:
                cmdline = p.cmdline()
                # TODO: this is a really hacky way to find all tangelo instances
                if len(cmdline) >= 3 and 'tangelo' in cmdline[1] and cmdline[2] in Globals.tangeloProcessCommands:
                    byPid[str(p.pid)] = p
            except psutil.AccessDenied:
                continue
        return byPid
    
    def findOrSaveConfig(self):
        infile = QFile('ui/config_path.ui')
        infile.open(QFile.ReadOnly)
        loader = QUiLoader()
        dialog = loader.load(infile, self.window)
        infile.close()
        
        def browse():
            path = QFileDialog.getSaveFileName(dialog, u"Choose or create a configuration file", dialog.pathBox.text())[0]
            if path != '':
                dialog.pathBox.setText(path)
        
        def cancel():
            dialog.hide()
        
        def ok():
            autodetectPort = dialog.autodetect.checkState() == Qt.Checked
            configPath = os.path.expanduser(dialog.pathBox.text())
            dialog.hide()
            self.start(configPath, autodetectPort)
        
        dialog.show()
        dialog.pathBox.setText(os.path.expanduser('~/.config/tangelo/tangelo.conf'))
        
        dialog.browseButton.clicked.connect(browse)
        dialog.cancelButton.clicked.connect(cancel)
        dialog.okButton.clicked.connect(ok)
    
    def start(self, path, autodetectPort=True):
        if os.path.exists(path):
            config = self.loadConfig(path)
        else:
            config = {
                'hostname' : 'localhost',
                'port' : 8080,
                'root' : sys.prefix + '/share/tangelo/web',
                'logdir' : os.path.expanduser('~/.config/tangelo'),
                'vtkpython' : '',
                'drop_privileges' : True,
                'user' : 'nobody',
                'group' : 'nobody',
                'daemonize' : True,
                'access_auth' : True
            }
        if autodetectPort:
            # Find an open socket
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.bind(('',0))
            config['port'] = s.getsockname()[1]
            s.close()
        try:
            self.saveConfig(config, path)
        except IOError as e:
            self.window.consoleOutput.setPlainText("Couldn't save " + path + ":" + e.strerror)
            return
        
        if sys.platform.startswith('win'):
            config['daemonize'] = False
        proc = Process(configPath=path)
        self.issueTangeloCommand([Globals.pythonPath, Globals.tangeloPath, 'start', '-c', path, '--verbose'], proc)
        self.window.scrollContents.layout().addWidget(proc.widget)
    
    def issueTangeloCommand(self, command, process):
        output = ""
        try:
            # We don't want to store the process by its old pid anymore
            if process.pid != None:
                del self.processes[process.pid]
            
            # If the process was already running (not as a daemon),
            # we need to kill it
            if process.nonDaemonProcess != None:
                assert 'start' not in command
                output += "Killing pid " + str(process.pid) + "...\n\n"
                process.nonDaemonProcess.kill()
                process.nonDaemonProcess = None
                if 'stop' in command:
                    # Clear our temporary stderr storage
                    process.err.close()
                    process.err = None
            
            output += " ".join(command)
            
            if 'stop' not in command:
                # How are we starting up a new process (or are we)?
                if not process.config['daemonize']:
                    if process.err == None:
                        process.err = tempfile.NamedTemporaryFile('wb')
                    process.nonDaemonProcess = subprocess.Popen(command, stderr=process.err)
                    process.pid = process.nonDaemonProcess.pid
                else:
                    oldPids = self.processes.keys()
                    tangeloProcess = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    output += '\n\n' + '\n\n'.join(tangeloProcess.communicate())
                    process.nonDaemonProcess = None
                    newPids = self.getDaemonPids()
                    
                    foundNewPid = False
                    for p in newPids:
                        if not p in oldPids:
                            foundNewPid = True
                            process.pid = p
                            break
                    assert foundNewPid
            else:
                tangeloProcess = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                output += '\n\n'.join(tangeloProcess.communicate())
                process.pid = None
            
            # If we started a new process, store it by its pid,
            # otherwise remove it if its manager isn't open
            if process.pid != None:
                self.processes[process.pid] = process
            
            #TODO: the call to isVisible() causes a segfault...
            #elif process.manager == None or not process.manager.isVisible():
            #    self.removeDeadPid(process.pid)
            
            process.updateWidget()
            self.window.consoleOutput.setPlainText(output)
        except OSError as e:
            self.communicationAlert(e.strerror)
    
    def removeDeadProcess(self, process):
        self.window.scrollContents.layout().removeWidget(process.widget)
        process.widget.deleteLater()
    
    def loadConfig(self, configPath):
        infile = open(configPath, 'rb')
        text = ""
        for line in infile:
            if not line.strip().startswith("//"):
                text += line
        infile.close()
        
        config = json.loads(text)
        
        # populate with the existing / default state if it doesn't already exist
        config['hostname'] = config.get('hostname', 'localhost')
        config['port'] = int(config.get('port', 8080))
        config['root'] = os.path.expanduser(config.get('root', sys.prefix + '/share/tangelo/web'))
        config['logdir'] = os.path.expanduser(config.get('logdir', '~/.config/tangelo'))
        config['vtkpython'] = config.get('vtkpython', "")
        config['drop_privileges'] = str(config.get('drop_privileges', 'true')).lower() == 'true'
        config['user'] = config.get('user', "nobody")
        config['group'] = config.get('group', "nobody")
        config['daemonize'] = str(config.get('daemonize', 'true')).lower() == 'true'
        config['access_auth'] = str(config.get('access_auth', 'true')).lower() == 'true'
        
        return config
    
    def saveConfig(self, config, configPath):
        for key,value in config.items():
            if value == '':
                del config[key]
        
        if config['drop_privileges'] == False:
            if config.has_key('user'):
                del config['user']
            if config.has_key('group'):
                del config['group']
        
        outfile = open(configPath, 'wb')
        outfile.write("// Tangelo config file auto-generated by tangelo-wrapper\n")
        outfile.write(json.dumps(config, separators=[", ",": "], indent=4))
        outfile.close()
    
    def communicationAlert(self, message):
        sys.exit(Globals.criticalError("Sorry, there was an error communicating with tangelo:\n\n" + message))

if __name__ == '__main__':
    app = QApplication(sys.argv)
    Globals.load()
    exitCode = app.exec_()
    del Globals.mainWindow
    sys.exit(exitCode)