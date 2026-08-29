"""
F1 Telemetry System - Network Receiver Thread (network.py)
Listens asynchronously for incoming UDP telemetry packets from simulator.py
without blocking the main GUI or computation thread.
Includes a Heartbeat Watchdog tracking signal status and loss delta.
"""

import socket
import json
import threading
import queue
import time
from typing import Optional

UDP_LISTEN_IP = "127.0.0.1"
UDP_LISTEN_PORT = 5005

class TelemetryReceiver(threading.Thread):
    def __init__(self, data_queue: queue.Queue, ip: str = UDP_LISTEN_IP, port: int = UDP_LISTEN_PORT):
        super().__init__(daemon=True)
        self.data_queue = data_queue
        self.ip = ip if ip else "127.0.0.1"
        self.port = port
        self.running = False
        self.sock: Optional[socket.socket] = None
        self.packets_received = 0
        self.packet_errors = 0
        self.last_packet_timestamp = time.time()
        self.signal_lost = False

    def run(self):
        """Asynchronous listening loop capturing UDP packets continuously."""
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        
        try:
            self.sock.bind((self.ip, self.port))
            self.sock.settimeout(0.2)  # 200ms socket timeout for watchdog check
            self.running = True
            print(f"[NETWORK RECEIVER] Listening on UDP {self.ip}:{self.port}...")

            while self.running:
                try:
                    data, addr = self.sock.recvfrom(65535)
                    now = time.time()
                    self.packets_received += 1
                    self.last_packet_timestamp = now
                    self.signal_lost = False
                    
                    packet = json.loads(data.decode('utf-8'))
                    
                    # Prevent queue overflow
                    if self.data_queue.full():
                        try:
                            self.data_queue.get_nowait()
                        except queue.Empty:
                            pass
                    
                    self.data_queue.put_nowait(packet)

                except socket.timeout:
                    # Watchdog check for signal loss (>200ms without packet)
                    if time.time() - self.last_packet_timestamp > 0.2:
                        self.signal_lost = True
                    continue
                except (json.JSONDecodeError, UnicodeDecodeError) as err:
                    self.packet_errors += 1
                    print(f"[NETWORK RECEIVER] Corrupt packet dropped: {err}")
                except Exception as e:
                    if self.running:
                        print(f"[NETWORK RECEIVER] Socket exception: {e}")

        except Exception as e:
            print(f"[NETWORK RECEIVER FATAL] Failed to bind UDP socket: {e}")
        finally:
            self.stop()

    def stop(self):
        """Gracefully close socket and terminate receiver loop."""
        self.running = False
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
        print("[NETWORK RECEIVER] UDP Socket closed.")
