#!/usr/bin/env python3
"""
Entrypoint for launching the Linux Troubleshooting Lab web interface.
"""
import os
import sys
import uvicorn

def main():
    port = int(os.getenv("PORT", 8088))
    host = os.getenv("HOST", "0.0.0.0")
    print(f"Starting Linux Troubleshooting Lab Web UI on http://localhost:{port}")
    uvicorn.run("linuxlab.web.app:app", host=host, port=port, log_level="info")

if __name__ == "__main__":
    main()
