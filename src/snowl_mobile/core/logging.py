from __future__ import annotations

import logging
from pathlib import Path


def configure_logging(verbosity: int = 0, *, log_file: Path | None = None) -> None:
    console_level = logging.WARNING
    if verbosity == 1:
        console_level = logging.INFO
    elif verbosity >= 2:
        console_level = logging.DEBUG

    # Keep console output quiet by default, but still persist useful runtime
    # progress into run.log/trial.log when file logging is enabled.
    file_level = logging.INFO if log_file is not None else console_level
    if verbosity >= 2:
        file_level = logging.DEBUG

    root_logger = logging.getLogger()
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)
        handler.close()

    formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] %(name)s - %(message)s")
    console_handler = logging.StreamHandler()
    console_handler.setLevel(console_level)
    console_handler.setFormatter(formatter)

    root_logger.setLevel(min(console_level, file_level))
    root_logger.addHandler(console_handler)

    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(file_level)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)


def get_trial_logger(trial_id: str, log_file: Path | None = None) -> logging.Logger:
    logger = logging.getLogger(f"snowl_mobile.trial.{trial_id}")
    logger.setLevel(logging.DEBUG)

    if log_file is None:
        logger.propagate = True
        return logger

    logger.propagate = False
    log_file.parent.mkdir(parents=True, exist_ok=True)
    resolved = str(log_file.resolve())
    for handler in list(logger.handlers):
        if isinstance(handler, logging.FileHandler) and handler.baseFilename == resolved:
            return logger
        logger.removeHandler(handler)
        handler.close()

    formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] %(name)s - %(message)s")
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    return logger
