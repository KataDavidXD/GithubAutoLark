#!/usr/bin/env python3
"""Run the GithubAutoLark web server."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
load_dotenv()

def main():
    import uvicorn
    
    host = os.getenv("SERVER_HOST", "0.0.0.0")
    port = int(os.getenv("SERVER_PORT", 8000))
    reload = os.getenv("SERVER_RELOAD", "true").lower() == "true"
    
    print(f"""
    ╔═══════════════════════════════════════════════════════╗
    ║           GithubAutoLark Server                       ║
    ╠═══════════════════════════════════════════════════════╣
    ║  URL: http://{host}:{port:<5}                            ║
    ║  API Docs: http://{host}:{port:<5}/docs                  ║
    ║  Hot Reload: {str(reload):<5}                              ║
    ╚═══════════════════════════════════════════════════════╝
    """)
    
    uvicorn.run(
        "server.app:app",
        host=host,
        port=port,
        reload=reload,
    )


if __name__ == "__main__":
    main()
