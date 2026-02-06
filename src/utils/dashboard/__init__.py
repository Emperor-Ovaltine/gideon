"""
Dashboard package for Gideon bot.
Provides a web-based admin interface for managing bot settings, channels, threads, and diagnostics.
"""

from .server import DashboardServer

__all__ = ['DashboardServer']
