import time
import subprocess
import sys

print("Starting NFD monitoring loop...")

while True:
    try:
        print("Running NFD processor...")

        # Use the SAME Python interpreter as the venv
        subprocess.run([sys.executable, "core/nfd_processor.py"])

        print("Waiting 30 seconds for next analysis...\n")
        time.sleep(30)

    except KeyboardInterrupt:
        print("Monitoring stopped.")
        break