"""
Centralized Logging Configuration for AgenticNet

Provides structured logging with:
- Console output with timestamps
- File output with rotation (5MB, 3 backups)
- Module-based loggers
- Configurable log levels
- Log reading utility for dashboard viewer
"""
import logging
import logging.handlers
import sys
import os
import re
from typing import Optional, List, Dict


# Log file path
LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "logs")
LOG_FILE = os.path.join(LOG_DIR, "agenticnet.log")

# Log format pattern
LOG_FORMAT = '%(asctime)s | %(levelname)s | %(name)s | %(message)s'
LOG_DATEFMT = '%Y-%m-%d %H:%M:%S'

# Regex to parse log lines
LOG_LINE_RE = re.compile(
    r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) \| (\w+) \| ([^ |]+) \| (.*)$'
)


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
    
    # Create formatter
    formatter = logging.Formatter(LOG_FORMAT, datefmt=LOG_DATEFMT)
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # File handler with rotation
    os.makedirs(LOG_DIR, exist_ok=True)
    file_handler = logging.handlers.RotatingFileHandler(
        LOG_FILE,
        maxBytes=5 * 1024 * 1024,  # 5MB
        backupCount=3,
        encoding='utf-8'
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    
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


def read_log_lines(
    level: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 100
) -> List[Dict]:
    """
    Read and parse log lines from the log file.
    
    Args:
        level: Filter by log level (INFO, WARNING, ERROR, DEBUG)
        search: Filter by text search (case-insensitive)
        limit: Max number of lines to return (newest first)
    
    Returns:
        List of parsed log entries [{timestamp, level, module, message}]
    """
    if not os.path.exists(LOG_FILE):
        return []
    
    entries = []
    try:
        with open(LOG_FILE, 'r', encoding='utf-8', errors='replace') as f:
            lines = f.readlines()
        
        # Process from newest to oldest
        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue
            
            match = LOG_LINE_RE.match(line)
            if not match:
                continue
            
            timestamp, log_level, module, message = match.groups()
            
            # Filter by level
            if level and log_level.upper() != level.upper():
                continue
            
            # Filter by search text
            if search and search.lower() not in line.lower():
                continue
            
            entries.append({
                "timestamp": timestamp,
                "level": log_level,
                "module": module,
                "message": message
            })
            
            if len(entries) >= limit:
                break
    except Exception:
        pass
    
    return entries


# Initialize root logger on import
logger = setup_logging()
