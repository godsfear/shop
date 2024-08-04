import logging.config
import logging.handlers


logger = logging.getLogger("log")

logging_config = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "simple": {
            "format": "%(asctime)s - %(levelname)s - %(message)s",
            "datefmt": "%Y-%m-%dT%H:%M:%S%z"
        },
        "json": {
            "()": "jsonlogger.JSONFormatter",
            "fmt_keys": {
                "level": "levelname",
                "message": "message",
                "timestamp": "timestamp",
                "logger": "name",
                "module": "module",
                "function": "funcName",
                "line": "lineno",
                "thread_name": "threadName",
            }
        }
    },
    "handlers": {
        "stdout": {
            "class": "logging.StreamHandler",
            "formatter": "simple",
            "stream": "ext://sys.stdout",
        },
        "file": {
            "class": "logging.handlers.TimedRotatingFileHandler",
            "formatter": "json",
            "filename": "logs/shop.log",
            "when": "D",
            "interval": 1,
        }
    },
    "loggers": {
        "root": {
            "level": "INFO", "handlers": ["stdout", "file"]
        }
    },
}

logging.config.dictConfig(config=logging_config)
