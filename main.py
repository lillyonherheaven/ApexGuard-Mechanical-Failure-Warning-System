"""
F1 Telemetry System - Main Application Orchestrator (main.py)
Central entry point wiring up all modular components:
- Shared Thread-Safe Queue
- Telemetry UDP Simulator (20 Hz)
- Network Receiver Thread (Async UDP Listener)
- Deterministic Rule Engine & FSM Controller
- Dual-View CustomTkinter GUI Application
"""

import sys
import time
import queue
import threading
from simulator import TelemetrySimulator
from network import TelemetryReceiver
from gui import F1TelemetryGUI

def main():
    print("================================================================")
    print(" SCUDERIA FERRARI F1 REAL-TIME TELEMETRY & WARNING SYSTEM")
    print("================================================================")
    print("Booting Clean Architecture multi-threaded pipeline...")

    # 1. Shared Thread-Safe Queue
    telemetry_queue = queue.Queue(maxsize=500)

    # 2. Initialize Telemetry UDP Simulator (20 Hz)
    simulator = TelemetrySimulator(ip="127.0.0.1", port=5005)
    sim_thread = threading.Thread(target=simulator.start_broadcasting, daemon=True)
    sim_thread.start()
    print("[ORCHESTRATOR] Telemetry Simulator thread booted (20 Hz UDP stream).")

    # 3. Initialize Network Receiver Thread
    receiver = TelemetryReceiver(data_queue=telemetry_queue, ip="127.0.0.1", port=5005)
    receiver.start()
    print("[ORCHESTRATOR] Network Receiver thread booted (Async UDP listener).")

    # Allow sockets time to bind cleanly
    time.sleep(0.5)

    # 4. Launch GUI Application (Driver DDU + Pit-Wall Console)
    print("[ORCHESTRATOR] Launching Dual-View GUI Application...")
    try:
        app = F1TelemetryGUI(telemetry_queue=telemetry_queue, simulator_ref=simulator)
        app.run()
    except Exception as e:
        print(f"[ORCHESTRATOR ERROR] GUI execution interrupted: {e}")
    finally:
        print("[ORCHESTRATOR SHUTDOWN] Terminating simulator and receiver sockets...")
        simulator.running = False
        receiver.stop()
        print("[ORCHESTRATOR SHUTDOWN] System cleanly terminated.")

if __name__ == "__main__":
    main()
