import pytest
import pc_reset_ping
import RPi.GPIO as GPIO

from pc_reset_ping import PingBoy

@pytest.fixture()
def mock_log(pingboy, mocker):
    """Mocks my_logger attribute of a PingBoy."""
    mock_logger = mocker.patch.object(pingboy, 'my_logger')
    return mock_logger

@pytest.fixture()
def mock_ping_succeed(mocker):
    """Mocks the os.system call to perform a ping and returns a success."""
    mock_os_system = mocker.patch('os.system')
    mock_os_system.return_value = 0
    return mock_os_system

@pytest.fixture()
def mock_ping_fail(mocker):
    """Mocks the os.system call to perform a ping and returns a fail."""
    mock_os_system = mocker.patch('os.system')
    mock_os_system.return_value = 1
    return mock_os_system

@pytest.fixture()
def mock_thread(pingboy, mocker):
    """Mocks the thread that restarts the PC.  It defaults to thread not running."""
    mock_thread = mocker.patch.object(pingboy, 'restart_thread')
    mock_thread.isRunning.return_value = False
    return mock_thread

@pytest.yield_fixture()
def pingboy():
    """Creates a default PingBoy for each test to use."""
    pingboy = PingBoy()

    # Default values.
    pingboy.config_values['wait_between_pings'] = 5
    pingboy.config_values['ping_fails_needed_for_restart'] = 4
    pingboy.config_values['wait_before_shutdown'] = 30
    pingboy.config_values['hold_power_switch'] = 3
    pingboy.config_values['hostname'] = "192.168.1.39"
    pingboy.config_values['relay_channel'] = 5
    pingboy.config_values['switch_channel'] = 5
    pingboy.flag_ping_fail_count = 0
    pingboy.flag_restarting = False
    
    yield pingboy
    
    # I tried to implement this in the actual class when the object is deleted
    # but I could not find a way to get it to execute before the next test
    # starts.  Any test after the first will crash if I do not do this here.
    GPIO.cleanup()

def test_ping_occurs(pingboy, mock_ping_succeed):
    """Confirms that a ping occurs."""
    pingboy.ping()

    mock_ping_succeed.assert_called_once_with('ping -c 1 192.168.1.39')

def test_ping_restart_successful(pingboy, mock_ping_succeed, mock_log):
    """A successful ping occurs during a restart."""
    pingboy.flag_ping_fail_count = 99
    pingboy.flag_restarting = True

    pingboy.ping()
    
    mock_log.logger.info.assert_called_once_with("192.168.1.39 successfully restarted! Response = 0")
    assert pingboy.flag_ping_fail_count == 0
    assert pingboy.flag_restarting == False

def test_ping_restart_in_progress(pingboy, mock_ping_fail, mock_log):
    """A ping fails during a restart."""
    pingboy.flag_ping_fail_count = 99
    pingboy.flag_restarting = True

    pingboy.ping()
    
    mock_log.logger.info.assert_called_once_with("192.168.1.39 is restarting but not back yet. Response = 1")
    assert pingboy.flag_ping_fail_count == 99
    assert pingboy.flag_restarting == True

def test_ping_failure_under_threshold(pingboy, mock_ping_fail, mock_log):
    """A ping fails but the fail counter does not indicate a need for restart."""
    pingboy.flag_ping_fail_count = 0
    pingboy.config_values['ping_fails_needed_for_restart'] = 2

    pingboy.ping()

    mock_log.logger.error.assert_called_once_with("192.168.1.39 did not respond! Response = 1 Consecutive fails = 1")
    assert pingboy.flag_ping_fail_count == 1

def test_ping_failure_over_threshold(pingboy, mock_ping_fail, mock_log, mock_thread):
    """A ping fails and the fail counter indicates a need for restart."""
    pingboy.flag_ping_fail_count = 1
    pingboy.flag_restarting = False
    pingboy.config_values['ping_fails_needed_for_restart'] = 2
    
    pingboy.ping()

    mock_log.logger.error.assert_called_once_with("192.168.1.39 is down, requesting auto restart! Response = 1")
    mock_thread.start.assert_called_once_with()
    mock_log.logger.info.assert_called_once_with("192.168.1.39 is restarting!")
    assert pingboy.flag_ping_fail_count == 2
    assert pingboy.flag_restarting == True

    
    
