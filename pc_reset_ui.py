import datetime
import RPi.GPIO as GPIO
import sys
import time

from pc_reset_ping import PingBoy

from PyQt5.QtCore import Qt, QSettings, QTimer
from PyQt5.QtWidgets import (QApplication, QFormLayout, QFrame, QLabel, QLineEdit, QMainWindow, QPlainTextEdit,
                             QPushButton, QSplitter, QVBoxLayout, QWidget)

class PcResetMainWindow(QMainWindow):
    """Handles the creation of the GUI."""

    def __init__(self):
        super().__init__()
        self.pingboy = PingBoy()
        self.pingboy.my_logger.handler.sig_message_logged.connect(self.__slot_message_logged)
        self.pingboy.sig_pinged_pc.connect(self.__slot_ping)
        self.pingboy.sig_restart_in_progress.connect(self.__slot_restart_in_progress)
        self.pingboy.sig_successful_restart.connect(self.__slot_successful_restart)
        self.config_values = self.pingboy.get_config_values()
        
        self.__init_UI()
        self.__init_status_bar()

        # This needs to always be last.
        self.ping_timer = QTimer()
        self.ping_timer.timeout.connect(self.pingboy.ping)
        self.ping_timer.start(self.config_values['wait_between_pings'] * 1000)

    def __generate_timestamp(self):
        """Returns a timestamp of the current time."""
        ts = time.time()
        st = datetime.datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')
        return st

    def __init_status_bar(self):
        """Initializes variables used for the main window's status bar message."""
        # Variables that will be displayed in the status bar.
        self.status_bar_ping_time = None
        self.status_bar_restarting = False
        self.status_bar_success_restart = 0
        self.status_bar_restart_time = None

    def __init_UI(self):
        """Creates UI elements."""
        
        ping_time_lbl = QLabel("Ping Time (Sec)")
        ping_time_le = QLineEdit()
        ping_time_le.setText(str(self.config_values['wait_between_pings']))

        ping_fail_lbl = QLabel("Ping Fail Limit")
        ping_fail_le = QLineEdit()
        ping_fail_le.setText(str(self.config_values['ping_fails_needed_for_restart']))

        wait_shutdown_lbl = QLabel("PC Shutdown Delay (Sec)")
        wait_shutdown_le = QLineEdit()
        wait_shutdown_le.setText(str(self.config_values['wait_before_shutdown']))

        hold_power_lbl = QLabel("Power Switch Hold (Sec)")
        hold_power_le = QLineEdit()
        hold_power_le.setText(str(self.config_values['hold_power_switch']))

        timing_config_layout = QFormLayout()
        timing_config_layout.addRow(ping_time_lbl, ping_time_le)
        timing_config_layout.addRow(ping_fail_lbl, ping_fail_le)
        timing_config_layout.addRow(wait_shutdown_lbl, wait_shutdown_le)
        timing_config_layout.addRow(hold_power_lbl, hold_power_le)

        timing_config_widget = QWidget()
        timing_config_widget.setLayout(timing_config_layout)

        self.log_widget = QPlainTextEdit()
        self.log_widget.setReadOnly(True)

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(timing_config_widget)
        splitter.addWidget(self.log_widget)
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

    def __slot_message_logged(self, message):
        """Slot for the signal generated when a message is logged."""
        self.log_widget.appendPlainText(message)

    def __slot_ping(self):
        """Slot for the signal generated whenever a ping occurs."""
        self.status_bar_ping_time = self.__generate_timestamp()
        self.__update_status_bar()

    def __slot_restart_in_progress(self):
        """Slot for the signal generated whenever a restart is initiated."""
        self.status_bar_restarting = True
        self.__update_status_bar()

    def __slot_successful_restart(self):
        """Slot for the signal generated whenever a successful restart occurs."""
        self.status_bar_restarting = False
        self.status_bar_success_restart += 1
        self.status_bar_restart_time = self.__generate_timestamp()
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
        """Overrides the main window's closeEvent."""
        # Save the current size and position of the UI so that it can
        # be restored to the same state the next time it runs.
        self.settings.setValue("geometry", self.saveGeometry())
        
        GPIO.cleanup()

        super(PcResetMainWindow, self).closeEvent(event)
   
if __name__ == '__main__':
    app = QApplication(sys.argv)
    pc_reset_main = PcResetMainWindow() 
    sys.exit(app.exec_())
