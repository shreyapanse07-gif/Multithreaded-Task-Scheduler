"""
decorators.py
Monitoring decorators applied to task functions (Decorators topic).
"""
import time
import functools
import threading

from .logger import get_logger

logger = get_logger(__name__)


def timed(func):
    """Logs how long the function took."""
    # TODO: @functools.wraps(func)   <- keeps original __name__ / __doc__
    # TODO: def wrapper(*args, **kwargs):
    #           start = time.perf_counter()
    #           try: return func(*args, **kwargs)
    #           finally:
    #               elapsed = time.perf_counter() - start
    #               logger.info(f"{func.__name__} took {elapsed:.3f}s")
    # TODO: return wrapper
    pass


def log_call(func):
    """Logs function name, args and which thread called it."""
    # TODO: wrapper logs f"{threading.current_thread().name} -> {func.__name__}{args}"
    # TODO: log result on success, logger.exception on error then re-raise
    pass


def retry(times=3, delay=1, exceptions=(Exception,)):
    """Decorator WITH arguments -> 3 levels: retry(...) -> decorator(func) -> wrapper(*a, **kw)
    Use this for small in-function retries; Scheduler handles big task-level retries."""
    # TODO: def decorator(func):
    #           @functools.wraps(func)
    #           def wrapper(*args, **kwargs):
    #               for attempt in range(1, times + 1):
    #                   try: return func(*args, **kwargs)
    #                   except exceptions as e:
    #                       if attempt == times: raise
    #                       logger.warning(...); time.sleep(delay)
    #           return wrapper
    #       return decorator
    pass


def synchronized(lock):
    """Runs the function while holding `lock` -> shows thread safety via decorator."""
    # TODO: decorator that does `with lock: return func(*args, **kwargs)`
    pass
