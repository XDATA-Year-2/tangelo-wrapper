#!/usr/bin/env python
import sys, os, subprocess, json, socket
from PySide.QtGui import QApplication, QMessageBox, QFileDialog, QLineEdit
from PySide.QtCore import QFile, Qt
from PySide.QtUiTools import QUiLoader

loader = None
mainWindow = None

SOCKET = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

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
    def __init__(self, config):
        self.config = config
        
        # Show the UI
        infile = QFile('process.ui')
        infile.open(QFile.ReadOnly)
        self.window = loader.load(infile, None)
        infile.close()
        
        self.window.show()

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
        self.widget.configLabel.setText(subprocess.Popen( \
            ['tangelo', 'status', '--pid', pid, '--attr', 'config'], \
            stdout=subprocess.PIPE).communicate()[0].strip())
        self.widget.logLabel.setText(subprocess.Popen( \
            ['tangelo', 'status', '--pid', pid, '--attr', 'log'], \
            stdout=subprocess.PIPE).communicate()[0].strip())
        self.widget.rootLabel.setText(subprocess.Popen( \
            ['tangelo', 'status', '--pid', pid, '--attr', 'root'], \
            stdout=subprocess.PIPE).communicate()[0].strip())
        
        # TODO: Don't know why connecting to self.manageProcess directly isn't working...
        self.widget.manageButton.clicked.connect(lambda : Process.dummy(self))
        
    def manageProcess(self):
        config = mainWindow.loadConfig(self.widget.configLabel.text())
        
        # Show the actual state of the instance instead of the defaults in the .conf file
        config['hostname'] = config.get('hostname', self.widget.interfaceLabel.text().split(':')[0])
        config['port'] = config.get('port', int(self.widget.interfaceLabel.text().split(':')[1]))
        config['root'] = config.get('root', self.widget.rootLabel.text())
        config['logdir'] = config.get('logdir', self.widget.logLabel.text())
        
        self.manager = ProcessManager(config)

class Overview:
    def __init__(self):
        # Load UI files
        infile = QFile("overview.ui")
        infile.open(QFile.ReadOnly)
        self.window = loader.load(infile, None)
        infile.close()
        
        self.processes = []
        
        # Events
        self.window.refreshButton.clicked.connect(self.refresh)
        self.window.startButton.clicked.connect(self.findOrSaveConfig)
        
        self.window.show()
        '''
        self.window.quitButton.clicked.connect(self.window.close)
        self.window.addButton.clicked.connect(self.addGene)
        self.window.geneBox.editTextChanged.connect(self.editGene)
        self.window.speedSlider.valueChanged.connect(self.changeSpeed)
        self.window.timeSlider.valueChanged.connect(self.changeTime)
        
        self.window.addButton.setEnabled(False)
        
        self.window.showFullScreen()
        #self.window.show()
        
        # Start timer
        
        # Update timer
        self.timer = QTimer(self.window)
        self.timer.timeout.connect(self.nextFrame)
        self.timer.start(Viz.FRAME_DURATION)
        '''
    def refresh(self, clearOutputOnSuccess=True):
        try:
            status = subprocess.Popen(['tangelo','status','--pids'], stderr=subprocess.PIPE).communicate()[1]
            
            layout = self.window.scrollContents.layout()
            clearLayout(layout)
            
            self.processes = []
            
            if status.startswith('no tangelo instances'):
                self.window.consoleOutput.setPlainText('No tangelo instances are running.')
            else:
                
                # Populate with new panels
                for pid in status.split('\n')[0].split(':')[1].split(','):
                    process = Process(pid)
                    layout.addWidget(process.widget)
                if clearOutputOnSuccess:
                    self.window.consoleOutput.setPlainText('')
                    
        except OSError as e:
            self.window.consoleOutput.setPlainText('Error communicating with tangelo: ' + e.strerror)
            return
    
    def findOrSaveConfig(self):
        infile = QFile('config.ui')
        infile.open(QFile.ReadOnly)
        dialog = loader.load(infile, self.window)
        infile.close()
        
        def browse():
            path = QFileDialog.getSaveFileName(dialog, u"Choose or create a configuration file", dialog.pathBox.text())[0]
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
            SOCKET.bind(('',0))
            config['port'] = SOCKET.getsockname()[1]
            print config['port']
        try:
            self.saveConfig(config, path)
        except IOError as e:
            self.window.consoleOutput.setPlainText("Couldn't save " + path + ":" + e.strerror)
            return
        
        try:
            command = ['tangelo', 'start', '-c', path, '--verbose']
            launchProcess = subprocess.Popen(command, stderr=subprocess.PIPE)
            
            output = " ".join(command)
            output += "\n\n"
            output += launchProcess.communicate()[1]
            output += "\n\ntangelo.log:\n-----------"
            logpath = os.path.join(config['logdir'], 'tangelo.log')
            if not os.path.exists(logpath):
                output += logpath + "doesn't exist."
            else:
                infile = open(logpath, 'rb')
                output += infile.read()
                infile.close()
            self.window.consoleOutput.setPlainText(output)
        except OSError as e:
            self.window.consoleOutput.setPlainText(e.strerror)
        self.refresh(False)
    
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
        
        outfile = open(configPath, 'wb')
        outfile.write("// Tangelo config file auto-generated by tangelo_wrapper.\n")
        outfile.write(json.dumps(config, separators=[", ",": "], indent=4))
        outfile.close()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    loader = QUiLoader()
    mainWindow = Overview()
    mainWindow.refresh()
    sys.exit(app.exec_())