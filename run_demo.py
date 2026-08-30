"""
run_demo.py — Launches the HealX FastAPI dashboard and opens the browser.

Usage:
    python run_demo.py
"""

import subprocess
import sys
import time
import webbrowser
import os

HOST = "127.0.0.1"
PORT = 8000
URL = f"http://{HOST}:{PORT}"


def main():
    print("=" * 60)
    print("  HealX — Autonomous AI Debugger")
    print("  IBM Granite via watsonx.ai")
    print("=" * 60)
    print(f"\n  Dashboard  → {URL}")
    print(f"  API docs   → {URL}/docs")
    print("\n  Press Ctrl+C to stop.\n")

    # Start uvicorn in a subprocess
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app:app", "--host", HOST, "--port", str(PORT), "--reload"],
        cwd=os.path.dirname(os.path.abspath(__file__)),
    )

    # Wait a moment for server to start, then open browser
    time.sleep(1.5)
    webbrowser.open(URL)

    try:
        proc.wait()
    except KeyboardInterrupt:
        print("\nShutting down HealX dashboard...")
        proc.terminate()


if __name__ == "__main__":
    main()
