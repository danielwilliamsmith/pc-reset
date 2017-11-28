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
        # My overload of the emit method needs to write the log message to
        # the widget.
        msg = self.format(record)
        self.widget.appendPlainText(msg)

        # Still want RotatingFileHandler emit to execute.
        super(MyLoggerWidget, self).emit(record)

class PcResetMainWindow(QMainWindow):

    def __generate_timestamp(self):
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
        self.__ping_timer = QTimer()
        self.__ping_timer.timeout.connect(self.__ping)
        self.__ping_timer.start(self.__config_wait_between_pings * 1000)

    def __init_flags(self):
        # Counter to keep track of the number of consecutive ping
        # failures that have occurred prior to executing a restart.
        self.__flag_ping_fail_count = 0

        # Flags to indicate when the PC is restarting.
        self.__flag_restarting = False

    def __init_GPIO(self):
        # Using BCM mode because I think it is less confusing.
        GPIO.setmode(GPIO.BCM)

        # This output drives the relay.  The relay is always opened initially.
        GPIO.setup(self.__config_relay_channel, GPIO.OUT)
        GPIO.output(self.__config_relay_channel, GPIO.HIGH)

        # This input detects a switch press.  The switch is normally low.
        GPIO.setup(self.__config_switch_channel, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
        GPIO.add_event_detect(self.__config_switch_channel, GPIO.RISING, bouncetime=300)

    def __init_status_bar(self):
        # Variables that will be displayed in the status bar.
        self.__status_bar_ping_time = None
        self.__status_bar_restarting = False
        self.__status_bar_success_restart = 0
        self.__status_bar_restart_time = None

    def __init_thread(self):
        self.__restart_thread = RestartThread(self.__config_relay_channel,
                                              self.__config_hold_power_switch,
                                              self.__config_wait_before_shutdown)

    def __init_UI(self):
        self.__init_logger()
        
        ping_time_lbl = QLabel("Ping Time (Sec)")
        ping_time_le = QLineEdit()
        ping_time_le.setText(str(self.__config_wait_between_pings))

        ping_fail_lbl = QLabel("Ping Fail Limit")
        ping_fail_le = QLineEdit()
        ping_fail_le.setText(str(self.__config_ping_fails_needed_for_restart))

        wait_shutdown_lbl = QLabel("PC Shutdown Delay (Sec)")
        wait_shutdown_le = QLineEdit()
        wait_shutdown_le.setText(str(self.__config_wait_before_shutdown))

        hold_power_lbl = QLabel("Power Switch Hold (Sec)")
        hold_power_le = QLineEdit()
        hold_power_le.setText(str(self.__config_hold_power_switch))

        timing_config_layout = QFormLayout()
        timing_config_layout.addRow(ping_time_lbl, ping_time_le)
        timing_config_layout.addRow(ping_fail_lbl, ping_fail_le)
        timing_config_layout.addRow(wait_shutdown_lbl, wait_shutdown_le)
        timing_config_layout.addRow(hold_power_lbl, hold_power_le)

        timing_config_widget = QWidget()
        timing_config_widget.setLayout(timing_config_layout)

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(timing_config_widget)
        splitter.addWidget(self.__log_widget.widget)
        splitter.setSizes([250, 750])

        self.statusBar()
        self.setCentralWidget(splitter)

        # Restore the main window to its previous state and size.
        self.settings = QSettings("DwsCo", "PcReset")
        if self.settings.value("geometry") == None:
            self.resize(1000, 500)
        else:
            self.restoreGeometry(self.settings.value("geometry"))

        self.setWindowTitle("Reset Yo PC Dawg")
        self.show()
  
    def __init_logger(self):
        # Formatter that includes a timestamp, log level and message.
        formatter = logging.Formatter(fmt='%(asctime)s %(levelname)-8s %(message)s',
                                  datefmt='%Y-%m-%d %H:%M:%S')

        # Using the custom log handler to write to the log file and the UI.
        self.__log_widget = MyLoggerWidget(self, "pc reset")
        self.__log_widget.setFormatter(formatter)

        # Stream handler to write to the console.
        screen_handler = logging.StreamHandler(stream=sys.stdout)
        screen_handler.setFormatter(formatter)

        # Finalize the actual logger and assign its handlers.
        self.__logger = logging.getLogger(self.__log_widget.log_name)
        self.__logger.setLevel(logging.DEBUG)
        self.__logger.addHandler(self.__log_widget)
        self.__logger.addHandler(screen_handler)

    def __parse_config(self):
        # Read the config file.
        config_parser = configparser.RawConfigParser()
        config_parser.read('PC_reset_config.ini')

        # The approximate delay time between each ping attempt (SECONDS).
        self.__config_wait_between_pings = int(config_parser.get('Timing',
                                                                'wait_between_pings',
                                                                fallback=5))

        # The number of pings that need to fail before the PC is considered dead.
        self.__config_ping_fails_needed_for_restart = int(config_parser.get('Timing',
                                                                          'ping_fails_needed_for_restart',
                                                                          fallback=4))

        # Time to wait for the PC to shutdown (SECONDS).
        self.__config_wait_before_shutdown = int(config_parser.get('Timing',
                                                                 'wait_before_shutdown',
                                                                 fallback=30))

        # Time to hold the power switch to trigger a restart of the PC (SECONDS).
        self.__config_hold_power_switch = int(config_parser.get('Timing',
                                                              'hold_power_switch',
                                                              fallback=3))

        # Address of the PC to ping.
        self.__config_hostname = config_parser.get('Comm',
                                                 'hostname', 
                                                 fallback=None)

        # Channel that the relay is connected to.  Relay closes on low output.
        self.__config_relay_channel = int(config_parser.get('Channel',
                                                          'relay_channel',
                                                          fallback=25))

        # Channel that the switch is connected to.  Switch should be pull down.
        self.__config_switch_channel = int(config_parser.get('Channel',
                                                           'switch_channel',
                                                           fallback=23))

    def __ping(self):
        
        # I am not going to ping at all if the thread that restarts the PC is running.
        if(not self.__restart_thread.isRunning()):
            
            request_restart = False
            
            # Ping the PC.
            response = os.system("ping -c 1 " + self.__config_hostname)
            self.__status_bar_ping_time = self.__generate_timestamp()
            self.__update_status_bar()
        
            # We are restarting the PC.
            if (self.__flag_restarting == True):
                # Ping succeeded so assume that the restart was successful.
                if(response == 0):
                    self.__logger.info("{} successfully restarted! Response = {}"
                                    .format(self.__config_hostname, response))
                    self.__flag_restarting = False
                    self.__status_bar_restarting = False
                    self.__flag_ping_fail_count = 0
                    self.__status_bar_success_restart += 1
                    self.__status_bar_restart_time = self.__generate_timestamp()
                    self.__update_status_bar()
                
                # Ping failed so just log a message to track how long it takes to restart.
                else:
                    self.__logger.info("{} is restarting but not back yet. Response = {}"
                                    .format(self.__config_hostname, response))
            # We are not restarting.
            else:
                # The ping failed.
                if(response != 0):
                    # Do not restart the PC until the ping fails enough times consecutively.
                    if (self.__flag_ping_fail_count < self.__config_ping_fails_needed_for_restart):
                        self.__flag_ping_fail_count += 1
                        self.__logger.error("{} did not respond! Response = {} Consecutive fails = {} "
                                        .format(self.__config_hostname, response, self.__flag_ping_fail_count))
                    # The ping has failed enough times consecutively so restart the PC.
                    else:
                        request_restart = True
                        self.__logger.error("{} is down, requesting auto restart! Response = {}"
                                        .format(self.__config_hostname, response))
                # The ping succeeded so reset the consecutive number of failures.
                else:
                    self.__flag_ping_fail_count = 0

            # Request a restart of the PC if the manual switch was pressed.
            if GPIO.event_detected(self.__config_switch_channel):
                request_restart = True
                self.__logger.info("{} manual restart request.".format(self.__config_hostname))

            # Handle any pending restart requests.
            if(request_restart == True):
                self.__logger.info("{} is restarting!".format(self.__config_hostname))
                self.__restart_thread.start()
                self.__flag_restarting = True
                self.__status_bar_restarting = True
                self.__update_status_bar()

    def __update_status_bar(self):
        status_bar_message = "Last Ping: {}  |  Restarting: {}  |  Successful Restarts: {}  |  Last Restart: {}".format(
                            self.__status_bar_ping_time,
                            self.__status_bar_restarting,
                            self.__status_bar_success_restart,
                            self.__status_bar_restart_time)
        self.statusBar().showMessage(status_bar_message)

    def closeEvent(self, event):
        # Save the current size and position of the UI so that it can
        # be restored to the same state the next time it runs.
        self.settings.setValue("geometry", self.saveGeometry())

        # Try to open the relay before exiting so that the PC does not get stuck
        # in an endless restart.
        GPIO.output(self.__config_relay_channel, GPIO.HIGH)
        GPIO.cleanup()

        self.__logger.info('He be gone, he be outta here!')
        
        super(PcResetMainWindow, self).closeEvent(event)
            
class RestartThread(QThread):
    def __init__(self, relay_channel, hold_power_switch, wait_before_shutdown):
        QThread.__init__(self)
        self.__relay_channel = relay_channel
        self.__hold_power_switch = hold_power_switch
        self.__wait_before_shutdown = wait_before_shutdown
        
    def __del__(self):
        self.wait()

    def run(self):    
        # Close relay to initiate power down.
        GPIO.output(self.__relay_channel, GPIO.LOW)
        time.sleep(self.__hold_power_switch)
        GPIO.output(self.__relay_channel, GPIO.HIGH)

        # Wait a while to give the PC some time to shutdown.
        time.sleep(self.__wait_before_shutdown)

        # Close the relay to initiate power up.
        GPIO.output(self.__relay_channel, GPIO.LOW)
        time.sleep(self.__hold_power_switch)
        GPIO.output(self.__relay_channel, GPIO.HIGH)

        
if __name__ == '__main__':
    app = QApplication(sys.argv)
    pc_reset_main = PcResetMainWindow() 
    sys.exit(app.exec_())
