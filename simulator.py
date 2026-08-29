"""
F1 Telemetry System - UDP Simulator (simulator.py)
Broadcasting live telemetry data packets (JSON format) at 20 Hz (every 50ms).
Features:
- Track-position velocity profile linked to lap_progress (0.0 to 1.0)
- Realistic gear shifts synchronized with vehicle speed
- Weather physics (Track Rain %, Track Temp °C, Tire Compound)
- Engine modes (PUSH, SAVE FUEL, OVERTAKE)
- Brake Bias % and ERS State of Charge (SoC %)
- Terminal Crash (DNF) logic with simulation freeze
- Fault injection triggers (Oil leak, tire overheat, brake thermal runaway, etc.)
"""

import socket
import json
import time
import random
import threading
import math
from typing import Dict, Any

UDP_IP = "127.0.0.1"
UDP_PORT = 5005
FREQUENCY_HZ = 20
INTERVAL_SEC = 1.0 / FREQUENCY_HZ

class TelemetrySimulator:
    def __init__(self, ip: str = UDP_IP, port: int = UDP_PORT):
        self.ip = ip
        self.port = port
        self.running = False
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        
        # Drivers & Track Config
        self.driver_name = "C. LECLERC"
        self.driver_number = 16
        self.team_name = "SCUDERIA FERRARI"
        self.track_name = "MONZA - ITALY (HOME RACE)"
        self.total_laps = 53
        self.current_lap = 14
        self.position = "P1"
        self.delta_time = 0.142

        # Telemetry Baselines
        self.time_elapsed = 0.0
        self.lap_progress = 0.0  # 0.0 to 1.0 along the lap
        self.speed = 285.0       # km/h
        self.rpm = 12200         # RPM
        self.gear = 7
        self.lap_time = 84.200    # seconds
        
        # Engine Mode: "PUSH", "SAVE_FUEL", "OVERTAKE"
        self.engine_mode = "PUSH"
        self.drs_enabled = False
        self.drs_available = True
        
        # Weather & Strategy Engine
        self.track_temp_c = 38.0
        self.track_rain_pct = 0.0   # 0% to 100%
        self.tire_compound = "SOFT" # SOFT, MEDIUM, HARD, INTERMEDIATE, WET
        
        # Brake Bias & ERS SoC
        self.brake_bias_pct = 55.5  # % Front
        self.ers_soc_pct = 82.0     # 0.0 to 100.0 %
        self.ers_state = "HARVESTING" # HARVESTING or DEPLOYING
        
        # Tire Surface Temps (°C) & Wear (%)
        self.tire_temp_fl = 92.0
        self.tire_temp_fr = 94.0
        self.tire_temp_rl = 89.0
        self.tire_temp_rr = 91.0
        
        self.tire_wear_fl = 35.0
        self.tire_wear_fr = 38.0
        self.tire_wear_rl = 30.0
        self.tire_wear_rr = 32.0

        self.tire_pressure_fl = 23.5  # PSI
        self.tire_pressure_fr = 23.8  # PSI
        self.tire_pressure_rl = 21.2  # PSI
        self.tire_pressure_rr = 21.4  # PSI
        
        # Engine Metrics
        self.engine_oil_pressure = 72.0  # PSI
        self.engine_temp = 108.0         # °C
        self.hydraulic_pressure = 2850.0  # PSI
        self.fuel_flow_rate = 98.5        # kg/h
        
        # Brake Temps (°C)
        self.brake_temp_fl = 580.0
        self.brake_temp_fr = 610.0
        self.brake_temp_rl = 540.0
        self.brake_temp_rr = 550.0
        
        # Terminal Crash / DNF Logic
        self.is_crashed = False
        self.crash_reason = ""
        self.crash_sector = ""

        # Fault Injection Flags
        self.fault_oil_leak = False
        self.fault_tire_overheat = False
        self.fault_brake_runaway = False
        self.fault_hydraulic_drop = False
        self.fault_engine_overheat = False

    def set_engine_mode(self, mode: str):
        """Dynamic signal receiver from GUI to change engine modes."""
        valid_modes = ["PUSH", "SAVE_FUEL", "OVERTAKE"]
        if mode in valid_modes:
            self.engine_mode = mode
            print(f"[SIMULATOR] Engine Mode Updated -> {self.engine_mode}")

    def set_driver_and_track(self, driver: str, track: str):
        """Dynamic update for driver name and track selection."""
        if "HAMILTON" in driver:
            self.driver_name = "L. HAMILTON"
            self.driver_number = 44
            self.team_name = "SCUDERIA FERRARI"
        elif "VERSTAPPEN" in driver:
            self.driver_name = "M. VERSTAPPEN"
            self.driver_number = 1
            self.team_name = "RED BULL RACING"
        elif "NORRIS" in driver:
            self.driver_name = "L. NORRIS"
            self.driver_number = 4
            self.team_name = "MCLAREN F1"
        elif "SAINZ" in driver:
            self.driver_name = "C. SAINZ"
            self.driver_number = 55
            self.team_name = "WILLIAMS RACING"
        else:
            self.driver_name = "C. LECLERC"
            self.driver_number = 16
            self.team_name = "SCUDERIA FERRARI"

        self.track_name = track
        if "SPA" in track:
            self.total_laps = 44
        elif "SILVERSTONE" in track:
            self.total_laps = 52
        elif "JEDDAH" in track:
            self.total_laps = 50
        elif "MONACO" in track:
            self.total_laps = 78
        else:
            self.total_laps = 53

    def trigger_oil_leak(self):
        self.fault_oil_leak = True
        print("[SIMULATOR FAULT] -> Sudden Oil Leak Injected!")

    def trigger_tire_overheat(self):
        self.fault_tire_overheat = True
        print("[SIMULATOR FAULT] -> Rapid Tire Overheat Injected!")

    def trigger_brake_runaway(self):
        self.fault_brake_runaway = True
        print("[SIMULATOR FAULT] -> Brake Thermal Runaway Injected!")

    def trigger_hydraulic_drop(self):
        self.fault_hydraulic_drop = True
        print("[SIMULATOR FAULT] -> Hydraulic System Failure Injected!")

    def trigger_engine_overheat(self):
        self.fault_engine_overheat = True
        print("[SIMULATOR FAULT] -> Engine Thermal Overheat Injected!")

    def trigger_crash(self, reason: str = "HIGH SPEED IMPACT AT TURN 4"):
        """Triggers terminal DNF state."""
        self.is_crashed = True
        self.crash_reason = reason
        self.crash_sector = f"SECTOR {int(self.lap_progress * 3) + 1}"
        self.speed = 0.0
        self.rpm = 0
        print(f"[SIMULATOR DNF] -> CRASH DETECTED: {reason}")

    def reset_faults(self):
        """Resets all faults and clears crash state."""
        self.fault_oil_leak = False
        self.fault_tire_overheat = False
        self.fault_brake_runaway = False
        self.fault_hydraulic_drop = False
        self.fault_engine_overheat = False
        
        self.is_crashed = False
        self.crash_reason = ""
        self.crash_sector = ""

        self.engine_oil_pressure = 72.0
        self.engine_temp = 108.0
        self.hydraulic_pressure = 2850.0
        self.tire_temp_fl = 92.0
        self.tire_temp_fr = 94.0
        self.tire_temp_rl = 89.0
        self.tire_temp_rr = 91.0
        self.tire_wear_fl = 35.0
        self.tire_wear_fr = 38.0
        self.tire_wear_rl = 30.0
        self.tire_wear_rr = 32.0
        self.tire_pressure_fl = 23.5
        self.tire_pressure_fr = 23.8
        self.tire_pressure_rl = 21.2
        self.tire_pressure_rr = 21.4
        self.brake_temp_fl = 580.0
        self.brake_temp_fr = 610.0
        self.brake_temp_rl = 540.0
        self.brake_temp_rr = 550.0
        print("[SIMULATOR RESET] -> All telemetry and crash states restored.")

    def update_physics(self, dt: float):
        """Realistic F1 track position-based velocity profile and thermal physics."""
        if self.is_crashed:
            # Freeze simulation movement on crash
            self.speed = 0.0
            self.rpm = 0
            self.gear = 0
            return

        self.time_elapsed += dt
        
        # Lap progress tracking (0.0 -> 1.0)
        progress_rate = 0.012 * (self.speed / 280.0) * dt
        self.lap_progress = (self.lap_progress + progress_rate) % 1.0
        if self.lap_progress < progress_rate:
            self.current_lap += 1

        # Track Position Velocity Profile linked to lap_progress
        # Straights: 0.1->0.4 & 0.6->0.9 (Full acceleration, 330-395 km/h)
        # Heavy Braking / Chicanes: 0.4->0.5 & 0.9->1.0 (Deceleration down to 80-130 km/h)
        p = self.lap_progress
        if (0.1 <= p < 0.4) or (0.6 <= p < 0.9):
            # Straight Line Acceleration
            target_speed = 365.0 if not self.drs_enabled else 388.0
            if self.engine_mode == "PUSH":
                target_speed += 8.0
            elif self.engine_mode == "SAVE_FUEL":
                target_speed -= 15.0
            elif self.engine_mode == "OVERTAKE":
                target_speed += 14.0

            # Smooth acceleration towards target
            self.speed = min(395.0, self.speed + (65.0 * dt))
            self.ers_state = "DEPLOYING"
            self.ers_soc_pct = max(10.0, self.ers_soc_pct - (1.2 * dt))
            self.drs_enabled = True if (p > 0.18 and self.speed > 270) else False
        else:
            # Heavy Braking Zone
            self.speed = max(88.0, self.speed - (140.0 * dt))
            self.ers_state = "HARVESTING"
            self.ers_soc_pct = min(100.0, self.ers_soc_pct + (2.5 * dt))
            self.drs_enabled = False
            
            # Spike brake temperatures in braking zones
            brake_spike = 45.0 * dt
            self.brake_temp_fl += brake_spike * (self.brake_bias_pct / 50.0)
            self.brake_temp_fr += brake_spike * (self.brake_bias_pct / 50.0)
            self.brake_temp_rl += brake_spike * ((100 - self.brake_bias_pct) / 50.0)
            self.brake_temp_rr += brake_spike * ((100 - self.brake_bias_pct) / 50.0)

        # Synchronize Gear strictly with Speed Thresholds
        if self.speed < 95.0:
            self.gear = 2
        elif self.speed < 140.0:
            self.gear = 3
        elif self.speed < 185.0:
            self.gear = 4
        elif self.speed < 230.0:
            self.gear = 5
        elif self.speed < 280.0:
            self.gear = 6
        elif self.speed < 335.0:
            self.gear = 7
        else:
            self.gear = 8

        # RPM Calculation tied to gear and speed
        min_rpm_gear = 8200
        max_rpm_gear = 14500
        gear_speed_ratio = (self.speed % 55.0) / 55.0
        self.rpm = int(min_rpm_gear + gear_speed_ratio * (max_rpm_gear - min_rpm_gear) + random.randint(-80, 80))
        self.rpm = max(3500, min(14800, self.rpm))

        # Check for Extreme Unhandled Terminal Crash Conditions
        if self.tire_wear_fr > 92.0 and self.speed > 160.0:
            self.trigger_crash("TIRE BLOWOUT IMPACT AT HIGH SPEED")
            return
        if self.engine_temp > 142.0 and self.time_elapsed > 10.0:
            self.trigger_crash("CATASTROPHIC ENGINE EXPLOSION")
            return

        # Engine Mode modifiers
        if self.engine_mode == "PUSH":
            self.fuel_flow_rate = 99.8
            engine_temp_target = 112.0
        elif self.engine_mode == "SAVE_FUEL":
            self.fuel_flow_rate = 88.2
            engine_temp_target = 101.0
        else: # OVERTAKE
            self.fuel_flow_rate = 100.0
            engine_temp_target = 116.0

        # Baseline thermal and wear dynamics
        self.tire_wear_fl += 0.015 * dt
        self.tire_wear_fr += 0.018 * dt
        self.tire_wear_rl += 0.012 * dt
        self.tire_wear_rr += 0.014 * dt

        # FAULT DYNAMICS SIMULATION
        if self.fault_oil_leak:
            self.engine_oil_pressure = max(5.0, self.engine_oil_pressure - (0.85 * dt))
            self.engine_temp = min(145.0, self.engine_temp + (0.65 * dt))
        else:
            self.engine_oil_pressure = max(65.0, min(82.0, self.engine_oil_pressure + random.uniform(-0.1, 0.1)))

        if self.fault_engine_overheat:
            self.engine_temp = min(150.0, self.engine_temp + (1.2 * dt))
        elif not self.fault_oil_leak:
            self.engine_temp += (engine_temp_target - self.engine_temp) * 0.05 * dt + random.uniform(-0.1, 0.1)

        if self.fault_tire_overheat:
            self.tire_temp_fl = min(160.0, self.tire_temp_fl + (2.8 * dt))
            self.tire_temp_fr = min(165.0, self.tire_temp_fr + (3.2 * dt))
            self.tire_wear_fr = min(98.0, self.tire_wear_fr + 0.8 * dt)
        else:
            self.tire_temp_fl = max(80.0, min(115.0, self.tire_temp_fl + random.uniform(-0.2, 0.2)))
            self.tire_temp_fr = max(80.0, min(118.0, self.tire_temp_fr + random.uniform(-0.2, 0.2)))

        if self.fault_brake_runaway:
            self.brake_temp_fl = min(1150.0, self.brake_temp_fl + (35.0 * dt))
            self.brake_temp_fr = min(1180.0, self.brake_temp_fr + (38.0 * dt))
            self.brake_temp_rl = min(1020.0, self.brake_temp_rl + (25.0 * dt))
            self.brake_temp_rr = min(1040.0, self.brake_temp_rr + (28.0 * dt))
        else:
            self.brake_temp_fl = max(380.0, min(780.0, self.brake_temp_fl - (12.0 * dt)))
            self.brake_temp_fr = max(380.0, min(800.0, self.brake_temp_fr - (12.0 * dt)))
            self.brake_temp_rl = max(350.0, min(720.0, self.brake_temp_rl - (12.0 * dt)))
            self.brake_temp_rr = max(350.0, min(730.0, self.brake_temp_rr - (12.0 * dt)))

        if self.fault_hydraulic_drop:
            self.hydraulic_pressure = max(300.0, self.hydraulic_pressure - (45.0 * dt))
        else:
            self.hydraulic_pressure = max(2700.0, min(3000.0, self.hydraulic_pressure + random.uniform(-5.0, 5.0)))

    def generate_packet(self) -> Dict[str, Any]:
        """
        Constructs telemetry packet containing ALL sensor key variants
        to eliminate key-mismatch discrepancies between modules!
        """
        now = time.time()
        packet = {
            "timestamp": now,
            "Timestamp": now,
            "driver_name": self.driver_name,
            "driver_number": self.driver_number,
            "team_name": self.team_name,
            "track_name": self.track_name,
            "total_laps": self.total_laps,
            "lap": self.current_lap,
            "lap_progress": round(self.lap_progress, 4),
            "position": self.position,
            "delta_time": self.delta_time,
            
            # Kinematics
            "Speed": round(self.speed, 1),
            "RPM": self.rpm,
            "Gear": self.gear,
            "Throttle": round(95.0 if self.speed > 200 else 40.0, 1),
            "Brake": round(80.0 if self.speed < 150 else 0.0, 1),
            "DRS": 1 if self.drs_enabled else 0,
            "Engine_Mode": self.engine_mode,

            # Weather & Strategy Engine
            "Track_Temp_C": round(self.track_temp_c, 1),
            "Track_Rain_%": round(self.track_rain_pct, 1),
            "Tire_Compound": self.tire_compound,
            
            # ERS & Brake Bias
            "Brake_Bias_%": round(self.brake_bias_pct, 1),
            "ERS_SoC_%": round(self.ers_soc_pct, 1),
            "ERS_State": self.ers_state,

            # Tire Temperatures (°C) - Dual Naming Convention for 100% Compatibility
            "Tire_Temp_FL": round(self.tire_temp_fl, 2),
            "Tire_Temp_FR": round(self.tire_temp_fr, 2),
            "Tire_Temp_RL": round(self.tire_temp_rl, 2),
            "Tire_Temp_RR": round(self.tire_temp_rr, 2),
            "FL_Tire_Temp": round(self.tire_temp_fl, 2),
            "FR_Tire_Temp": round(self.tire_temp_fr, 2),
            "RL_Tire_Temp": round(self.tire_temp_rl, 2),
            "RR_Tire_Temp": round(self.tire_temp_rr, 2),

            # Tire Pressures (PSI)
            "FL_Tire_Pressure": round(self.tire_pressure_fl, 2),
            "FR_Tire_Pressure": round(self.tire_pressure_fr, 2),
            "RL_Tire_Pressure": round(self.tire_pressure_rl, 2),
            "RR_Tire_Pressure": round(self.tire_pressure_rr, 2),

            # Tire Wear (%)
            "Tire_Wear_FL": round(self.tire_wear_fl, 2),
            "Tire_Wear_FR": round(self.tire_wear_fr, 2),
            "Tire_Wear_RL": round(self.tire_wear_rl, 2),
            "Tire_Wear_RR": round(self.tire_wear_rr, 2),
            "FL_Tire_Wear": round(self.tire_wear_fl, 2),
            "FR_Tire_Wear": round(self.tire_wear_fr, 2),
            "RL_Tire_Wear": round(self.tire_wear_rl, 2),
            "RR_Tire_Wear": round(self.tire_wear_rr, 2),

            # Engine Systems
            "Engine_Oil_Pressure": round(self.engine_oil_pressure, 2),
            "Engine_Temp": round(self.engine_temp, 2),
            "Hydraulic_Pressure": round(self.hydraulic_pressure, 1),
            "Fuel_Flow_Rate": round(self.fuel_flow_rate, 2),

            # Brake Temperatures (°C)
            "Brake_Temp_FL": round(self.brake_temp_fl, 1),
            "Brake_Temp_FR": round(self.brake_temp_fr, 1),
            "Brake_Temp_RL": round(self.brake_temp_rl, 1),
            "Brake_Temp_RR": round(self.brake_temp_rr, 1),
            "FL_Brake_Temp": round(self.brake_temp_fl, 1),
            "FR_Brake_Temp": round(self.brake_temp_fr, 1),
            "RL_Brake_Temp": round(self.brake_temp_rl, 1),
            "RR_Brake_Temp": round(self.brake_temp_rr, 1),

            # Terminal Crash State
            "is_crashed": self.is_crashed,
            "crash_reason": self.crash_reason,
            "crash_sector": self.crash_sector
        }
        return packet

    def start_broadcasting(self):
        self.running = True
        print(f"[SIMULATOR] UDP Telemetry Stream active on {self.ip}:{self.port} at {FREQUENCY_HZ} Hz...")
        last_time = time.time()
        
        try:
            while self.running:
                now = time.time()
                dt = now - last_time
                last_time = now
                
                self.update_physics(dt)
                packet = self.generate_packet()
                payload = json.dumps(packet).encode('utf-8')
                
                try:
                    self.sock.sendto(payload, (self.ip, self.port))
                except Exception as e:
                    print(f"[SIMULATOR SOCKET ERROR] {e}")
                
                elapsed = time.time() - now
                sleep_time = max(0.001, INTERVAL_SEC - elapsed)
                time.sleep(sleep_time)
                
        except Exception as e:
            print(f"[SIMULATOR EXCEPTION] {e}")
        finally:
            self.sock.close()
