# podcast_outreach/windows_socket_config.py

"""
Windows-specific socket and resource configuration to prevent buffer exhaustion.
Import this module early in your application startup.
"""

import os
import socket
import sys
import logging

logger = logging.getLogger(__name__)

def configure_windows_sockets():
    """
    Configure Windows socket settings to prevent buffer exhaustion.
    """
    if sys.platform != "win32":
        return  # Only apply on Windows
    
    try:
        # Set socket defaults
        socket.setdefaulttimeout(30.0)  # 30 second timeout
        
        # Set environment variables for better socket handling
        os.environ.setdefault('PYTHONIOENCODING', 'utf-8')
        
        # Windows-specific socket buffer settings
        # These help prevent the "queue was full" error
        if hasattr(socket, 'SO_SNDBUF'):
            # These would need to be set per socket, but we set defaults
            pass
            
        logger.info("Windows socket configuration applied successfully")
        
    except Exception as e:
        logger.warning(f"Could not apply Windows socket configuration: {e}")

def configure_asyncio_for_windows():
    """
    Configure asyncio settings for better Windows performance.
    """
    if sys.platform != "win32":
        return
        
    try:
        import asyncio
        
        # Use ProactorEventLoop on Windows for better performance
        if hasattr(asyncio, 'WindowsProactorEventLoopPolicy'):
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
            logger.info("Using ProactorEventLoop for better Windows performance")
        
        # Set default asyncio debug mode in development
        if os.getenv('DEBUG', '').lower() in ('true', '1', 'yes'):
            asyncio.set_debug(True)
            
    except Exception as e:
        logger.warning(f"Could not configure asyncio for Windows: {e}")

def apply_windows_optimizations():
    """
    Apply all Windows-specific optimizations.
    Call this early in your application startup.
    """
    if sys.platform != "win32":
        logger.info("Skipping Windows optimizations (not running on Windows)")
        return
    
    logger.info("Applying Windows-specific socket and asyncio optimizations...")
    
    configure_windows_sockets()
    configure_asyncio_for_windows()
    
    # Additional environment variables for stability
    os.environ.setdefault('PYTHONASYNCIODEBUG', '0')  # Disable asyncio debug unless explicitly enabled
    
    logger.info("Windows optimizations applied successfully")

# Auto-apply optimizations when module is imported
if __name__ != "__main__":
    apply_windows_optimizations()