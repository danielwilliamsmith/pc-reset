import logging
import sys

from logging.handlers import RotatingFileHandler
from PyQt5.QtCore import pyqtSignal, QObject

class CustomHandler(RotatingFileHandler, QObject):
    """
    This is a RotatingFileHandler that is capable of emitting a signal
    whenever a message is logged.
    """
    sig_message_logged = pyqtSignal(str)
    
    def __init__(self, name):
        """
        Name is the log file name.
        """
        RotatingFileHandler.__init__(self, filename=name, mode='a', maxBytes=5*1024*1024,
                         backupCount=2, encoding=None, delay=0)
        QObject.__init__(self)

    def emit(self, record):
        """Override of emit in RotatingFileHandler."""
        
        # Emit a signal that can be used by the GUI to display the log message.
        message = self.format(record)
        self.sig_message_logged.emit(message)

        # Call the normal logger handle.
        super(CustomHandler, self).emit(record)
        
class CustomLogger(QObject):
    """
    Creates a logger that will rotate log files when they become too big.
    Output will also be logged to the console.
    """
    def __init__(self, name):
        """
        Name will be used for the log file name.
        """
        super(CustomLogger, self).__init__()
        
        self.log_name = '{}'.format(name.lower().replace(" ","_")) 
        self.handler = CustomHandler(self.log_name)
        formatter = logging.Formatter(fmt='%(asctime)s %(levelname)-8s %(message)s',
                                      datefmt='%Y-%m-%d %H:%M:%S')
        self.handler.setFormatter(formatter)
        screen_handler = logging.StreamHandler(stream=sys.stdout)
        screen_handler.setFormatter(formatter)
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.DEBUG)
        self.logger.addHandler(self.handler)
        self.logger.addHandler(screen_handler)

    
