"""
Centralized Logging Configuration for AgenticNet

Provides structured logging with:
- Console output with timestamps
- Module-based loggers
- Configurable log levels
"""
import logging
import sys
from typing import Optional


def setup_logging(level: int = logging.INFO, name: str = "agenticNet") -> logging.Logger:
    """
    Setup and return a configured logger.
    
    Args:
        level: Logging level (default: INFO)
        name: Logger name (default: agenticNet)
    
    Returns:
        Configured logger instance
    """
    # Create logger
    logger = logging.getLogger(name)
    
    # Avoid adding duplicate handlers
    if logger.handlers:
        return logger
    
    logger.setLevel(level)
    
    # Create console handler
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)
    
    # Create formatter
    formatter = logging.Formatter(
        '%(asctime)s | %(levelname)s | %(name)s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    handler.setFormatter(formatter)
    
    # Add handler to logger
    logger.addHandler(handler)
    
    return logger


def get_logger(module_name: str) -> logging.Logger:
    """
    Get a child logger for a specific module.
    
    Args:
        module_name: Name of the module (e.g., 'agent', 'tools')
    
    Returns:
        Child logger instance
    """
    return logging.getLogger(f"agenticNet.{module_name}")


# Initialize root logger on import
logger = setup_logging()
