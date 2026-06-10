"""Retry logic with exponential backoff.

Provides configurable retry mechanisms for transient failures.
"""

from __future__ import annotations

import asyncio
import functools
import logging
import random
from collections.abc import Callable

logger = logging.getLogger(__name__)


class RetryExhausted(Exception):
    """Raised when all retry attempts are exhausted."""

    def __init__(self, last_exception: Exception, attempts: int):
        self.last_exception = last_exception
        self.attempts = attempts
        super().__init__(
            f"Retry exhausted after {attempts} attempts. Last exception: {type(last_exception).__name__}: {last_exception}",
        )


def retry_async(
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0,
    jitter: bool = True,
    retryable_exceptions: tuple[type[Exception], ...] = (Exception,),
    on_retry: Callable[[int, Exception], None] | None = None,
) -> Callable:
    """Decorator for async functions with retry logic.

    Args:
        max_attempts: Maximum number of retry attempts
        base_delay: Initial delay between retries (seconds)
        max_delay: Maximum delay between retries (seconds)
        exponential_base: Base for exponential backoff
        jitter: Add random jitter to delay
        retryable_exceptions: Tuple of exceptions to retry on
        on_retry: Callback function(attempt, exception) called on each retry

    Usage:
        @retry_async(max_attempts=3, base_delay=1.0)
        async def call_flaky_service():
            ...
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_attempts):
                try:
                    return await func(*args, **kwargs)
                except retryable_exceptions as e:
                    last_exception = e
                    if attempt < max_attempts - 1:
                        delay = min(
                            base_delay * (exponential_base**attempt),
                            max_delay,
                        )
                        if jitter:
                            delay = delay * (0.5 + random.random())
                        logger.debug(
                            "Retry %d/%d for %s: %s: %s, waiting %.2fs",
                            attempt + 1,
                            max_attempts,
                            func.__name__,
                            type(e).__name__,
                            e,
                            delay,
                        )
                        if on_retry:
                            on_retry(attempt + 1, e)
                        await asyncio.sleep(delay)
            raise RetryExhausted(last_exception or Exception("unknown error"), max_attempts)

        return wrapper

    return decorator


def retry_sync(
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0,
    jitter: bool = True,
    retryable_exceptions: tuple[type[Exception], ...] = (Exception,),
    on_retry: Callable[[int, Exception], None] | None = None,
) -> Callable:
    """Decorator for sync functions with retry logic.

    Args:
        max_attempts: Maximum number of retry attempts
        base_delay: Initial delay between retries (seconds)
        max_delay: Maximum delay between retries (seconds)
        exponential_base: Base for exponential backoff
        jitter: Add random jitter to delay
        retryable_exceptions: Tuple of exceptions to retry on
        on_retry: Callback function(attempt, exception) called on each retry
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except retryable_exceptions as e:
                    last_exception = e
                    if attempt < max_attempts - 1:
                        delay = min(
                            base_delay * (exponential_base**attempt),
                            max_delay,
                        )
                        if jitter:
                            delay = delay * (0.5 + random.random())
                        logger.debug(
                            "Retry %d/%d for %s: %s: %s, waiting %.2fs",
                            attempt + 1,
                            max_attempts,
                            func.__name__,
                            type(e).__name__,
                            e,
                            delay,
                        )
                        if on_retry:
                            on_retry(attempt + 1, e)
                        import time

                        time.sleep(delay)
            raise RetryExhausted(last_exception or Exception("unknown error"), max_attempts)

        return wrapper

    return decorator


class RetryContext:
    """Context manager for retry logic.

    Usage:
        async with RetryContext(max_attempts=3) as retry:
            while retry.should_retry():
                try:
                    result = await call_service()
                    retry.mark_success()
                    return result
                except Exception as e:
                    retry.mark_failure(e)
    """

    def __init__(
        self,
        max_attempts: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        retryable_exceptions: tuple[type[Exception], ...] = (Exception,),
    ):
        self.max_attempts = max_attempts
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.retryable_exceptions = retryable_exceptions
        self.attempt = 0
        self.last_exception: Exception | None = None
        self._succeeded = False

    def should_retry(self) -> bool:
        """Check if we should attempt another retry."""
        return self.attempt < self.max_attempts and not self._succeeded

    def mark_success(self):
        """Mark the current attempt as successful."""
        self._succeeded = True

    def mark_failure(self, exception: Exception):
        """Mark the current attempt as failed."""
        self.last_exception = exception
        self.attempt += 1

    async def wait_if_retrying(self):
        """Wait before retry if needed."""
        if self.should_retry():
            delay = min(
                self.base_delay * (2 ** (self.attempt - 1)),
                self.max_delay,
            )
            await asyncio.sleep(delay)

    @property
    def succeeded(self) -> bool:
        return self._succeeded

    @property
    def exhausted(self) -> bool:
        return self.attempt >= self.max_attempts and not self._succeeded

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return False


# Pre-configured retry decorators for common use cases
retry_on_database_error = retry_async(
    max_attempts=3,
    base_delay=0.5,
    max_delay=5.0,
    retryable_exceptions=(Exception,),
)

retry_on_network_error = retry_async(
    max_attempts=3,
    base_delay=1.0,
    max_delay=10.0,
    retryable_exceptions=(Exception,),
)

retry_on_rate_limit = retry_async(
    max_attempts=5,
    base_delay=2.0,
    max_delay=30.0,
    retryable_exceptions=(Exception,),
)
