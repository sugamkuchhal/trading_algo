import logging
logger = logging.getLogger(__name__)

def safe_run(func, *args, **kwargs):
    try:
        return func(*args, **kwargs)
    except Exception:
        logger.exception("Error during safe_run")
        return None