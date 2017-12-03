import pytest
import pc_reset_ping

from pc_reset_ping import PingBoy

@pytest.fixture(autouse=True)
def mock_my_logger(pingboy, mocker):
    """Mocks my_logger attribute of a PingBoy."""
    mock_log = mocker.patch.object(pingboy, 'my_logger')
    return mock_log

@pytest.fixture(autouse=True)
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

@pytest.fixture(autouse=True)
def mock_restart_thread(pingboy, mocker):
    """Mocks the thread that restarts the PC.  It defaults to thread not running."""
    mock_thread = mocker.patch.object(pingboy, 'restart_thread')
    mock_thread.isRunning.return_value = False
    return mock_thread

@pytest.fixture()
def mock_switch_event_detected(mocker):
    """Mocks the manual switch input.  It defaults to switch pressed."""
    mock_event = mocker.patch('RPi.GPIO.event_detected')
    mock_event.return_value = True
    return mock_event

@pytest.fixture(autouse=True)
def mock_switch_event_not_detected(mocker):
    """Mocks the manual switch input.  It defaults to switch not pressed."""
    mock_event = mocker.patch('RPi.GPIO.event_detected')
    mock_event.return_value = False
    return mock_event

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

    # Waits here until test is done.
    yield pingboy

    # Force GPIO cleanup.
    pingboy.close()

def test_ping_occurs(pingboy, mock_ping_succeed):
    """Confirms that a ping occurs."""
    pingboy.ping()

    mock_ping_succeed.assert_called_once_with('ping -c 1 192.168.1.39')

def test_ping_restart_successful_log(pingboy, mock_my_logger):
    """A successful ping occurs during a restart."""
    pingboy.flag_ping_fail_count = 99
    pingboy.flag_restarting = True

    pingboy.ping()
    
    mock_my_logger.logger.info.assert_called_once_with(
        "192.168.1.39 successfully restarted! Response = 0")
    assert pingboy.flag_ping_fail_count == 0
    assert pingboy.flag_restarting == False

def test_ping_restart_successful_flag_ping_fail_count(pingboy):
    """A successful ping occurs during a restart."""
    pingboy.flag_ping_fail_count = 99
    pingboy.flag_restarting = True

    pingboy.ping()
    
    assert pingboy.flag_ping_fail_count == 0
    assert pingboy.flag_restarting == False

def test_ping_restart_successful_flag_restarting(pingboy):
    """A successful ping occurs during a restart."""
    pingboy.flag_ping_fail_count = 99
    pingboy.flag_restarting = True

    pingboy.ping()
    
    assert pingboy.flag_restarting == False

def test_ping_restart_in_progress_log(pingboy, mock_ping_fail, mock_my_logger):
    """A ping fails during a restart."""
    pingboy.flag_ping_fail_count = 99
    pingboy.flag_restarting = True

    pingboy.ping()
    
    mock_my_logger.logger.info.assert_called_once_with(
        "192.168.1.39 is restarting but not back yet. Response = 1")

def test_ping_restart_in_progress_flag_ping_fail_count(pingboy, mock_ping_fail):
    """A ping fails during a restart."""
    pingboy.flag_ping_fail_count = 99
    pingboy.flag_restarting = True

    pingboy.ping()
    
    assert pingboy.flag_ping_fail_count == 99

def test_ping_restart_in_progress_flag_restarting(pingboy, mock_ping_fail):
    """A ping fails during a restart."""
    pingboy.flag_ping_fail_count = 99
    pingboy.flag_restarting = True

    pingboy.ping()
    
    assert pingboy.flag_restarting == True

def test_ping_failure_under_threshold_log(pingboy, mock_ping_fail, mock_my_logger):
    """A ping fails but the fail counter does not indicate a need for restart."""
    pingboy.flag_ping_fail_count = 0
    pingboy.config_values['ping_fails_needed_for_restart'] = 2

    pingboy.ping()

    mock_my_logger.logger.error.assert_called_once_with(
        "192.168.1.39 did not respond! Response = 1 Consecutive fails = 1")
    assert pingboy.flag_ping_fail_count == 1

def test_ping_failure_under_threshold_flag_ping_fail_count(pingboy, mock_ping_fail):
    """A ping fails but the fail counter does not indicate a need for restart."""
    pingboy.flag_ping_fail_count = 0
    pingboy.config_values['ping_fails_needed_for_restart'] = 2

    pingboy.ping()

    assert pingboy.flag_ping_fail_count == 1

def test_ping_failure_over_threshold_log(pingboy, mock_ping_fail, mock_my_logger):
    """A ping fails and the fail counter indicates a need for restart."""
    pingboy.flag_ping_fail_count = 1
    pingboy.flag_restarting = False
    pingboy.config_values['ping_fails_needed_for_restart'] = 2
    
    pingboy.ping()

    mock_my_logger.logger.error.assert_called_once_with(
        "192.168.1.39 is down, requesting auto restart! Response = 1")
    mock_my_logger.logger.info.assert_called_once_with("192.168.1.39 is restarting!")

def test_ping_failure_over_threshold_restart_thread(pingboy, mock_ping_fail, mock_restart_thread):
    """A ping fails and the fail counter indicates a need for restart."""
    pingboy.flag_ping_fail_count = 1
    pingboy.flag_restarting = False
    pingboy.config_values['ping_fails_needed_for_restart'] = 2
    
    pingboy.ping()

    mock_restart_thread.start.assert_called_once_with()

def test_ping_failure_over_threshold_flag_ping_fail_count(pingboy, mock_ping_fail):
    """A ping fails and the fail counter indicates a need for restart."""
    pingboy.flag_ping_fail_count = 1
    pingboy.flag_restarting = False
    pingboy.config_values['ping_fails_needed_for_restart'] = 2
    
    pingboy.ping()

    assert pingboy.flag_ping_fail_count == 3

def test_ping_failure_over_threshold_flag_restarting(pingboy, mock_ping_fail):
    """A ping fails and the fail counter indicates a need for restart."""
    pingboy.flag_ping_fail_count = 1
    pingboy.flag_restarting = False
    pingboy.config_values['ping_fails_needed_for_restart'] = 2
    
    pingboy.ping()

    assert pingboy.flag_restarting == True

def test_manual_restart_event_detected(pingboy, mock_switch_event_detected):
    """A manual restart request is made via the switch input."""
    pingboy.flag_ping_fail_count = 0
    pingboy.flag_restarting = False
    pingboy.config_values['ping_fails_needed_for_restart'] = 2
    pingboy.config_values['relay_channel'] = 5
    pingboy.config_values['switch_channel'] = 6

    pingboy.ping()

    mock_switch_event_detected.assert_called_once_with(6)

def test_manual_restart_log(pingboy, mock_my_logger, mock_switch_event_detected):
    """A manual restart request is made via the switch input."""
    pingboy.flag_ping_fail_count = 0
    pingboy.flag_restarting = False
    pingboy.config_values['ping_fails_needed_for_restart'] = 2
    pingboy.config_values['relay_channel'] = 5
    pingboy.config_values['switch_channel'] = 6

    pingboy.ping()

    mock_my_logger.logger.info.assert_any_call("192.168.1.39 manual restart request.")
    mock_my_logger.logger.info.assert_any_call("192.168.1.39 is restarting!")


def test_manual_restart_thread(pingboy, mock_restart_thread, mock_switch_event_detected):
    """A manual restart request is made via the switch input."""
    pingboy.flag_ping_fail_count = 0
    pingboy.flag_restarting = False
    pingboy.config_values['ping_fails_needed_for_restart'] = 2
    pingboy.config_values['relay_channel'] = 5
    pingboy.config_values['switch_channel'] = 6

    pingboy.ping()

    mock_restart_thread.start.assert_called_once_with()


def test_manual_restart_flag_restarting(pingboy, mock_switch_event_detected):
    """A manual restart request is made via the switch input."""
    pingboy.flag_ping_fail_count = 0
    pingboy.flag_restarting = False
    pingboy.config_values['ping_fails_needed_for_restart'] = 2
    pingboy.config_values['relay_channel'] = 5
    pingboy.config_values['switch_channel'] = 6

    pingboy.ping()

    assert pingboy.flag_restarting == True
    
