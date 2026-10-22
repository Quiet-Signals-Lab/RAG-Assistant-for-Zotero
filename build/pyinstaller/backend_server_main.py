#!/usr/bin/env python3
"""
Backend server wrapper for PyInstaller bundle
This script starts the FastAPI backend server with uvicorn
Accepts port as a command-line argument to match Electron's expectations
"""
import sys
import socket
import uvicorn

def is_port_available(host: str, port: int) -> bool:
    """Check if a port is available for binding"""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind((host, port))
            return True
    except OSError:
        return False

def find_available_port(host: str, preferred_port: int = 8000, max_tries: int = 10) -> int:
    """Find an available port starting from the preferred port"""
    for i in range(max_tries):
        port = preferred_port + i
        if is_port_available(host, port):
            if port != preferred_port:
                print(f"Port {preferred_port} unavailable, using port {port} instead")
            return port
        print(f"Port {port} is in use, trying next...")
    
    raise RuntimeError(f"Could not find an available port in range {preferred_port}-{preferred_port + max_tries - 1}")

def main():
    # Parse command line arguments
    port = 8000  # default port
    host = "127.0.0.1"
    
    # Simple argument parsing
    args = sys.argv[1:]
    for i, arg in enumerate(args):
        if arg == '--port' and i + 1 < len(args):
            port = int(args[i + 1])
        elif arg == '--host' and i + 1 < len(args):
            host = args[i + 1]
    
    # Find an available port if the requested one is in use
    try:
        available_port = find_available_port(host, port)
    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
    
    print(f"Starting RAG Assistant for Zotero backend server on {host}:{available_port}")
    print(f"PyInstaller bundle - Python {sys.version}")
    
    # Import the app directly (not as a string) so PyInstaller can find it
    from backend.main import app
    
    # Run uvicorn with the FastAPI app object
    uvicorn.run(
        app,
        host=host,
        port=available_port,
        log_level="info"
    )

if __name__ == "__main__":
    main()
