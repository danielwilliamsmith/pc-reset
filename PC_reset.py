import configparser
import os
import RPi.GPIO as GPIO
import time

import my_logger

# ---------- CONFIG FILE ---------- #

config_parser = configparser.RawConfigParser()
config_parser.read('PC_reset_config.ini')

# The approximate delay time between each ping attempt (SECONDS).
WAIT_BETWEEN_PINGS = int(config_parser.get('Timing', 'wait_between_pings', fallback=5))

# The number of pings that need to fail before the PC is considered dead.
PING_FAILS_NEEDED_FOR_RESTART = int(config_parser.get('Timing', 'ping_fails_needed_for_restart', fallback=4))

# Time to wait for the PC to shutdown (SECONDS).
WAIT_BEFORE_SHUTDOWN = int(config_parser.get('Timing', 'wait_before_shutdown', fallback=30))

# Time to hold the power switch to trigger a restart of the PC (SECONDS).
HOLD_POWER_SWITCH = int(config_parser.get('Timing', 'hold_power_switch', fallback=3))

# Address of the PC to ping.
HOSTNAME = config_parser.get('Comm', 'hostname', fallback=None)

# Channel that the relay is connected to.  Relay closes on low output.
RELAY_CHANNEL = int(config_parser.get('Channel', 'relay_channel', fallback=25))

# Channel that the switch is connected to.  Switch should be pull down.
SWITCH_CHANNEL = int(config_parser.get('Channel', 'switch_channel', fallback=23)) 


# ---------- GPIO CONFIG ---------- #

# Using BCM mode because I think it is less confusing.
GPIO.setmode(GPIO.BCM)

# This output drives the relay.  The relay is always opened initially.
GPIO.setup(RELAY_CHANNEL, GPIO.OUT)
GPIO.output(RELAY_CHANNEL, GPIO.HIGH)

# This input detects a switch press.  The switch is normally low.
GPIO.setup(SWITCH_CHANNEL, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
GPIO.add_event_detect(SWITCH_CHANNEL, GPIO.RISING, bouncetime=300)


# ---------- FLAGS ---------- #

# Flags to indicate when the PC is restarting.  This is needed
# to ignore ping failures during the restart.
restarting = False
request_restart = False

# Counter to keep track of the number of consecutive ping
# failures that have occurred prior to executing a restart.
ping_fail_count = 0


# ---------- LOGGER ---------- #

logger = my_logger.custom_logger('Ping Boy')


# Function to handle the power down and power up of the PC.
def restart_PC():
    global restarting
    global request_restart

    # Close relay to initiate power down.
    GPIO.output(RELAY_CHANNEL, GPIO.LOW)
    time.sleep(HOLD_POWER_SWITCH)
    GPIO.output(RELAY_CHANNEL, GPIO.HIGH)
    logger.info("{} shutting down...".format(HOSTNAME))

    # Wait a while to give the PC some time to shutdown.
    time.sleep(WAIT_BEFORE_SHUTDOWN)

    # Close the relay to initiate power up.
    GPIO.output(RELAY_CHANNEL, GPIO.LOW)
    time.sleep(HOLD_POWER_SWITCH)
    GPIO.output(RELAY_CHANNEL, GPIO.HIGH)
    logger.info("{} starting up...".format(HOSTNAME))

    # Set the global flags to indicate that a restart is in progress.
    restarting = True
    request_restart = False

try:
    while True:
        # Handle any pending restart requests.
        if(request_restart == True):
            restart_PC()
        
        # Take a break then ping the PC.
        time.sleep(WAIT_BETWEEN_PINGS)
        response = os.system("ping -c 1 " + HOSTNAME)
        
        # We are restarting the PC.
        if (restarting == True):
            # Ping succeeded so assume that the restart was successful.
            if(response == 0):
                logger.info("{} successfully restarted! Response = {}".format(HOSTNAME, response))
                restarting = False
                ping_fail_count = 0
            # Ping failed so just log a message to track how long it takes to restart.
            else:
                logger.info("{} is restarting but not back yet. Response = {}".format(HOSTNAME, response))
                
        # We are not restarting.
        else:
            # The ping failed.
            if(response != 0):
                # Do not restart the PC until the ping fails enough times consecutively.
                if (ping_fail_count < PING_FAILS_NEEDED_FOR_RESTART):
                    ping_fail_count += 1
                    logger.error("{} did not respond! Response = {} Consecutive fails = {} ".format(HOSTNAME, response, ping_fail_count))
                # The ping has failed enough times consecutively so restart the PC.
                else:
                    request_restart = True
                    logger.error("{} is down, requesting auto restart! Response = {}".format(HOSTNAME, response))
            # The ping succeeded so reset the consecutive number of failures.
            else:
                ping_fail_count = 0

        # Request a restart of the PC if the manual switch was pressed.
        if GPIO.event_detected(SWITCH_CHANNEL):
            request_restart = True
            logger.info("{} manual restart request.".format(HOSTNAME))
            
    
except KeyboardInterrupt:
    logger.info('Sayonara baby!')
    
    # Try to open the relay before exiting so that the PC does not get stuck
    # in an endless restart.
    GPIO.output(RELAY_CHANNEL, GPIO.HIGH)
    GPIO.cleanup()
