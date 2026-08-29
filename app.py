"""
===============================================================================
 ApexGuard - F1 Real-Time Telemetry & Mechanical Failure Early Warning System
 Hugging Face Spaces Deployment Entrypoint (Gradio 6.0+, ZeroGPU & Plotly)
 Scuderia Ferrari F1 Team (Rosso Corsa #CE2B37, Giallo Modena #FFD700)
===============================================================================
"""

import time
import math
import os
import random
import numpy as np
import pandas as pd
import gradio as gr
import plotly.graph_objects as go

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    from google import genai
    from google.genai import types
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False

# =============================================================================
# ZeroGPU COMPATIBILITY DECORATOR FOR HUGGING FACE SPACES
# =============================================================================
try:
    import spaces
except ImportError:
    class spaces:
        @staticmethod
        def GPU(func=None, duration=None):
            if callable(func):
                return func
            def decorator(f):
                return f
            return decorator


# =============================================================================
# 1. VISUAL STYLING & FERRARI SCUDERIA BRAND IDENTITY (CSS)
# =============================================================================
CUSTOM_CSS = """
body, .gradio-container {
    background-color: #0F0F0F !important;
    color: #FFFFFF !important;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif !important;
}
.ferrari-header {
    background: linear-gradient(90deg, #CE2B37 0%, #181818 100%) !important;
    padding: 14px 20px !important;
    border-radius: 8px !important;
    margin-bottom: 12px !important;
    border-left: 6px solid #FFD700 !important;
    box-shadow: 0 4px 14px rgba(206, 43, 55, 0.25) !important;
}
.tricolore-bar {
    height: 5px !important;
    background: linear-gradient(90deg, #009246 33%, #FFFFFF 33%, #FFFFFF 66%, #CE2B37 66%) !important;
    border-radius: 2px !important;
    margin-bottom: 10px !important;
}
.metric-box {
    background-color: #181818 !important;
    border: 1px solid #2A2A2A !important;
    border-radius: 8px !important;
    padding: 14px !important;
}
.status-nominal {
    border: 2px solid #00FF66 !important;
    background-color: rgba(0, 255, 102, 0.08) !important;
    color: #00FF66 !important;
}
.status-warning {
    border: 2px solid #FFD700 !important;
    background-color: rgba(255, 215, 0, 0.09) !important;
    color: #FFD700 !important;
}
.status-critical {
    border: 2px solid #CE2B37 !important;
    background-color: rgba(206, 43, 55, 0.18) !important;
    color: #CE2B37 !important;
}
.ai-advisor-container {
    background-color: #141414 !important;
    border: 1px solid #CE2B37 !important;
    border-radius: 8px !important;
    padding: 16px !important;
    margin-top: 14px !important;
    box-shadow: 0 4px 16px rgba(206, 43, 55, 0.15) !important;
}
.ai-badge {
    background-color: #CE2B37 !important;
    color: #FFFFFF !important;
    font-weight: 700 !important;
    font-size: 11px !important;
    padding: 3px 8px !important;
    border-radius: 4px !important;
    display: inline-block !important;
    margin-right: 8px !important;
}
"""

# =============================================================================
# 2. DETERMINISTIC MONZA CIRCUIT GEOMETRY & CURVATURE PROFILE
# =============================================================================
def generate_monza_geometry(num_points: int = 180):
    """
    Constructs high-density 2D vector spline coordinates and curvature profile for Monza:
    - Rettifilo Main Straight (DRS Zone 1, speeds up to 350 km/h)
    - Variante del Rettifilo (Heavy Braking, Chicanes, high G-force)
    - Curva Grande (High-speed sweeping right curve, lateral G)
    - Variante della Roggia (Chicane 2)
    - Curva di Lesmo 1 & 2 (Medium speed technical corners)
    - Serraglio Straight (DRS Zone 2)
    - Variante Ascari (High lateral transient chicane)
    - Rettifilo Posteriore & Curva Parabolica (Curva Alboreto high lateral load)
    """
    raw_x = [0, 60, 120, 180, 220, 240, 230, 200, 150, 120, 110, 130, 170, 190, 170, 100, 30, -10, 0]
    raw_y = [0, 0, 5, 20, 30, 60, 80, 85, 75, 65, 75, 105, 115, 135, 150, 150, 110, 40, 0]

    raw_x = np.array(raw_x, dtype=float)
    raw_y = np.array(raw_y, dtype=float)
    
    t_raw = np.linspace(0, 1, len(raw_x))
    t_fine = np.linspace(0, 1, num_points, endpoint=False)
    
    fine_x = np.interp(t_fine, t_raw, raw_x)
    fine_y = np.interp(t_fine, t_raw, raw_y)
    
    # Calculate track tangent vectors and curvature (d_theta / ds)
    dx = np.gradient(fine_x)
    dy = np.gradient(fine_y)
    headings = np.arctan2(dy, dx)
    
    # Heading derivative gives corner sharpness / curvature magnitude
    d_heading = np.gradient(np.unwrap(headings))
    ds = np.sqrt(dx**2 + dy**2)
    curvature = np.abs(d_heading / np.maximum(ds, 1e-4))
    
    # Normalize curvature 0.0 (pure straight) to 1.0 (hairpin/chicane apex)
    norm_curv = curvature / (np.max(curvature) + 1e-4)
    norm_curv = np.clip(norm_curv * 1.5, 0.0, 1.0)
    
    # Define DRS Zones based on progression ratio (Rettifilo Straight & Serraglio Straight)
    drs_zones = []
    for i in range(num_points):
        p = i / num_points
        # Straight 1: Start/Finish (0.0 to 0.16) and Serraglio Straight (0.58 to 0.72)
        is_drs = (0.0 <= p <= 0.15) or (0.58 <= p <= 0.72)
        drs_zones.append(is_drs)

    return fine_x, fine_y, headings, norm_curv, drs_zones

MONZA_X, MONZA_Y, MONZA_HEADINGS, MONZA_CURVATURE, MONZA_DRS = generate_monza_geometry(180)
TOTAL_TRACK_POINTS = len(MONZA_X)


# =============================================================================
# 3. DETERMINISTIC PHYSICS & RATE-OF-CHANGE (d/dt) EARLY FAILURE ENGINE
# =============================================================================
TYRE_SPECS = {
    "SOFT (C5 - High Grip, Fast Wear)": {
        "grip_coeff": 1.15,
        "wear_rate": 0.038,
        "heat_gen": 1.25,
        "base_temp": 102.0,
        "name": "SOFT"
    },
    "MEDIUM (C4 - Balanced)": {
        "grip_coeff": 1.00,
        "wear_rate": 0.022,
        "heat_gen": 1.00,
        "base_temp": 95.0,
        "name": "MEDIUM"
    },
    "HARD (C3 - Low Grip, High Durability)": {
        "grip_coeff": 0.88,
        "wear_rate": 0.011,
        "heat_gen": 0.80,
        "base_temp": 88.0,
        "name": "HARD"
    }
}


class DeterministicPhysicsTelemetryEngine:
    def __init__(self):
        self.driver_name = "C. LECLERC [16] - SCUDERIA FERRARI"
        self.compound_key = "MEDIUM (C4 - Balanced)"
        self.engine_mode = "PUSH"  # PUSH, SAVE_FUEL, OVERTAKE
        
        # Vehicle Mass Dynamics (Fuel depletion model)
        self.fuel_mass_kg = 110.0  # Initial race fuel mass
        self.dry_car_mass_kg = 798.0  # FIA minimum regulations
        self.lap_count = 1
        
        # Dynamic State Variables
        self.speed_kmh = 310.0
        self.gear = 7
        self.rpm = 12600
        self.drs_active = False
        self.ers_soc = 86.0
        
        # G-Force Telemetry (Lateral and Longitudinal in units of g)
        self.g_lat = 0.0
        self.g_lon = 0.0
        
        # Powertrain & Hydraulics (Absolute Sensor Values)
        self.engine_temp_c = 104.5   # Target: 100 - 110 °C
        self.oil_pressure_bar = 4.85 # Target: 4.5 - 5.5 bar (1 bar ≈ 14.5 PSI)
        self.hyd_pressure_bar = 195.0 # Target: 180 - 210 bar
        self.brake_temp_c = 620.0    # Target: 500 - 800 °C
        
        # Rate of Change derivatives (d/dt: per second)
        self.prev_engine_temp_c = 104.5
        self.prev_oil_pressure_bar = 4.85
        self.d_temp_dt = 0.0  # °C / sec
        self.d_oil_dt = 0.0   # bar / sec
        
        # 4-Wheel Tyre Matrix (Temperatures & Degradation)
        self.tire_fl_temp = 96.0
        self.tire_fr_temp = 98.0
        self.tire_rl_temp = 93.0
        self.tire_rr_temp = 94.0
        
        self.tire_fl_wear = 22.0  # %
        self.tire_fr_wear = 24.5  # %
        self.tire_rl_wear = 19.0  # %
        self.tire_rr_wear = 20.2  # %
        
        # Fault Injection Flags
        self.fault_oil_leak = False
        self.fault_engine_overheat = False
        self.fault_tire_thermal_runaway = False
        
        # System FSM State ('NOMINAL', 'EARLY_WARNING', 'CRITICAL')
        self.system_state = "NOMINAL"
        self.last_logged_state = "NOMINAL"
        
        # Blackbox history records
        self.action_logs = [f"[{time.strftime('%H:%M:%S')}] Telemetry initialized. Nominal baseline established."]
        self.history = []

    def log_event(self, message: str):
        timestamp = time.strftime('%H:%M:%S')
        log_entry = f"[{timestamp}] {message}"
        self.action_logs.insert(0, log_entry)
        if len(self.action_logs) > 40:
            self.action_logs.pop()

    def update_physics_step(self, step_idx: int, dt: float = 0.1):
        """
        Deterministic physics step mapped to track curvature, aerodynamic drag,
        engine mode, fuel mass dissipation, and sensor rate-of-change (d/dt).
        """
        curv = MONZA_CURVATURE[step_idx]
        is_drs_eligible = MONZA_DRS[step_idx]
        compound = TYRE_SPECS.get(self.compound_key, TYRE_SPECS["MEDIUM (C4 - Balanced)"])
        
        # 1. Fuel Mass Burn Rate (~2.4 kg per lap at Monza)
        fuel_burn = 0.015 * (1.3 if self.engine_mode == "OVERTAKE" else (0.8 if self.engine_mode == "SAVE_FUEL" else 1.0))
        self.fuel_mass_kg = max(2.0, self.fuel_mass_kg - fuel_burn)
        total_mass = self.dry_car_mass_kg + self.fuel_mass_kg
        mass_accel_factor = (908.0 / total_mass) ** 0.5  # Lighter car accelerates faster
        
        # 2. Track Curvature-Based Target Speed & DRS Logic
        # On straights (curv < 0.15) -> 335-350 km/h; In apexes (curv > 0.7) -> 105-130 km/h
        base_corner_speed = 345.0 - (curv * 230.0 * (1.0 / compound["grip_coeff"]))
        
        # DRS actuation on eligible straights
        self.drs_active = is_drs_eligible and (self.speed_kmh > 260.0)
        drs_speed_bonus = 12.5 if self.drs_active else 0.0
        
        mode_speed_bias = 8.0 if self.engine_mode == "OVERTAKE" else (-12.0 if self.engine_mode == "SAVE_FUEL" else 0.0)
        target_speed = (base_corner_speed + drs_speed_bonus + mode_speed_bias) * mass_accel_factor
        
        # Smooth vehicle momentum transition
        smoothing = 0.22 if target_speed > self.speed_kmh else 0.38  # Braking is sharper than acceleration
        self.speed_kmh = (1.0 - smoothing) * self.speed_kmh + smoothing * target_speed + random.uniform(-0.8, 0.8)
        
        # 3. Gear & RPM Deterministic Mapping
        if self.speed_kmh < 110: self.gear = 2; self.rpm = int(9200 + (self.speed_kmh / 110.0) * 3200)
        elif self.speed_kmh < 155: self.gear = 3; self.rpm = int(9800 + ((self.speed_kmh - 110) / 45.0) * 3100)
        elif self.speed_kmh < 205: self.gear = 4; self.rpm = int(10200 + ((self.speed_kmh - 155) / 50.0) * 2900)
        elif self.speed_kmh < 255: self.gear = 5; self.rpm = int(10600 + ((self.speed_kmh - 205) / 50.0) * 2800)
        elif self.speed_kmh < 298: self.gear = 6; self.rpm = int(11000 + ((self.speed_kmh - 255) / 43.0) * 2600)
        elif self.speed_kmh < 332: self.gear = 7; self.rpm = int(11400 + ((self.speed_kmh - 298) / 34.0) * 2400)
        else: self.gear = 8; self.rpm = int(12200 + min(1600, ((self.speed_kmh - 332) / 25.0) * 1600))
        
        # 4. G-Force Equations (Lateral & Longitudinal GG Diagram)
        # Lateral G = (v^2 / R) ~ proportional to (speed^2 * curvature)
        speed_ms = self.speed_kmh / 3.6
        raw_g_lat = (curv * (speed_ms ** 1.65)) / 220.0 * compound["grip_coeff"]
        # Sign lateral G based on track heading changes
        d_head = MONZA_HEADINGS[(step_idx + 1) % TOTAL_TRACK_POINTS] - MONZA_HEADINGS[step_idx]
        sign_lat = 1.0 if d_head >= 0 else -1.0
        self.g_lat = float(np.clip(sign_lat * raw_g_lat, -4.8, 4.8))
        
        # Longitudinal G = dv/dt (acceleration > 0, braking < 0)
        dv = target_speed - self.speed_kmh
        if dv < -15.0: # Heavy Braking Zone
            self.g_lon = float(np.clip(dv / 25.0, -5.2, -0.2))
            self.brake_temp_c = min(1080.0, self.brake_temp_c + abs(self.g_lon) * 18.0)
        else: # Acceleration or Coasting
            self.g_lon = float(np.clip(dv / 40.0, 0.0, 2.2))
            self.brake_temp_c = max(450.0, self.brake_temp_c - (self.speed_kmh / 300.0) * 14.0)

        # 5. ERS Battery State of Charge
        if self.engine_mode == "OVERTAKE": self.ers_soc = max(4.0, self.ers_soc - 0.18)
        elif self.engine_mode == "SAVE_FUEL": self.ers_soc = min(98.0, self.ers_soc + 0.15)
        else: self.ers_soc = max(15.0, min(95.0, self.ers_soc + (0.10 if self.g_lon < 0 else -0.04)))

        # 6. Tyre Wear & Thermal Evolution
        speed_factor = self.speed_kmh / 300.0
        load_heat = (abs(self.g_lat) * 2.8 + abs(self.g_lon) * 1.5) * compound["heat_gen"]
        cooling = speed_factor * 2.4
        target_tire_temp = compound["base_temp"] + load_heat - cooling
        
        # Asymmetric wear for Monza (Higher load on front-right FR and rear-right RR in Curva Grande & Parabolica)
        self.tire_fl_temp = 0.92 * self.tire_fl_temp + 0.08 * (target_tire_temp + random.uniform(-0.4, 0.4))
        self.tire_fr_temp = 0.92 * self.tire_fr_temp + 0.08 * (target_tire_temp + 2.5 + random.uniform(-0.4, 0.4))
        self.tire_rl_temp = 0.92 * self.tire_rl_temp + 0.08 * (target_tire_temp - 3.0 + random.uniform(-0.4, 0.4))
        self.tire_rr_temp = 0.92 * self.tire_rr_temp + 0.08 * (target_tire_temp - 1.5 + random.uniform(-0.4, 0.4))
        
        wear_increment = compound["wear_rate"] * (1.0 + abs(self.g_lat) * 0.4)
        self.tire_fl_wear = min(100.0, self.tire_fl_wear + wear_increment * 0.9)
        self.tire_fr_wear = min(100.0, self.tire_fr_wear + wear_increment * 1.1)
        self.tire_rl_wear = min(100.0, self.tire_rl_wear + wear_increment * 0.85)
        self.tire_rr_wear = min(100.0, self.tire_rr_wear + wear_increment * 0.95)

        # 7. Powertrain Thermals & Pressure with Failure Injections
        # Nominal physics values
        nominal_oil = 4.85 + (self.rpm / 13000.0) * 0.45
        nominal_temp = 103.0 + (self.speed_kmh / 350.0) * 4.0

        if self.fault_oil_leak:
            # Continuous pressure drop
            self.oil_pressure_bar = max(0.4, self.oil_pressure_bar - 0.065)
            # Loss of lubrication rapidly drives up engine thermals
            self.engine_temp_c = min(138.0, self.engine_temp_c + 0.38)
        else:
            # Settle back to nominal
            self.oil_pressure_bar = 0.88 * self.oil_pressure_bar + 0.12 * nominal_oil + random.uniform(-0.02, 0.02)

        if self.fault_engine_overheat:
            self.engine_temp_c = min(142.0, self.engine_temp_c + 0.48)
        elif not self.fault_oil_leak:
            self.engine_temp_c = 0.90 * self.engine_temp_c + 0.10 * nominal_temp + random.uniform(-0.1, 0.1)

        # 8. Compute Rate-of-Change Derivatives (d/dt: per second)
        self.d_temp_dt = (self.engine_temp_c - self.prev_engine_temp_c) / dt
        self.d_oil_dt = (self.oil_pressure_bar - self.prev_oil_pressure_bar) / dt
        
        self.prev_engine_temp_c = self.engine_temp_c
        self.prev_oil_pressure_bar = self.oil_pressure_bar

        # Lap counter increment
        if step_idx == 0:
            self.lap_count += 1

        # 9. Evaluate State & Rate-of-Change Early Failure Rules
        self.evaluate_early_warning_rules()

        # Blackbox Record Buffer
        record = {
            "timestamp": time.strftime("%H:%M:%S"),
            "lap": self.lap_count,
            "speed_kmh": round(self.speed_kmh, 1),
            "gear": self.gear,
            "rpm": self.rpm,
            "drs": "ACTIVE" if self.drs_active else "OFF",
            "oil_press_bar": round(self.oil_pressure_bar, 2),
            "d_oil_dt": round(self.d_oil_dt, 3),
            "engine_temp_c": round(self.engine_temp_c, 1),
            "d_temp_dt": round(self.d_temp_dt, 3),
            "tire_fr_temp": round(self.tire_fr_temp, 1),
            "max_wear_pct": round(max(self.tire_fl_wear, self.tire_fr_wear), 1),
            "state": self.system_state
        }
        self.history.append(record)
        if len(self.history) > 1200:
            self.history.pop(0)

    def evaluate_early_warning_rules(self):
        """
        Deterministic Rule Engine with Rate-of-Change early detection:
        - Critical: Absolute boundary limits breached (T > 115°C or P < 1.0 bar)
        - Early Warning: Thermal spike (dT/dt > 2.0°C/s) AND Oil drop (dP/dt < -0.30 bar/s)
        - Nominal: All states within operating envelope
        """
        prev_state = self.system_state
        
        # Absolute Critical Limits
        if self.engine_temp_c > 115.0 or self.oil_pressure_bar < 1.0 or self.brake_temp_c > 1050.0:
            self.system_state = "CRITICAL"
            if prev_state != "CRITICAL":
                self.log_event("🚨 CRITICAL FAILURE BREACH: Absolute threshold reached (Engine Temp > 115°C or Oil < 1.0 bar). BOX IMMEDIATELY.")
        # Proactive Rate-of-Change (d/dt) Early Warning
        elif (self.d_temp_dt > 1.8 and self.d_oil_dt < -0.25) or (self.oil_pressure_bar < 2.8) or (self.engine_temp_c > 111.0):
            self.system_state = "EARLY_WARNING"
            if prev_state != "EARLY_WARNING" and prev_state != "CRITICAL":
                self.log_event(f"⚠️ EARLY FAILURE WARNING: Rate-of-Change anomaly detected (dT/dt = +{self.d_temp_dt:.2f}°C/s, dP/dt = {self.d_oil_dt:.2f} bar/s). Lubrication loss imminent.")
        else:
            self.system_state = "NOMINAL"
            if prev_state in ["EARLY_WARNING", "CRITICAL"] and not self.fault_oil_leak and not self.fault_engine_overheat:
                self.log_event("✅ NOMINAL RECOVERY: Telemetry parameters stabilized within safe operating window.")

    def get_pit_strategy_advisory(self) -> str:
        """Rule engine evaluating tyre degradation, fuel delta, and strategy recommendations."""
        max_wear = max(self.tire_fl_wear, self.tire_fr_wear, self.tire_rl_wear, self.tire_rr_wear)
        
        if max_wear > 70.0:
            return "🚨 BOX BOX: Tyre Wear Exceeds 70% Limit [Fit Hard Compound C3 - Plan B]"
        elif max_wear > 50.0:
            return "⚠️ PIT WINDOW OPEN (Laps 16-22): Prepare for Medium -> Hard undercut"
        elif self.fuel_mass_kg < 12.0:
            return "⚠️ LOW FUEL ALERT: Minimum mass threshold approaching"
        else:
            return "✅ STRATEGY PLAN A: Optimum pace delta maintained. Continue stint."


# Initialize engine singleton
telemetry_engine = DeterministicPhysicsTelemetryEngine()


# =============================================================================
# 4. PLOTLY VISUALIZERS (2D MONZA TRACK WITH HEADING CAR + G-G TRACTION CIRCLE)
# =============================================================================
def rotate_point(x, y, angle_rad, origin_x=0, origin_y=0):
    cos_a = math.cos(angle_rad)
    sin_a = math.sin(angle_rad)
    dx = x - origin_x
    dy = y - origin_y
    return origin_x + (dx * cos_a - dy * sin_a), origin_y + (dx * sin_a + dy * cos_a)

def create_rotated_polygon(poly_coords, angle_rad, cx, cy, scale=1.0):
    tx, ty = [], []
    for lx, ly in poly_coords:
        sx = lx * scale
        sy = ly * scale
        rx, ry = rotate_point(sx, sy, angle_rad)
        tx.append(cx + rx)
        ty.append(cy + ry)
    if tx and (tx[0] != tx[-1] or ty[0] != ty[-1]):
        tx.append(tx[0])
        ty.append(ty[0])
    return tx, ty


def build_monza_track_figure(step_idx: int, is_warning: bool) -> go.Figure:
    """Renders the 2D Monza vector track map with Charles Leclerc's #16 car steering along headings."""
    car_x = MONZA_X[step_idx]
    car_y = MONZA_Y[step_idx]
    heading_rad = MONZA_HEADINGS[step_idx]
    
    fig = go.Figure()

    # Track Base Asphalt Contour
    fig.add_trace(go.Scatter(
        x=MONZA_X, y=MONZA_Y,
        mode='lines',
        line=dict(color='#262626', width=12, shape='spline'),
        hoverinfo='none', showlegend=False
    ))

    # Centerline (Rosso Corsa #CE2B37 or Warning Yellow #FFD700)
    fig.add_trace(go.Scatter(
        x=MONZA_X, y=MONZA_Y,
        mode='lines',
        line=dict(color='#CE2B37' if not is_warning else '#FFD700', width=3, shape='spline'),
        hoverinfo='none', showlegend=False
    ))

    # Start / Finish Checkpoint
    fig.add_trace(go.Scatter(
        x=[MONZA_X[0]], y=[MONZA_Y[0]],
        mode='markers',
        marker=dict(color='#FFFFFF', size=8, symbol='square', line=dict(color='#000000', width=1)),
        hoverinfo='text', hovertext='START / FINISH - RETTIFILO', showlegend=False
    ))

    # Rotated Ferrari F1 #16 Top-Down Car Geometry
    car_scale = 1.05
    body_color = "#CE2B37" if not is_warning else "#FFD700"
    
    # Front & Rear Wings
    fw_local = [(6.5, -4.2), (7.5, -4.0), (7.5, 4.0), (6.5, 4.2)]
    fw_x, fw_y = create_rotated_polygon(fw_local, heading_rad, car_x, car_y, scale=car_scale)
    fig.add_trace(go.Scatter(x=fw_x, y=fw_y, mode='lines', fill='toself', fillcolor='#1A1A1A', line=dict(color=body_color, width=1.5), hoverinfo='none', showlegend=False))
    
    rw_local = [(-6.5, -4.5), (-5.2, -4.5), (-5.2, 4.5), (-6.5, 4.5)]
    rw_x, rw_y = create_rotated_polygon(rw_local, heading_rad, car_x, car_y, scale=car_scale)
    fig.add_trace(go.Scatter(x=rw_x, y=rw_y, mode='lines', fill='toself', fillcolor='#111111', line=dict(color='#CE2B37', width=1.5), hoverinfo='none', showlegend=False))

    # Pirelli Slick Tires
    tires_local = [
        [(3.2, -3.8), (5.2, -3.8), (5.2, -2.5), (3.2, -2.5)],
        [(3.2, 2.5), (5.2, 2.5), (5.2, 3.8), (3.2, 3.8)],
        [(-4.8, -4.0), (-2.8, -4.0), (-2.8, -2.6), (-4.8, -2.6)],
        [(-4.8, 2.6), (-2.8, 2.6), (-2.8, 4.0), (-4.8, 4.0)]
    ]
    for tire in tires_local:
        tx, ty = create_rotated_polygon(tire, heading_rad, car_x, car_y, scale=car_scale)
        fig.add_trace(go.Scatter(x=tx, y=ty, mode='lines', fill='toself', fillcolor='#0A0A0A', line=dict(color='#FFD700', width=1), hoverinfo='none', showlegend=False))

    # Main Chassis Body
    body_local = [
        (6.8, 0.0), (4.5, -1.2), (2.0, -2.2), (-2.5, -2.3), (-4.8, -1.4),
        (-5.5, -1.2), (-5.5, 1.2), (-4.8, 1.4), (-2.5, 2.3), (2.0, 2.2), (4.5, 1.2)
    ]
    bx, by = create_rotated_polygon(body_local, heading_rad, car_x, car_y, scale=car_scale)
    fig.add_trace(go.Scatter(x=bx, y=by, mode='lines', fill='toself', fillcolor=body_color, line=dict(color='#FFFFFF', width=1.5), hoverinfo='none', showlegend=False))

    # Cockpit Halo
    cockpit_local = [(1.5, -0.7), (-1.2, -0.7), (-1.2, 0.7), (1.5, 0.7)]
    cx, cy = create_rotated_polygon(cockpit_local, heading_rad, car_x, car_y, scale=car_scale)
    fig.add_trace(go.Scatter(x=cx, y=cy, mode='lines', fill='toself', fillcolor='#0F0F0F', line=dict(color='#FFD700', width=1.5), hoverinfo='none', showlegend=False))

    # Tag
    fig.add_trace(go.Scatter(
        x=[car_x], y=[car_y], mode='text',
        text=["#16"], textposition="top center",
        textfont=dict(color="#FFD700", size=11, family="monospace"),
        hoverinfo='text', hovertext=f"C. Leclerc #16 | Heading: {math.degrees(heading_rad):.0f}°",
        showlegend=False
    ))

    fig.update_layout(
        margin=dict(l=10, r=10, t=32, b=10),
        paper_bgcolor='#0F0F0F',
        plot_bgcolor='#0F0F0F',
        xaxis=dict(visible=False, showgrid=False, zeroline=False),
        yaxis=dict(visible=False, showgrid=False, zeroline=False, scaleanchor="x", scaleratio=1),
        height=240,
        title=dict(text="<b>2D VECTOR TRACK MAP — AUTODROMO NAZIONALE MONZA</b>", font=dict(color="#FFD700", size=11), x=0.01, y=0.98)
    )
    return fig


def build_g_force_diagram(g_lat: float, g_lon: float) -> go.Figure:
    """Renders the G-Force Traction Friction Circle (G-G Diagram)."""
    fig = go.Figure()

    # Concentric Limit Friction Circles (1.5g, 3.0g, 4.5g, 5.0g peak)
    theta = np.linspace(0, 2*np.pi, 100)
    for r, col, dash in [(1.5, '#333333', 'dot'), (3.0, '#444444', 'dash'), (4.5, '#666666', 'solid')]:
        fig.add_trace(go.Scatter(
            x=r * np.cos(theta), y=r * np.sin(theta),
            mode='lines', line=dict(color=col, width=1, dash=dash),
            hoverinfo='none', showlegend=False
        ))

    # Axis Crosshairs
    fig.add_trace(go.Scatter(x=[-5.5, 5.5], y=[0, 0], mode='lines', line=dict(color='#2A2A2A', width=1), hoverinfo='none', showlegend=False))
    fig.add_trace(go.Scatter(x=[0, 0], y=[-5.5, 5.5], mode='lines', line=dict(color='#2A2A2A', width=1), hoverinfo='none', showlegend=False))

    # Live Vehicle Traction Operating Point
    fig.add_trace(go.Scatter(
        x=[g_lat], y=[g_lon],
        mode='markers',
        marker=dict(
            color='#FFD700',
            size=16,
            line=dict(color='#CE2B37', width=3)
        ),
        hoverinfo='text',
        hovertext=f"Lat: {g_lat:+.2f}g | Lon: {g_lon:+.2f}g",
        showlegend=False
    ))

    fig.update_layout(
        margin=dict(l=10, r=10, t=32, b=10),
        paper_bgcolor='#0F0F0F',
        plot_bgcolor='#0F0F0F',
        xaxis=dict(range=[-5.5, 5.5], title=dict(text="Lateral G (Cornering)", font=dict(color="#888888", size=10)), gridcolor='#181818', zerolinecolor='#333333'),
        yaxis=dict(range=[-5.5, 5.5], title=dict(text="Longitudinal G (Brake/Accel)", font=dict(color="#888888", size=10)), gridcolor='#181818', zerolinecolor='#333333', scaleanchor="x", scaleratio=1),
        height=240,
        title=dict(text=f"<b>G-FORCE TRACTION CIRCLE ({g_lat:+.1f}g, {g_lon:+.1f}g)</b>", font=dict(color="#FFD700", size=11), x=0.01, y=0.98)
    )
    return fig


# =============================================================================
# 5. STEP ADVANCE & TELEMETRY DISPATCH (ZeroGPU @spaces.GPU COMPLIANT)
# =============================================================================
@spaces.GPU
def advance_telemetry_tick(current_step: int, tyre_choice: str):
    """
    Periodic tick function (~10 Hz / 100ms interval).
    Executes pure deterministic physics, d/dt rate-of-change failure evaluations,
    updates Plotly Monza vector track and GG traction circle diagrams.
    """
    next_step = (current_step + 1) % TOTAL_TRACK_POINTS
    
    telemetry_engine.compound_key = tyre_choice
    telemetry_engine.update_physics_step(next_step, dt=0.1)
    
    state = telemetry_engine.system_state
    
    # 1. Status Banner HTML with Rate-of-Change Telemetry
    if state == "CRITICAL":
        banner_class = "status-critical"
        status_label = "🚨 CRITICAL MECHANICAL FAILURE: IMMEDIATE RETIREMENT MANDATE"
    elif state == "EARLY_WARNING":
        banner_class = "status-warning"
        status_label = f"⚠️ EARLY FAILURE WARNING: dT/dt = +{telemetry_engine.d_temp_dt:.2f}°C/s | dP/dt = {telemetry_engine.d_oil_dt:.2f} bar/s"
    else:
        banner_class = "status-nominal"
        status_label = "✅ ALL SYSTEMS NOMINAL: THERMAL ENVELOPE & LUBRICATION HEALTHY"

    pit_advisory = telemetry_engine.get_pit_strategy_advisory()

    status_html = f"""
    <div class="metric-box {banner_class}">
        <div style="font-size: 17px; font-weight: 800; letter-spacing: 0.5px;">{status_label}</div>
        <div style="margin-top: 4px; font-size: 13px; font-weight: 600; color: #FFFFFF;">STRATEGY: {pit_advisory}</div>
        <div style="margin-top: 2px; font-size: 12px; opacity: 0.85;">
            Fuel Remaining: <b>{telemetry_engine.fuel_mass_kg:.1f} kg</b> | 
            Lap: <b>{telemetry_engine.lap_count}</b> | 
            dT/dt: <b>{telemetry_engine.d_temp_dt:+.2f} °C/s</b> | 
            dP/dt: <b>{telemetry_engine.d_oil_dt:+.2f} bar/s</b>
        </div>
    </div>
    """

    # 2. Telemetry Gauges
    speed_text = f"{telemetry_engine.speed_kmh:.0f} km/h"
    gear_text = str(telemetry_engine.gear)
    rpm_text = f"{telemetry_engine.rpm} RPM"
    drs_text = "DRS OPEN (+12 km/h)" if telemetry_engine.drs_active else "DRS CLOSED"
    ers_text = f"SoC {telemetry_engine.ers_soc:.0f}% [{telemetry_engine.engine_mode}]"

    # 3. 4-Wheel Thermal Matrix
    tires_html = f"""
    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px; font-family: monospace;">
        <div style="background:#141414; padding:8px; border-radius:6px; border: 1px solid #2A2A2A;">
            <b style="color:#888;">FL TIRE</b><br/>
            Temp: <b style="color:{'#CE2B37' if telemetry_engine.tire_fl_temp>115 else '#FFFFFF'};">{telemetry_engine.tire_fl_temp:.1f}°C</b> | 
            Wear: <b style="color:{'#CE2B37' if telemetry_engine.tire_fl_wear>70 else '#00FF66'};">{telemetry_engine.tire_fl_wear:.1f}%</b>
        </div>
        <div style="background:#141414; padding:8px; border-radius:6px; border: 1px solid #2A2A2A;">
            <b style="color:#888;">FR TIRE (High Load)</b><br/>
            Temp: <b style="color:{'#CE2B37' if telemetry_engine.tire_fr_temp>115 else '#FFFFFF'};">{telemetry_engine.tire_fr_temp:.1f}°C</b> | 
            Wear: <b style="color:{'#CE2B37' if telemetry_engine.tire_fr_wear>70 else '#00FF66'};">{telemetry_engine.tire_fr_wear:.1f}%</b>
        </div>
        <div style="background:#141414; padding:8px; border-radius:6px; border: 1px solid #2A2A2A;">
            <b style="color:#888;">RL TIRE</b><br/>
            Temp: <b style="color:{'#CE2B37' if telemetry_engine.tire_rl_temp>115 else '#FFFFFF'};">{telemetry_engine.tire_rl_temp:.1f}°C</b> | 
            Wear: <b style="color:{'#CE2B37' if telemetry_engine.tire_rl_wear>70 else '#00FF66'};">{telemetry_engine.tire_rl_wear:.1f}%</b>
        </div>
        <div style="background:#141414; padding:8px; border-radius:6px; border: 1px solid #2A2A2A;">
            <b style="color:#888;">RR TIRE</b><br/>
            Temp: <b style="color:{'#CE2B37' if telemetry_engine.tire_rr_temp>115 else '#FFFFFF'};">{telemetry_engine.tire_rr_temp:.1f}°C</b> | 
            Wear: <b style="color:{'#CE2B37' if telemetry_engine.tire_rr_wear>70 else '#00FF66'};">{telemetry_engine.tire_rr_wear:.1f}%</b>
        </div>
    </div>
    """

    # 4. Powertrain & Hydraulics
    oil_col = '#CE2B37' if telemetry_engine.oil_pressure_bar < 1.5 else ('#FFD700' if telemetry_engine.oil_pressure_bar < 3.2 else '#00FF66')
    temp_col = '#CE2B37' if telemetry_engine.engine_temp_c > 115 else ('#FFD700' if telemetry_engine.engine_temp_c > 110 else '#FFFFFF')

    powertrain_html = f"""
    <div style="font-family: monospace; line-height: 1.8; background:#141414; padding:10px; border-radius:6px; border:1px solid #2A2A2A;">
        <div>OIL PRESSURE: <b style="color:{oil_col};">{telemetry_engine.oil_pressure_bar:.2f} bar ({telemetry_engine.oil_pressure_bar*14.5038:.1f} PSI)</b></div>
        <div>ENGINE TEMP: <b style="color:{temp_col};">{telemetry_engine.engine_temp_c:.1f} °C</b></div>
        <div>BRAKE TEMP: <b style="color:{'#CE2B37' if telemetry_engine.brake_temp_c>900 else '#FFFFFF'};">{telemetry_engine.brake_temp_c:.0f} °C</b></div>
        <div>HYDRAULICS: <b>{telemetry_engine.hyd_pressure_bar:.0f} bar</b></div>
        <div>ENGINE MODE: <b style="color:#FFD700;">{telemetry_engine.engine_mode}</b></div>
    </div>
    """

    # 5. Visualizer Figures
    track_fig = build_monza_track_figure(next_step, is_warning=(state != "NOMINAL"))
    g_force_fig = build_g_force_diagram(telemetry_engine.g_lat, telemetry_engine.g_lon)
    
    # 6. Action Log String
    log_text = "\n".join(telemetry_engine.action_logs[:12])

    return (
        next_step,
        status_html,
        speed_text,
        gear_text,
        rpm_text,
        drs_text,
        ers_text,
        tires_html,
        powertrain_html,
        track_fig,
        g_force_fig,
        log_text
    )


# =============================================================================
# 6. INTERACTIVE FAULT INJECTIONS & HANDLERS
# =============================================================================
def trigger_oil_leak():
    telemetry_engine.fault_oil_leak = True
    telemetry_engine.log_event("⚠️ FAULT INJECTED: Sudden Oil Pressure Line Breach (Loss rate: -0.65 bar/s)")
    return "\n".join(telemetry_engine.action_logs[:12])

def trigger_engine_overheat():
    telemetry_engine.fault_engine_overheat = True
    telemetry_engine.log_event("⚠️ FAULT INJECTED: Radiator Air Duct Blockage & Powertrain Thermal Spike (+4.8°C/s)")
    return "\n".join(telemetry_engine.action_logs[:12])

def reset_all_faults():
    telemetry_engine.fault_oil_leak = False
    telemetry_engine.fault_engine_overheat = False
    telemetry_engine.oil_pressure_bar = 4.85
    telemetry_engine.engine_temp_c = 104.5
    telemetry_engine.brake_temp_c = 620.0
    telemetry_engine.tire_fl_temp = 96.0
    telemetry_engine.tire_fr_temp = 98.0
    telemetry_engine.system_state = "NOMINAL"
    telemetry_engine.log_event("✅ FAULT SYSTEM RESET: Powertrain parameters recalibrated to nominal baseline.")
    return "\n".join(telemetry_engine.action_logs[:12])

def set_engine_mode(mode: str):
    telemetry_engine.engine_mode = mode
    telemetry_engine.log_event(f"🔄 ENGINE MAP SWITCH: Active mode changed to {mode}")
    return "\n".join(telemetry_engine.action_logs[:12])

def on_tyre_compound_change(compound: str):
    telemetry_engine.compound_key = compound
    telemetry_engine.log_event(f"🛞 TYRE COMPOUND SWITCH: Selected {compound}")
    return "\n".join(telemetry_engine.action_logs[:12])

def export_blackbox():
    if not telemetry_engine.history:
        return None
    df = pd.DataFrame(telemetry_engine.history)
    csv_file = "apexguard_f1_blackbox_telemetry.csv"
    df.to_csv(csv_file, index=False)
    return csv_file


# =============================================================================
# 7. GOOGLE GEMINI API AI RACE STRATEGY & DIAGNOSTICS ENGINE
# =============================================================================
def get_current_telemetry_snapshot() -> dict:
    """Extracts instantaneous telemetry parameters for AI analysis."""
    return {
        "driver": telemetry_engine.driver_name,
        "circuit": "Autodromo Nazionale Monza (5.793 km)",
        "lap": telemetry_engine.lap_count,
        "fuel_mass_kg": telemetry_engine.fuel_mass_kg,
        "speed_kmh": telemetry_engine.speed_kmh,
        "gear": telemetry_engine.gear,
        "rpm": telemetry_engine.rpm,
        "drs": "ACTIVE" if telemetry_engine.drs_active else "OFF",
        "engine_mode": telemetry_engine.engine_mode,
        "ers_soc": telemetry_engine.ers_soc,
        "engine_temp_c": telemetry_engine.engine_temp_c,
        "d_temp_dt": telemetry_engine.d_temp_dt,
        "oil_press_bar": telemetry_engine.oil_pressure_bar,
        "d_oil_dt": telemetry_engine.d_oil_dt,
        "brake_temp_c": telemetry_engine.brake_temp_c,
        "fl_temp": telemetry_engine.tire_fl_temp,
        "fr_temp": telemetry_engine.tire_fr_temp,
        "rl_temp": telemetry_engine.tire_rl_temp,
        "rr_temp": telemetry_engine.tire_rr_temp,
        "fl_wear": telemetry_engine.tire_fl_wear,
        "fr_wear": telemetry_engine.tire_fr_wear,
        "rl_wear": telemetry_engine.tire_rl_wear,
        "rr_wear": telemetry_engine.tire_rr_wear,
        "tyre_compound": telemetry_engine.compound_key,
        "system_state": telemetry_engine.system_state,
        "strategy_rec": telemetry_engine.get_pit_strategy_advisory()
    }


def ask_gemini_pit_wall(driver_query: str = "") -> str:
    """
    Invokes Google Gemini API to analyze current telemetry and deliver real-time
    Scuderia Ferrari race engineering directives.
    """
    snapshot = get_current_telemetry_snapshot()
    api_key = os.getenv("GEMINI_API_KEY")
    
    if not api_key:
        return f"""### ⚠️ **Google Gemini API Key Not Configured**

To enable live AI Race Strategy & Deep Mechanical Diagnostics, configure your `GEMINI_API_KEY` in your environment variables or Space settings.

---

### 🏎️ **Deterministic Rule-Engine Fallback (Active Telemetry Snapshot)**
- **System Operating State**: `{snapshot['system_state']}`
- **Active Pit Wall Advisory**: {snapshot['strategy_rec']}
- **Powertrain Envelope**: Engine Temp `{snapshot['engine_temp_c']:.1f}°C` (Rate: `{snapshot['d_temp_dt']:+.2f}°C/s`) | Oil Pressure `{snapshot['oil_press_bar']:.2f} bar` (Rate: `{snapshot['d_oil_dt']:+.2f} bar/s`)
- **Tyre Health**: Max Wear `{max(snapshot['fl_wear'], snapshot['fr_wear']):.1f}%` on `{snapshot['tyre_compound']}`
- **Fuel Remaining**: `{snapshot['fuel_mass_kg']:.1f} kg` | Lap `{snapshot['lap']}`
"""

    if not GENAI_AVAILABLE:
        return "### ⚠️ `google-genai` SDK is not installed. Run `pip install google-genai` to activate AI analysis."

    try:
        client = genai.Client(api_key=api_key)
        system_instruction = (
            "You are the Senior Race Strategist & Chief Powertrain Diagnostics Engineer for Scuderia Ferrari F1 Team "
            "(Callsign: ApexGuard Pit Wall AI). You communicate over the encrypted pit-to-car radio channel with "
            "precise technical authority, sharp Italian racing flair, and decisive strategic directives. "
            "Analyze live telemetry: vehicle speed, rates of change in oil pressure (dP/dt) and engine temperature (dT/dt), "
            "brake thermal loads, 4-wheel tyre surface/wear matrices, fuel depletion delta, and DRS/ERS energy modes. "
            "Provide explicit calls on: (1) Immediate driver tactical directives, (2) Mechanical & thermal failure prognosis, "
            "(3) Tyre degradation and graining/blistering risks, (4) Tactical pit stop window & compound selection."
        )

        prompt = f"""
[LIVE F1 TELEMETRY PACKET - SCUDERIA FERRARI]
- Driver: {snapshot['driver']}
- Circuit: {snapshot['circuit']} | Current Lap: {snapshot['lap']}
- Fuel Mass: {snapshot['fuel_mass_kg']:.1f} kg (Burn rate ~2.4 kg/lap)
- Speed: {snapshot['speed_kmh']:.0f} km/h | Gear: {snapshot['gear']} | RPM: {snapshot['rpm']} | DRS: {snapshot['drs']}
- Engine Mode: {snapshot['engine_mode']} | ERS State of Charge: {snapshot['ers_soc']:.0f}%
- Engine Temperature: {snapshot['engine_temp_c']:.1f}°C (Rate of Change dT/dt: {snapshot['d_temp_dt']:+.2f}°C/s)
- Oil Pressure: {snapshot['oil_press_bar']:.2f} bar / {snapshot['oil_press_bar']*14.5038:.1f} PSI (Rate of Change dP/dt: {snapshot['d_oil_dt']:+.2f} bar/s)
- Brake Disc Temperature: {snapshot['brake_temp_c']:.0f}°C
- 4-Wheel Temperatures (°C): FL={snapshot['fl_temp']:.1f}, FR={snapshot['fr_temp']:.1f}, RL={snapshot['rl_temp']:.1f}, RR={snapshot['rr_temp']:.1f}
- 4-Wheel Degradation (%): FL={snapshot['fl_wear']:.1f}%, FR={snapshot['fr_wear']:.1f}%, RL={snapshot['rl_wear']:.1f}%, RR={snapshot['rr_wear']:.1f}%
- Active Tyre Set: {snapshot['tyre_compound']}
- Mechanical System FSM State: {snapshot['system_state']}
- Rule-Engine Primary Directive: {snapshot['strategy_rec']}

User / Driver Query:
{driver_query.strip() if driver_query and driver_query.strip() else "Provide full telemetry debrief, mechanical failure risk check, and tactical pit strategy."}

Respond in the following structured format with Markdown headers and bullet points:
### 🏎️ **PIT WALL DIRECTIVE & RADIO CALL**
(One clear, concise direct radio command to the driver)

### 🔍 **POWERTRAIN & MECHANICAL DIAGNOSTICS**
(Analysis of oil pressure line, thermal stability, derivative rates dT/dt and dP/dt)

### 🛞 **TYRE DEGRADATION & PACE OUTLOOK**
(Wear analysis across all 4 corners, thermal window compliance, stint longevity)

### ⏱️ **TACTICAL PIT STRATEGY & WINDOW**
(Target pit lap, recommended tyre compound switch Plan A/Plan B, undercut/overcut advice)
"""
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=0.4,
                max_output_tokens=700
            )
        )
        return response.text if response.text else "Telemetry analysis complete."
    except Exception as e:
        return f"### ⚠️ **Gemini AI Service Exception:**\n`{str(e)}`\n\n*Deterministic fallback remains fully active.*"


# =============================================================================
# 8. GRADIO 6.0 DASHBOARD INTERFACE CONSTRUCTION
# =============================================================================
with gr.Blocks() as demo:
    # Italian Flag Tricolore Header Bar (#009246, #FFFFFF, #CE2B37)
    gr.HTML('<div class="tricolore-bar"></div>')
    
    # Ferrari Scuderia Header with Yellow Accent (#FFD700)
    with gr.Row(elem_classes=["ferrari-header"]):
        with gr.Column(scale=3):
            gr.Markdown(
                "## 🏎️ **APEXGUARD** | Scuderia Ferrari F1 Real-Time Telemetry & Failure Warning System"
            )
        with gr.Column(scale=1):
            gr.Markdown("### **Google Gemini AI & Deterministic Physics Engine**")

    # Driver & Tyre Compound Selectors
    with gr.Row():
        driver_dropdown = gr.Dropdown(
            choices=[
                "C. LECLERC [16] - SCUDERIA FERRARI",
                "L. HAMILTON [44] - SCUDERIA FERRARI",
                "M. VERSTAPPEN [1] - RED BULL RACING",
                "L. NORRIS [4] - MCLAREN F1"
            ],
            value="C. LECLERC [16] - SCUDERIA FERRARI",
            label="SELECT DRIVER"
        )
        tyre_dropdown = gr.Dropdown(
            choices=[
                "SOFT (C5 - High Grip, Fast Wear)",
                "MEDIUM (C4 - Balanced)",
                "HARD (C3 - Low Grip, High Durability)"
            ],
            value="MEDIUM (C4 - Balanced)",
            label="TYRE COMPOUND"
        )
        circuit_info = gr.Textbox(label="CIRCUIT", value="AUTODROMO NAZIONALE MONZA (5.793 km)", interactive=False)

    # Dynamic Early Warning & Strategy Banner
    status_banner = gr.HTML(value="<div class='metric-box status-nominal'>INITIALIZING DETERMINISTIC TELEMETRY STREAM...</div>")

    # Core Gauges, 2D Monza Vector Map & GG Traction Circle
    with gr.Row():
        with gr.Column(scale=1):
            speed_metric = gr.Textbox(label="SPEED", value="310 km/h", interactive=False)
            gear_metric = gr.Textbox(label="GEAR", value="7", interactive=False)
            rpm_metric = gr.Textbox(label="RPM", value="12600 RPM", interactive=False)
            drs_metric = gr.Textbox(label="DRS STATUS", value="DRS CLOSED", interactive=False)
            ers_metric = gr.Textbox(label="ERS BATTERY", value="SoC 86% [PUSH]", interactive=False)

        with gr.Column(scale=1):
            gr.Markdown("### 🛞 4-Wheel Thermal Matrix")
            tires_html_box = gr.HTML()
            gr.Markdown("### ⚡ Powertrain & Lubrication")
            powertrain_html_box = gr.HTML()

        with gr.Column(scale=1):
            track_plot = gr.Plot(label="Monza Circuit 2D Vector Map")

        with gr.Column(scale=1):
            g_force_plot = gr.Plot(label="G-Force Traction Circle")

    # Interactive Control Panels & Fault Injection
    gr.Markdown("### 🛠️ Interactive Powertrain Controls & Simulator Fault Injections")
    with gr.Row():
        btn_push = gr.Button("PUSH MODE (ERS)", variant="primary")
        btn_save = gr.Button("SAVE FUEL")
        btn_overtake = gr.Button("OVERTAKE (MAX ERS)")
        btn_oil_leak = gr.Button("⚠️ INJECT OIL LEAK", variant="stop")
        btn_overheat = gr.Button("⚠️ INJECT ENGINE OVERHEAT", variant="stop")
        btn_reset = gr.Button("✅ RESET ALL FAULTS")

    # -------------------------------------------------------------------------
    # 🧠 GOOGLE GEMINI AI PIT WALL RACE STRATEGIST & DIAGNOSTICS PANEL
    # -------------------------------------------------------------------------
    gr.Markdown("### 🧠 **Scuderia Ferrari AI Pit Wall Strategist (Powered by Google Gemini)**")
    with gr.Row():
        with gr.Column(scale=3):
            ai_query_input = gr.Textbox(
                label="Driver / Pit Wall Strategy Query",
                placeholder="e.g. 'Can we extend this stint for 6 more laps?' or 'Analyze current oil pressure drop and recommend engine mode.'",
                lines=2
            )
            with gr.Row():
                btn_ask_ai = gr.Button("🧠 RUN GEMINI TELEMETRY ANALYSIS", variant="primary")
                btn_preset_pit = gr.Button("🏎️ Strategy & Box Lap")
                btn_preset_engine = gr.Button("⚠️ Engine Health & Leak Check")
                btn_preset_tyre = gr.Button("🛞 Tyre Degradation & Blistering")
        with gr.Column(scale=4):
            ai_response_box = gr.Markdown(
                value="*Click **RUN GEMINI TELEMETRY ANALYSIS** or submit a tactical query to receive real-time Scuderia Ferrari engineering debriefs.*"
            )

    # Live Action Log & Blackbox CSV Export
    with gr.Row():
        with gr.Column(scale=3):
            action_log_box = gr.Textbox(label="Action & State Transition Log", lines=4, value="System operational. Baseline nominal.", interactive=False)
        with gr.Column(scale=1):
            btn_export = gr.Button("📥 EXPORT BLACKBOX TELEMETRY (.CSV)")
            file_download = gr.File(label="Download CSV")

    # Event Connections
    btn_push.click(fn=lambda: set_engine_mode("PUSH"), outputs=action_log_box)
    btn_save.click(fn=lambda: set_engine_mode("SAVE_FUEL"), outputs=action_log_box)
    btn_overtake.click(fn=lambda: set_engine_mode("OVERTAKE"), outputs=action_log_box)
    
    btn_oil_leak.click(trigger_oil_leak, outputs=action_log_box)
    btn_overheat.click(trigger_engine_overheat, outputs=action_log_box)
    btn_reset.click(reset_all_faults, outputs=action_log_box)
    
    tyre_dropdown.change(on_tyre_compound_change, inputs=[tyre_dropdown], outputs=action_log_box)
    btn_export.click(export_blackbox, outputs=file_download)

    # Gemini AI Event Handlers
    btn_ask_ai.click(fn=ask_gemini_pit_wall, inputs=[ai_query_input], outputs=[ai_response_box])
    btn_preset_pit.click(
        fn=lambda: ask_gemini_pit_wall("Evaluate current tyre degradation, fuel burn rate, and calculate our optimum pit stop window and compound switch."),
        outputs=[ai_response_box]
    )
    btn_preset_engine.click(
        fn=lambda: ask_gemini_pit_wall("Analyze powertrain oil pressure, engine thermals, rate of change derivatives (dT/dt and dP/dt), and check for mechanical failure risks."),
        outputs=[ai_response_box]
    )
    btn_preset_tyre.click(
        fn=lambda: ask_gemini_pit_wall("Deep 4-wheel tyre thermal and wear analysis. Identify asymmetric loads on FR/RR at Monza and warn of blistering or graining."),
        outputs=[ai_response_box]
    )

    # State & High-Frequency Step-Update Engine (~10 Hz / 100ms)
    car_step_state = gr.State(value=0)
    timer = gr.Timer(0.1)
    
    timer.tick(
        fn=advance_telemetry_tick,
        inputs=[car_step_state, tyre_dropdown],
        outputs=[
            car_step_state,
            status_banner,
            speed_metric,
            gear_metric,
            rpm_metric,
            drs_metric,
            ers_metric,
            tires_html_box,
            powertrain_html_box,
            track_plot,
            g_force_plot,
            action_log_box
        ]
    )

if __name__ == "__main__":
    demo.launch(css=CUSTOM_CSS)

