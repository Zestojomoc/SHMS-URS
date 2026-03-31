from apscheduler.schedulers.background import BackgroundScheduler
import subprocess
import sys
from core.services.shm_service import save_shm_history


process_running = False

def run_nfd_processor():
    global process_running

    if process_running:
        print("Processor already running, skipping...")
        return

    process_running = True
    print("Running NFD processor...")

    try:
        subprocess.run([sys.executable, "core/nfd_processor.py"])
    finally:
        process_running = False

def start():
    scheduler = BackgroundScheduler()

    # Run every 60 seconds
    scheduler.add_job(run_nfd_processor, "interval", seconds=60)
    
    
    scheduler.add_job(save_shm_history, "interval", seconds=60)

    scheduler.start()
    print("NFD monitoring scheduler started.")