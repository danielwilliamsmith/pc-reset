import logging
import sys

def custom_logger(name):
    formatter = logging.Formatter(fmt='%(asctime)s %(levelname)-8s %(message)s',
                                  datefmt='%Y-%m-%d %H:%M:%S')
    log_name = name.lower().replace(" ","_")
    handler = RotatingFileHandler('{}_log.log'.format(log_name), mode='a', maxBytes=5*1024*1024,
                                  backupCount=2, encoding=None, delay=0)
    handler.setFormatter(formatter)
    screen_handler = logging.StreamHandler(stream=sys.stdout)
    screen_handler.setFormatter(formatter)
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    logger.addHandler(handler)
    logger.addHandler(screen_handler)
    return logger
