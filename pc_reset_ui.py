import configparser
import logging
import sys

from logging.handlers import RotatingFileHandler
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QApplication, QFormLayout, QFrame, QLabel, QLineEdit, QMainWindow, QPlainTextEdit,
                             QPushButton, QSplitter, QVBoxLayout, QWidget)  

class MyLoggerWidget(RotatingFileHandler):
    def __init__(self, parent, name):
        # This will be used as the name of the log file.
        self.log_name = name.lower().replace(" ","_")

        # Initialize the RotatingFileHandler.
        super().__init__('{}_log.log'.format(self.log_name), mode='a', maxBytes=5*1024*1024,
                        backupCount=2, encoding=None, delay=0)

        # A read only QPlainTextEdit is used to display log messages as they
        # are logged.
        self.widget = QPlainTextEdit(parent)
        self.widget.setReadOnly(True)

    def emit(self, record):
        # Still want RotatingFileHandler emit to execute.
        super(MyLoggerWidget, self).emit(record)
        
        # My overload of the emit method needs to write the log message to
        # the widget.
        msg = self.format(record)
        self.widget.appendPlainText(msg)

class PcResetMainWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self.parse_config()
        self.init_UI()

    def parse_config(self):
        config_parser = configparser.RawConfigParser()
        config_parser.read('PC_reset_config.ini')

        # The approximate delay time between each ping attempt (SECONDS).
        self.wait_between_pings = int(config_parser.get('Timing', 'wait_between_pings', fallback=5))

        # The number of pings that need to fail before the PC is considered dead.
        self.ping_fails_needed_for_restart = int(config_parser.get('Timing', 'ping_fails_needed_for_restart', fallback=4))

        # Time to wait for the PC to shutdown (SECONDS).
        self.wait_before_shutdown = int(config_parser.get('Timing', 'wait_before_shutdown', fallback=30))

        # Time to hold the power switch to trigger a restart of the PC (SECONDS).
        self.hold_power_switch = int(config_parser.get('Timing', 'hold_power_switch', fallback=3))

        # Address of the PC to ping.
        self.hostname = config_parser.get('Comm', 'hostname', fallback=None)

        # Channel that the relay is connected to.  Relay closes on low output.
        self.relay_channel = int(config_parser.get('Channel', 'relay_channel', fallback=25))

        # Channel that the switch is connected to.  Switch should be pull down.
        self.switch_channel = int(config_parser.get('Channel', 'switch_channel', fallback=23)) 
        

    def init_UI(self):
        self.__setup_logger()

        ping_time_lbl = QLabel("Ping Time (Sec)")
        ping_time_le = QLineEdit()
        ping_time_le.setText(str(self.wait_between_pings))

        ping_fail_lbl = QLabel("Ping Fail Limit")
        ping_fail_le = QLineEdit()
        ping_fail_le.setText(str(self.ping_fails_needed_for_restart))

        wait_shutdown_lbl = QLabel("PC Shutdown Delay (Sec)")
        wait_shutdown_le = QLineEdit()
        wait_shutdown_le.setText(str(self.wait_before_shutdown))

        hold_power_lbl = QLabel("Power Switch Hold (Sec)")
        hold_power_le = QLineEdit()
        hold_power_le.setText(str(self.hold_power_switch))

        timing_config_layout = QFormLayout()
        timing_config_layout.addRow(ping_time_lbl, ping_time_le)
        timing_config_layout.addRow(ping_fail_lbl, ping_fail_le)
        timing_config_layout.addRow(wait_shutdown_lbl, wait_shutdown_le)
        timing_config_layout.addRow(hold_power_lbl, hold_power_le)

        timing_config_widget = QWidget()
        timing_config_widget.setLayout(timing_config_layout)

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(timing_config_widget)
        splitter.addWidget(self.log_widget.widget)
        splitter.setSizes([250, 750])

        self.statusBar()
        self.setCentralWidget(splitter)
        self.move(300, 300)
        self.resize(1000, 500)
        self.setWindowTitle('Reset Yo PC Dawg')
        self.show()

    def __setup_logger(self):
        formatter = logging.Formatter(fmt='%(asctime)s %(levelname)-8s %(message)s',
                                  datefmt='%Y-%m-%d %H:%M:%S')
        
        self.log_widget = MyLoggerWidget(self, "pc reset")
        self.log_widget.setFormatter(formatter)

        screen_handler = logging.StreamHandler(stream=sys.stdout)
        screen_handler.setFormatter(formatter)
        
        self.logger = logging.getLogger(self.log_widget.log_name)
        self.logger.setLevel(logging.DEBUG)
        self.logger.addHandler(self.log_widget)
        self.logger.addHandler(screen_handler)
        
if __name__ == '__main__':
    app = QApplication(sys.argv)
    pc_reset_main = PcResetMainWindow() 
    sys.exit(app.exec_())
