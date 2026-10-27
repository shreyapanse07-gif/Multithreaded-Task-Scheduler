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
    @functools.wraps(func)                 # keeps the original __name__ / __doc__
    def wrapper(*args, **kwargs):
        start = time.perf_counter()
        try:
            return func(*args, **kwargs)
        finally:                           # runs even if func raises
            elapsed = time.perf_counter() - start
            logger.info(f"{func.__name__} took {elapsed:.3f}s")
    return wrapper


def log_call(func):
    """Logs function name, args and which thread called it."""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        thread = threading.current_thread().name
        logger.info(f"{thread} -> {func.__name__}{args}")
        try:
            result = func(*args, **kwargs)
            logger.info(f"{func.__name__} returned {result}")
            return result
        except Exception:
            logger.exception(f"{func.__name__} raised an error")
            raise                          # let the caller decide retry / fail
    return wrapper


def retry(times=3, delay=1, exceptions=(Exception,)):
    """Decorator WITH arguments -> 3 levels: retry(...) -> decorator(func) -> wrapper(*a, **kw)
    Use this for small in-function retries; Scheduler handles big task-level retries."""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(1, times + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    if attempt == times:
                        raise                      # out of attempts -> let the error go up
                    logger.warning(f"{func.__name__} failed ({e}), attempt {attempt}/{times}")
                    time.sleep(delay)
        return wrapper
    return decorator


def synchronized(lock):
    """Runs the function while holding `lock` -> shows thread safety via decorator."""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            with lock:
                return func(*args, **kwargs)
        return wrapper
    return decorator