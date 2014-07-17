#!/usr/bin/env python
import sys, os, subprocess, json, socket
from PySide.QtGui import QApplication, QFileDialog
from PySide.QtCore import QFile, Qt
from PySide.QtUiTools import QUiLoader

loader = None
mainWindow = None

def clearLayout(layout):
    if layout is not None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
            else:
                clearLayout(item.layout())

class ProcessManager:
    def __init__(self, config, pid, path):
        self.config = config
        self.pid = pid
        self.configPath = path
        
        # Show the UI
        infile = QFile('process.ui')
        infile.open(QFile.ReadOnly)
        self.window = loader.load(infile, mainWindow.window)
        infile.close()
        
        self.window.setWindowTitle(self.configPath + " (pid: " + self.pid + ")")
        self.window.hostnameField.setText(config['hostname'])
        self.window.portField.setValue(config['port'])
        self.window.rootField.setText(config['root'])
        self.window.logdirField.setText(config['logdir'])
        self.window.vtkField.setText(config['vtkpython'])
        if (config['drop_privileges'] == 'true'):
            self.window.drop_privilegesCheckBox.setChecked(Qt.Checked)
            self.window.drop_privilegesExtras.setEnabled(True)
        else:
            self.window.drop_privilegesCheckBox.setChecked(Qt.Unchecked)
            self.window.drop_privilegesExtras.setEnabled(False)
        self.window.userField.setText(config['user'])
        self.window.groupField.setText(config['group'])
        self.window.daemonizeCheckBox.setChecked(Qt.Checked if config['daemonize'] == 'true' else Qt.Unchecked)
        self.window.access_authCheckBox.setChecked(Qt.Checked if config['access_auth'] == 'true' else Qt.Unchecked)
        
        self.window.drop_privilegesCheckBox.stateChanged.connect(self.togglePrivileges)
        self.window.browseRoot.clicked.connect(self.browseRoot)
        self.window.browseLogdir.clicked.connect(self.browseLogdir)
        self.window.browseVtk.clicked.connect(lambda : self.browse(self.window.vtkField))
        self.window.stopButton.clicked.connect(self.stop)
        self.window.restartButton.clicked.connect(self.restart)
        
        self.window.show()
    
    def togglePrivileges(self):
        if self.window.drop_privilegesCheckBox.checkState() == Qt.Checked:
            self.window.drop_privilegesExtras.setEnabled(True)
        else:
            self.window.drop_privilegesExtras.setEnabled(False)
    
    def browseRoot(self):
        path = QFileDialog.getExistingDirectory(self.window, u"Choose the root directory", self.window.rootField.text())[0]
        if path != '':
            self.window.rootField.setText(path)
    
    def browseLogdir(self):
        path = QFileDialog.getExistingDirectory(self.window, u"Choose the log directory", self.window.logdirField.text())[0]
        if path != '':
            self.window.logdirField.setText(path)
    
    def browseVtk(self):
        path = QFileDialog.getOpenFileName(self.window, u"Where is vtkpython?", self.window.vtkField.text())[0]
        if path != '':
            self.window.vtkField.setText(path)    
    
    def updateConfig(self):
        self.config['hostname'] = self.window.hostnameField.text()
        self.config['port'] = self.window.portField.value()
        self.config['root'] = self.window.rootField.text()
        self.config['logdir'] = self.window.logdirField.text()
        self.config['vtkpython'] = self.window.vtkField.text()
        self.config['drop_privileges'] = 'true' if self.window.drop_privilegesCheckBox.checkState() == Qt.Checked else 'false'
        self.config['user'] = self.window.userField.text()
        self.config['group'] = self.window.groupField.text()
        self.config['daemonize'] = 'true' if self.window.daemonizeCheckBox.checkState() == Qt.Checked else 'false'
        self.config['access_auth'] = 'true' if self.window.access_authCheckBox.checkState() == Qt.Checked else 'false'
        mainWindow.saveConfig(self.config, self.configPath)
    
    def stop(self):
        self.updateConfig()
        if mainWindow.issueTangeloCommand(['tangelo', 'stop', '--pid', str(self.pid), '--verbose'], self.config['logdir']):
            self.window.restartButton.clicked.disconnect(self.restart)
            self.window.restartButton.clicked.connect(self.start)
            self.window.restartButton.setText('Save and Start')
            self.window.setWindowTitle(self.configPath + " (Not Running)")
        mainWindow.refresh(False)
    
    def restart(self):
        self.updateConfig()
        oldPids = mainWindow.pids
        if not mainWindow.issueTangeloCommand(['tangelo', 'restart', '-c', self.configPath, '--verbose'], self.config['logdir']):
            self.window.restartButton.clicked.disconnect(self.restart)
            self.window.restartButton.clicked.connect(self.start)
            self.window.restartButton.setText('Save and Start')
        mainWindow.refresh(False)
        for p in mainWindow.pids:
            if not p in oldPids:
                self.pid = p
                self.window.setWindowTitle(self.configPath + " (pid: " + self.pid + ")")
                break
    
    def start(self):
        self.updateConfig()
        oldPids = mainWindow.pids
        if mainWindow.issueTangeloCommand(['tangelo', 'start', '-c', self.configPath, '--verbose'], self.config['logdir']):
            self.window.restartButton.clicked.disconnect(self.start)
            self.window.restartButton.clicked.connect(self.restart)
            self.window.restartButton.setText('Save and Restart')
        mainWindow.refresh(False)
        for p in mainWindow.pids:
            if not p in oldPids:
                self.pid = p
                self.window.setWindowTitle(self.configPath + " (pid: " + self.pid + ")")
                break

class Process:
    def dummy(process):
        process.manageProcess()
    
    def __init__(self, pid):
        self.pid = pid
        
        # To clone the widget, I need to load it from the file
        # multiple times... there really isn't a more elegant way
        # to do this
        infile = QFile('overview_template.ui')
        infile.open(QFile.ReadOnly)
        self.widget = loader.load(infile, mainWindow.window)
        infile.close()
        
        # Collect and display info about the process
        self.widget.groupBox.setTitle(pid)
        self.widget.pidLabel.setText(pid)
        self.widget.statusLabel.setText(subprocess.Popen( \
            ['tangelo', 'status', '--pid', pid, '--attr', 'status'], \
            stdout=subprocess.PIPE).communicate()[0].strip())
        self.widget.interfaceLabel.setText(subprocess.Popen( \
            ['tangelo', 'status', '--pid', pid, '--attr', 'interface'], \
            stdout=subprocess.PIPE).communicate()[0].strip())
        self.configPath = subprocess.Popen( \
            ['tangelo', 'status', '--pid', pid, '--attr', 'config'], \
            stdout=subprocess.PIPE).communicate()[0].strip()
        self.widget.configLabel.setText(self.configPath)
        self.widget.logLabel.setText(subprocess.Popen( \
            ['tangelo', 'status', '--pid', pid, '--attr', 'log'], \
            stdout=subprocess.PIPE).communicate()[0].strip())
        self.widget.rootLabel.setText(subprocess.Popen( \
            ['tangelo', 'status', '--pid', pid, '--attr', 'root'], \
            stdout=subprocess.PIPE).communicate()[0].strip())
        
        # TODO: Don't know why connecting to self.manageProcess directly isn't working...
        self.widget.manageButton.clicked.connect(lambda : self.manageProcess(pid))
        # TODO: Button to bottle as standalone app or VM
        
    def manageProcess(self, pid):
        config = mainWindow.loadConfig(self.widget.configLabel.text())
        
        # Show the actual state of the instance instead of the defaults in the .conf file
        config['hostname'] = config.get('hostname', self.widget.interfaceLabel.text().split(':')[0])
        config['port'] = config.get('port', int(self.widget.interfaceLabel.text().split(':')[1]))
        config['root'] = config.get('root', self.widget.rootLabel.text())
        config['logdir'] = config.get('logdir', self.widget.logLabel.text())
        
        self.manager = ProcessManager(config, pid, self.configPath)

class Overview:
    def __init__(self):
        # Load UI files
        infile = QFile("overview.ui")
        infile.open(QFile.ReadOnly)
        self.window = loader.load(infile, None)
        infile.close()
        
        self.pids = []
        
        # Events
        self.window.refreshButton.clicked.connect(self.refresh)
        self.window.startButton.clicked.connect(self.findOrSaveConfig)
        
        self.window.show()
    
    def refresh(self, clearOutputOnSuccess=True):
        layout = self.window.scrollContents.layout()
        clearLayout(layout)
        
        self.pids = self.getPidList()
        
        if self.pids == None:
            return
        elif len(self.pids) == 0:
            self.window.consoleOutput.setPlainText('No tangelo instances are running.')
        else:
            # Populate with new panels
            for pid in self.pids:
                process = Process(pid)
                layout.addWidget(process.widget)
            if clearOutputOnSuccess:
                self.window.consoleOutput.setPlainText('')
    
    def getPidList(self):
        try:
            status = subprocess.Popen(['tangelo','status','--pids'], stderr=subprocess.PIPE).communicate()[1]
            
            if status.startswith('no tangelo instances'):
                return []
            else:
                return [x.strip() for x in status.split('\n')[0].split(':')[1].split(',')]
        except OSError as e:
            self.window.consoleOutput.setPlainText('Error communicating with tangelo: ' + e.strerror + "\n" + str(e))
            return None
    
    def findOrSaveConfig(self):
        infile = QFile('config.ui')
        infile.open(QFile.ReadOnly)
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
                'drop_privileges' : 'true',
                'user' : 'nobody',
                'group' : 'nobody',
                'daemonize' : 'true',
                'access_auth' : 'true'
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
        
        self.issueTangeloCommand(['tangelo', 'start', '-c', path, '--verbose'], config['logdir'])
        self.refresh(False)
    
    def issueTangeloCommand(self, command, logdir=None):
        try:
            launchProcess = subprocess.Popen(command, stderr=subprocess.PIPE)
            
            output = " ".join(command)
            output += "\n\n"
            output += launchProcess.communicate()[1]
            if logdir != None:
                output += "\n\ntangelo.log:\n-----------"
                logpath = os.path.join(logdir, 'tangelo.log')
                if not os.path.exists(logpath):
                    output += logpath + "doesn't exist."
                else:
                    infile = open(logpath, 'rb')
                    output += infile.read()
                    infile.close()
            self.window.consoleOutput.setPlainText(output)
        except OSError as e:
            self.window.consoleOutput.setPlainText('Error communicating with tangelo: ' + e.strerror)
            return False
        return True
    
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
        config['drop_privileges'] = config.get('drop_privileges', 'true').lower()
        config['user'] = config.get('user', "nobody")
        config['group'] = config.get('group', "nobody")
        config['daemonize'] = config.get('daemonize', 'true').lower()
        config['access_auth'] = config.get('access_auth', 'true').lower()
        
        return config
    
    def saveConfig(self, config, configPath):
        for key,value in config.items():
            if value == '':
                del config[key]
        
        if config['drop_privileges'] == 'false':
            if config.has_key('user'):
                del config['user']
            if config.has_key('group'):
                del config['group']
        
        outfile = open(configPath, 'wb')
        outfile.write("// Tangelo config file auto-generated by tangelo_wrapper.\n")
        outfile.write(json.dumps(config, separators=[", ",": "], indent=4))
        outfile.close()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    loader = QUiLoader()
    mainWindow = Overview()
    mainWindow.refresh()
    exitCode = app.exec_()
    del mainWindow
    sys.exit(exitCode)