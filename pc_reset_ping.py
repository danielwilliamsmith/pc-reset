import configparser
import os
import RPi.GPIO as GPIO
import time

from my_logger import CustomLogger
from PyQt5.QtCore import pyqtSignal, QObject, QThread

class PingBoy(QObject):

    sig_pinged_pc = pyqtSignal()
    sig_restart_in_progress = pyqtSignal()
    sig_successful_restart = pyqtSignal()

    def __init__(self):
        super(PingBoy, self).__init__()
        
        # Create a logger.
        self.my_logger = CustomLogger("PC_reset_log.log")
        
        self.get_config_values()
        self.__init_GPIO()
        self.__init_flags()

        # Prepare the thread that will restart the PC.
        self.restart_thread = RestartThread(self.config_values['relay_channel'],
                                            self.config_values['hold_power_switch'],
                                            self.config_values['wait_before_shutdown'])

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
        GPIO.setup(self.config_values['relay_channel'], GPIO.OUT)
        GPIO.output(self.config_values['relay_channel'], GPIO.HIGH)

        # This input detects a switch press.  The switch is normally low.
        GPIO.setup(self.config_values['switch_channel'], GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
        GPIO.add_event_detect(self.config_values['switch_channel'], GPIO.RISING, bouncetime=300)

    def get_config_values(self):
        """Obtains initial values for configurable inputs from an .ini file."""
        # Read the config file.
        config_parser = configparser.RawConfigParser()
        config_parser.read('pc_reset_config.ini')

        self.config_values = {}

        # The approximate delay time between each ping attempt (SECONDS).
        self.config_values['wait_between_pings'] = int(config_parser.get('Timing',
                                                        'wait_between_pings',
                                                        fallback=5))

        # The number of pings that need to fail before the PC is considered dead.
        self.config_values['ping_fails_needed_for_restart'] = int(config_parser.get('Timing',
                                                                'ping_fails_needed_for_restart',
                                                                fallback=4))

        # Time to wait for the PC to shutdown (SECONDS).
        self.config_values['wait_before_shutdown'] = int(config_parser.get('Timing',
                                                        'wait_before_shutdown',
                                                        fallback=30))

        # Time to hold the power switch to trigger a restart of the PC (SECONDS).
        self.config_values['hold_power_switch'] = int(config_parser.get('Timing',
                                                    'hold_power_switch',
                                                    fallback=3))

        # Address of the PC to ping.
        self.config_values['hostname'] = config_parser.get('Comm',
                                        'hostname', 
                                        fallback=None)

        # Channel that the relay is connected to.  Relay closes on low output.
        self.config_values['relay_channel'] = int(config_parser.get('Channel',
                                            'relay_channel',
                                            fallback=25))

        # Channel that the switch is connected to.  Switch should be pull down.
        self.config_values['switch_channel'] = int(config_parser.get('Channel',
                                                'switch_channel',
                                                fallback=23))

        return self.config_values

    def ping(self):
        """
        Handles the pinging of the remote PC, initiating a restart,
        and confirming a successful restart.
        """ 
        # I am not going to ping or look for the switch input if the thread
        # that restarts the PC is running.
        if(not self.restart_thread.isRunning()):
            request_restart = False
            
            # Ping the PC.
            response = os.system("ping -c 1 " + self.config_values['hostname'])
            self.sig_pinged_pc.emit()
        
            # We are restarting the PC.
            if (self.flag_restarting == True):
                # Ping succeeded so assume that the restart was successful.
                if(response == 0):
                    self.my_logger.logger.info("{} successfully restarted! Response = {}"
                                   .format(self.config_values['hostname'], response))
                    self.flag_restarting = False
                    self.flag_ping_fail_count = 0
                    self.sig_successful_restart.emit()
                
                # Ping failed so just log a message to track how long it takes to restart.
                else:
                    self.my_logger.logger.info("{} is restarting but not back yet. Response = {}"
                                    .format(self.config_values['hostname'], response))
            # We are not restarting.
            else:
                # The ping failed.
                if(response != 0):
                    # Do not restart the PC until the ping fails enough times consecutively.
                    if (self.flag_ping_fail_count < self.config_values['ping_fails_needed_for_restart']):
                        self.flag_ping_fail_count += 1                       
                        self.my_logger.logger.error("{} did not respond! Response = {} Consecutive fails = {} "
                                        .format(self.config_values['hostname'], response, self.flag_ping_fail_count))
                                               
                    # The ping has failed enough times consecutively so restart the PC.
                    else:
                        request_restart = True
                        self.my_logger.logger.error("{} is down, requesting auto restart! Response = {}"
                                        .format(self.config_values['hostname'], response))
                        
                # The ping succeeded so reset the consecutive number of failures.
                else:
                    self.flag_ping_fail_count = 0

            # Request a restart of the PC if the manual switch was pressed.
            if GPIO.event_detected(self.config_values['switch_channel']):
                request_restart = True
                self.my_logger.logger.info("{} manual restart request.".format(self.config_values['hostname']))

            # Handle any pending restart requests.
            if(request_restart == True):
                self.restart_thread.start()
                self.my_logger.logger.info("{} is restarting!".format(self.config_values['hostname']))
                self.flag_restarting = True
                self.sig_restart_in_progress.emit()
                


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
