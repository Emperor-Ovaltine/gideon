"""
Database module - Compatibility shim for backward compatibility.
The actual implementation has been moved to the database package.
"""

from .database import DatabaseManager

__all__ = ['DatabaseManager']
