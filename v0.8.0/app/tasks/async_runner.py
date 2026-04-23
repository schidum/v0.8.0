# app/tasks/async_runner.py
"""
Helper utilities for safely running async code in Celery tasks.
Handles event loop creation and prevents "RuntimeError: asyncio.run() cannot be called from a running event loop"
"""

import asyncio
import logging

logger = logging.getLogger(__name__)


def run_async_task(coro):
    """
    Safely run an async coroutine in a Celery task context.
    
    This function handles edge cases:
    - Creates new event loop if needed
    - Recovers from existing event loop errors
    - Properly cleans up resources
    
    Args:
        coro: The coroutine to run
        
    Returns:
        The result of the coroutine
        
    Raises:
        Any exceptions raised by the coroutine
    """
    try:
        # First attempt: try asyncio.run() (recommended for Python 3.7+)
        return asyncio.run(coro)
    except RuntimeError as e:
        # If there's already a running loop, fall back to event loop management
        if "asyncio.run() cannot be called from a running event loop" in str(e):
            logger.warning("Event loop already running, using fallback execution method")
            return _run_with_new_loop(coro)
        else:
            logger.error(f"Unexpected RuntimeError in asyncio.run: {e}")
            raise


def _run_with_new_loop(coro):
    """
    Fallback method: Create a new event loop and run the coroutine.
    Used when asyncio.run() fails due to an already-running loop.
    """
    loop = None
    try:
        # Create a completely new event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        logger.debug("Created new event loop for async task")
        return loop.run_until_complete(coro)
    finally:
        if loop:
            try:
                # Close the loop to prevent resource leaks
                loop.close()
            except Exception as e:
                logger.warning(f"Error closing event loop: {e}")


def get_or_create_event_loop():
    """
    Get the current event loop or create a new one if none exists.
    This is useful for task initialization.
    """
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            raise RuntimeError("Event loop is closed")
        return loop
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop
