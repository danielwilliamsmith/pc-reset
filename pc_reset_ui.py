import configparser
import datetime
import RPi.GPIO as GPIO
import logging
import os
import sys
import time

from logging.handlers import RotatingFileHandler
from PyQt5.QtCore import Qt, QSettings, QThread, QTimer
from PyQt5.QtWidgets import (QApplication, QFormLayout, QFrame, QLabel, QLineEdit, QMainWindow, QPlainTextEdit,
                             QPushButton, QSplitter, QVBoxLayout, QWidget)  

class MyLoggerWidget(RotatingFileHandler):
    """
    The purpose of this class is to log messages to the GUI whenever a message is written
    to the normal log file.
    """
    def __init__(self, parent, name):
        # Initialize a RotatingFileHandler.
        self.log_name = name.lower().replace(" ","_")
        super().__init__('{}_log.log'.format(self.log_name), mode='a', maxBytes=5*1024*1024,
                        backupCount=2, encoding=None, delay=0)

        # A read only QPlainTextEdit is used to display log messages as they
        # are logged.
        self.widget = QPlainTextEdit(parent)
        self.widget.setReadOnly(True)

    def emit(self, record):
        """Overrides emit for RotatingFileHandler to log message to the GUI."""
        # Log the message to the GUI.
        msg = self.format(record)
        self.widget.appendPlainText(msg)

        # Still want RotatingFileHandler emit to execute.
        super(MyLoggerWidget, self).emit(record)

class PcResetMainWindow(QMainWindow):
    """Handles the creation of the GUI and the logic underlying logic."""

    def generate_timestamp(self):
        """Returns a timestamp of the current time."""
        ts = time.time()
        st = datetime.datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')
        return st

    def __init__(self):
        super().__init__()
        self.__parse_config()
        self.__init_UI()
        self.__init_GPIO()
        self.__init_flags()
        self.__init_thread()
        self.__init_status_bar()

        # This needs to always be last.
        self.ping_timer = QTimer()
        self.ping_timer.timeout.connect(self.ping)
        self.ping_timer.start(self.config_wait_between_pings * 1000)

    def __init_flags(self):
        """Initializes flags that are used when monitoring pings and restarting the PC."""
        # Counter to keep track of consecutive ping failures.
        self.flag_ping_fail_count = 0

        # Flags to indicate when the PC is restarting.
        self.flag_restarting = False

    def __init_GPIO(self):
        """Initializes the Raspberry Pi GPIO pins."""
        # Using BCM mode because I think it is less confusing.
        GPIO.setmode(GPIO.BCM)

        # This output drives the relay.  The relay is always opened initially.
        GPIO.setup(self.config_relay_channel, GPIO.OUT)
        GPIO.output(self.config_relay_channel, GPIO.HIGH)

        # This input detects a switch press.  The switch is normally low.
        GPIO.setup(self.config_switch_channel, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
        GPIO.add_event_detect(self.config_switch_channel, GPIO.RISING, bouncetime=300)

    def __init_status_bar(self):
        """Initializes variables used for the main window's status bar message."""
        # Variables that will be displayed in the status bar.
        self.status_bar_ping_time = None
        self.status_bar_restarting = False
        self.status_bar_success_restart = 0
        self.status_bar_restart_time = None

    def __init_thread(self):
        """Initializes the thread used to handle the restart of the PC."""
        self.restart_thread = RestartThread(self.config_relay_channel,
                                            self.config_hold_power_switch,
                                            self.config_wait_before_shutdown)

    def __init_UI(self):
        """Creates UI elements."""
        self.__init_logger()
        
        ping_time_lbl = QLabel("Ping Time (Sec)")
        ping_time_le = QLineEdit()
        ping_time_le.setText(str(self.config_wait_between_pings))

        ping_fail_lbl = QLabel("Ping Fail Limit")
        ping_fail_le = QLineEdit()
        ping_fail_le.setText(str(self.config_ping_fails_needed_for_restart))

        wait_shutdown_lbl = QLabel("PC Shutdown Delay (Sec)")
        wait_shutdown_le = QLineEdit()
        wait_shutdown_le.setText(str(self.config_wait_before_shutdown))

        hold_power_lbl = QLabel("Power Switch Hold (Sec)")
        hold_power_le = QLineEdit()
        hold_power_le.setText(str(self.config_hold_power_switch))

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

        # Restore the main window to its previous state and size.
        self.settings = QSettings("DwsCo", "PcReset")
        if self.settings.value("geometry") == None:
            self.resize(1000, 500)
        else:
            self.restoreGeometry(self.settings.value("geometry"))

        self.setWindowTitle("Reset Yo PC")
        self.show()
  
    def __init_logger(self):
        """Initializes the logger."""
        # Formatter that includes a timestamp, log level and message.
        formatter = logging.Formatter(fmt='%(asctime)s %(levelname)-8s %(message)s',
                                      datefmt='%Y-%m-%d %H:%M:%S')

        # Using the custom log handler to write to the log file and the UI.
        self.log_widget = MyLoggerWidget(self, "pc reset")
        self.log_widget.setFormatter(formatter)

        # Stream handler to write to the console.
        screen_handler = logging.StreamHandler(stream=sys.stdout)
        screen_handler.setFormatter(formatter)

        # Finalize the actual logger and assign its handlers.
        self.logger = logging.getLogger(self.log_widget.log_name)
        self.logger.setLevel(logging.DEBUG)
        self.logger.addHandler(self.log_widget)
        self.logger.addHandler(screen_handler)

    def __parse_config(self):
        """Obtains initial values for configurable inputs from an .ini file."""
        # Read the config file.
        config_parser = configparser.RawConfigParser()
        config_parser.read('PC_reset_config.ini')

        # The approximate delay time between each ping attempt (SECONDS).
        self.config_wait_between_pings = int(config_parser.get('Timing',
                                                                'wait_between_pings',
                                                                fallback=5))

        # The number of pings that need to fail before the PC is considered dead.
        self.config_ping_fails_needed_for_restart = int(config_parser.get('Timing',
                                                                          'ping_fails_needed_for_restart',
                                                                          fallback=4))

        # Time to wait for the PC to shutdown (SECONDS).
        self.config_wait_before_shutdown = int(config_parser.get('Timing',
                                                                 'wait_before_shutdown',
                                                                 fallback=30))

        # Time to hold the power switch to trigger a restart of the PC (SECONDS).
        self.config_hold_power_switch = int(config_parser.get('Timing',
                                                              'hold_power_switch',
                                                              fallback=3))

        # Address of the PC to ping.
        self.config_hostname = config_parser.get('Comm',
                                                 'hostname', 
                                                 fallback=None)

        # Channel that the relay is connected to.  Relay closes on low output.
        self.config_relay_channel = int(config_parser.get('Channel',
                                                          'relay_channel',
                                                          fallback=25))

        # Channel that the switch is connected to.  Switch should be pull down.
        self.config_switch_channel = int(config_parser.get('Channel',
                                                           'switch_channel',
                                                           fallback=23))

    def ping(self):
        """
        Handles the pinging of the remote PC, initiating a restart,
        and confirming a successful restart.
        """ 
        # I am not going to ping at all if the thread that restarts the PC is running.
        if(not self.restart_thread.isRunning()):
            request_restart = False
            
            # Ping the PC.
            response = os.system("ping -c 1 " + self.config_hostname)
            self.status_bar_ping_time = self.generate_timestamp()
            self.__update_status_bar()
        
            # We are restarting the PC.
            if (self.flag_restarting == True):
                # Ping succeeded so assume that the restart was successful.
                if(response == 0):
                    self.logger.info("{} successfully restarted! Response = {}"
                                    .format(self.config_hostname, response))
                    self.flag_restarting = False
                    self.status_bar_restarting = False
                    self.flag_ping_fail_count = 0
                    self.status_bar_success_restart += 1
                    self.status_bar_restart_time = self.generate_timestamp()
                    self.__update_status_bar()
                
                # Ping failed so just log a message to track how long it takes to restart.
                else:
                    self.logger.info("{} is restarting but not back yet. Response = {}"
                                    .format(self.config_hostname, response))
            # We are not restarting.
            else:
                # The ping failed.
                if(response != 0):
                    # Do not restart the PC until the ping fails enough times consecutively.
                    if (self.flag_ping_fail_count < self.config_ping_fails_needed_for_restart):
                        self.flag_ping_fail_count += 1
                        self.logger.error("{} did not respond! Response = {} Consecutive fails = {} "
                                        .format(self.config_hostname, response, self.flag_ping_fail_count))
                    # The ping has failed enough times consecutively so restart the PC.
                    else:
                        request_restart = True
                        self.logger.error("{} is down, requesting auto restart! Response = {}"
                                        .format(self.config_hostname, response))
                # The ping succeeded so reset the consecutive number of failures.
                else:
                    self.flag_ping_fail_count = 0

            # Request a restart of the PC if the manual switch was pressed.
            if GPIO.event_detected(self.config_switch_channel):
                request_restart = True
                self.logger.info("{} manual restart request.".format(self.config_hostname))

            # Handle any pending restart requests.
            if(request_restart == True):
                self.logger.info("{} is restarting!".format(self.config_hostname))
                self.restart_thread.start()
                self.flag_restarting = True
                self.status_bar_restarting = True
                self.__update_status_bar()

    def __update_status_bar(self):
        """Updates the status bar with the current values in the status bar variables."""
        status_bar_message = "Last Ping: {}  |  Restarting: {}  |  Successful Restarts: {}  |  Last Restart: {}".format(
                            self.status_bar_ping_time,
                            self.status_bar_restarting,
                            self.status_bar_success_restart,
                            self.status_bar_restart_time)
        self.statusBar().showMessage(status_bar_message)

    def closeEvent(self, event):
        """Overrides the main windows closeEvent."""
        # Save the current size and position of the UI so that it can
        # be restored to the same state the next time it runs.
        self.settings.setValue("geometry", self.saveGeometry())

        # Try to open the relay before exiting so that the PC does not get stuck
        # in an endless restart.
        GPIO.output(self.config_relay_channel, GPIO.HIGH)
        GPIO.cleanup()

        self.logger.info('He be gone, he be outta here!')
        
        super(PcResetMainWindow, self).closeEvent(event)
            
class RestartThread(QThread):
    """Thread used to restart a PC via the power switch."""
    def __init__(self, relay_channel, hold_power_switch, wait_before_shutdown):
        QThread.__init__(self)
        self.relay_channel = relay_channel
        self.hold_power_switch = hold_power_switch
        self.wait_before_shutdown = wait_before_shutdown
        
    def __del__(self):
        self.wait()

    def run(self):    
        # Close relay to initiate power down.
        GPIO.output(self.relay_channel, GPIO.LOW)
        time.sleep(self.hold_power_switch)
        GPIO.output(self.relay_channel, GPIO.HIGH)

        # Wait a while to give the PC some time to shutdown.
        time.sleep(self.wait_before_shutdown)

        # Close the relay to initiate power up.
        GPIO.output(self.relay_channel, GPIO.LOW)
        time.sleep(self.hold_power_switch)
        GPIO.output(self.relay_channel, GPIO.HIGH)

        
if __name__ == '__main__':
    app = QApplication(sys.argv)
    pc_reset_main = PcResetMainWindow() 
    sys.exit(app.exec_())
