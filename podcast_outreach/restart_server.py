#!/usr/bin/env python3
"""
Safe server restart script with socket fixes.
Run this script to restart your FastAPI server with all optimizations.
"""

import subprocess
import sys
import time
import psutil
import os

def kill_existing_servers():
    """Kill any existing FastAPI/uvicorn processes"""
    print("🔍 Checking for existing server processes...")
    
    killed_count = 0
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            cmdline = ' '.join(proc.info['cmdline'] or [])
            if ('uvicorn' in cmdline or 'main:app' in cmdline) and 'python' in cmdline:
                print(f"   🔪 Killing process {proc.info['pid']}: {proc.info['name']}")
                proc.kill()
                killed_count += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    
    if killed_count > 0:
        print(f"✅ Killed {killed_count} existing server process(es)")
        time.sleep(2)  # Give processes time to die
    else:
        print("✅ No existing server processes found")

def check_port_available(port=8000):
    """Check if port is available"""
    import socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(('127.0.0.1', port))
        sock.close()
        return True
    except OSError:
        return False

def start_server():
    """Start the FastAPI server with optimized settings"""
    print("🚀 Starting FastAPI server with socket optimizations...")
    
    # Check if port is available
    if not check_port_available(8000):
        print("❌ Port 8000 is still in use. Waiting...")
        time.sleep(5)
        if not check_port_available(8000):
            print("❌ Port 8000 still unavailable. Please manually kill processes using port 8000")
            return False
    
    try:
        # Start server with optimized settings
        cmd = [
            sys.executable, "-m", "uvicorn",
            "main:app",
            "--host", "127.0.0.1",
            "--port", "8000",
            "--reload",
            "--workers", "1",  # Single worker to prevent resource conflicts
            "--limit-concurrency", "100",  # Limit concurrent connections
            "--timeout-keep-alive", "30",  # Keep alive timeout
            "--access-log"
        ]
        
        print(f"   📋 Command: {' '.join(cmd)}")
        
        # Change to the correct directory
        os.chdir("/mnt/c/Users/ebube/Documents/PGL - Postgres/podcast_outreach")
        
        # Start the server
        process = subprocess.Popen(cmd)
        
        print("✅ Server started successfully!")
        print("🌐 Access your app at: http://127.0.0.1:8000")
        print("📊 API docs at: http://127.0.0.1:8000/docs")
        print()
        print("💡 The server now includes:")
        print("   - Optimized database connection pool (max 5 connections)")
        print("   - Windows socket optimizations")
        print("   - Resource cleanup middleware")
        print("   - Connection leak monitoring")
        print()
        print("⏹️  Press Ctrl+C to stop the server")
        
        # Wait for the process
        process.wait()
        
    except KeyboardInterrupt:
        print("\n🛑 Server stopped by user")
        return True
    except Exception as e:
        print(f"❌ Error starting server: {e}")
        return False

def main():
    """Main restart function"""
    print("🔄 FastAPI Server Restart with Socket Fixes")
    print("=" * 50)
    
    # Step 1: Kill existing servers
    kill_existing_servers()
    
    # Step 2: Start optimized server
    success = start_server()
    
    if not success:
        print("\n❌ Server restart failed")
        sys.exit(1)

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"❌ Restart script failed: {e}")
        sys.exit(1)