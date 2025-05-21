import time
import logging
import asyncio
from functools import wraps
from typing import Callable, Any, TypeVar, cast

logger = logging.getLogger(__name__)

T = TypeVar('T')

def retry(max_attempts: int = 3, delay_seconds: int = 2):
    """
    Retry decorator for handling transient email sending failures.
    
    Args:
        max_attempts: Maximum number of retry attempts
        delay_seconds: Delay between retry attempts in seconds
        
    Returns:
        Decorated function that will retry on failure
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            attempts = 0
            while attempts < max_attempts:
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    attempts += 1
                    if attempts == max_attempts:
                        logger.error(f"Failed after {max_attempts} attempts: {str(e)}")
                        raise
                    logger.warning(f"Attempt {attempts} failed, retrying in {delay_seconds}s: {str(e)}")
                    time.sleep(delay_seconds)
            
            # Should never get here, but makes type checker happy
            return cast(T, None)
        return wrapper
    return decorator

async def async_retry(max_attempts: int = 3, delay_seconds: int = 2):
    """
    Async retry decorator for handling transient email sending failures.
    
    Args:
        max_attempts: Maximum number of retry attempts
        delay_seconds: Delay between retry attempts in seconds
        
    Returns:
        Decorated async function that will retry on failure
    """
    def decorator(func: Callable[..., Any]):
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any):
            attempts = 0
            while attempts < max_attempts:
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    attempts += 1
                    if attempts == max_attempts:
                        logger.error(f"Failed after {max_attempts} attempts: {str(e)}")
                        raise
                    logger.warning(f"Attempt {attempts} failed, retrying in {delay_seconds}s: {str(e)}")
                    await asyncio.sleep(delay_seconds)
            return None
        return wrapper
    return decorator
