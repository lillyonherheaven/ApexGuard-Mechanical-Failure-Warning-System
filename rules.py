"""
F1 Telemetry System - Deterministic Rule Engine (rules.py)
Evaluates live telemetry metrics against physical mechanical thresholds.
Computes rate of change derivatives (dy/dt) for early anomaly prediction.
Includes:
- Weather & Tire Strategy recommendations (Intermediate/Wet tires)
- Lift & Coast driver directive logic
- Brake Bias Balance advice
- Engine Oil / Thermal failure rules
- Brake thermal fade checks
"""

import time
import os
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

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

SEVERITY_HIERARCHY = {
    "NORMAL": 0,
    "WARNING": 1,
    "CRITICAL_BOX": 2,
    "CRITICAL_SHUTDOWN": 3,
    "CRITICAL_DNF": 4
}

@dataclass
class AnomalyFault:
    category: str       # "ENGINE", "TIRE", "BRAKE", "HYDRAULIC", "STRATEGY", "DIRECTIVE"
    severity: str       # "WARNING", "CRITICAL_BOX", "CRITICAL_SHUTDOWN", "CRITICAL_DNF"
    code: str           # System fault code
    message: str        # Human-readable engineer/driver text
    metric_value: float # Numerical value
    rate_of_change: float # Numerical derivative (units/sec)

@dataclass
class RuleReport:
    faults: List[AnomalyFault] = field(default_factory=list)
    highest_severity: str = "NORMAL"
    strategy_recommendation: str = "STAY OUT - NOMINAL STRATEGY"
    driver_directive: str = "PUSH - ALL SYSTEMS OPTIMAL"
    timestamp: float = field(default_factory=time.time)

class RateTracker:
    """Calculates numerical rate of change (dy/dt) between telemetry frames."""
    def __init__(self):
        self._history: Dict[str, tuple[float, float]] = {}

    def compute_rates(self, packet: Dict[str, Any]) -> Dict[str, float]:
        rates = {}
        now = packet.get("timestamp", packet.get("Timestamp", time.time()))

        numeric_keys = [
            "Engine_Oil_Pressure", "Engine_Temp",
            "FL_Tire_Pressure", "FR_Tire_Pressure", "RL_Tire_Pressure", "RR_Tire_Pressure",
            "FL_Brake_Temp", "FR_Brake_Temp", "RL_Brake_Temp", "RR_Brake_Temp",
            "Brake_Temp_FL", "Brake_Temp_FR", "Brake_Temp_RL", "Brake_Temp_RR",
            "Tire_Temp_FL", "Tire_Temp_FR", "Tire_Temp_RL", "Tire_Temp_RR"
        ]

        for key in numeric_keys:
            if key in packet and packet[key] is not None:
                val = float(packet[key])
                if key in self._history:
                    prev_val, prev_time = self._history[key]
                    dt = now - prev_time
                    if dt > 0.001:
                        rates[key] = (val - prev_val) / dt
                    else:
                        rates[key] = 0.0
                else:
                    rates[key] = 0.0
                self._history[key] = (val, now)
        return rates

class RuleEngine:
    """Core deterministic physics rule evaluator for Formula 1 mechanics."""
    def __init__(self):
        self.rate_tracker = RateTracker()

    def evaluate(self, packet: Dict[str, Any]) -> RuleReport:
        faults: List[AnomalyFault] = []
        rates = self.rate_tracker.compute_rates(packet)
        strategy_rec = "STAY OUT - NOMINAL STRATEGY"
        driver_dir = "PUSH - ALL SYSTEMS OPTIMAL"

        # Check Terminal Crash State
        if packet.get("is_crashed", False):
            reason = packet.get("crash_reason", "CRASH DETECTED")
            faults.append(AnomalyFault(
                category="CRASH",
                severity="CRITICAL_DNF",
                code="CAR_RETIRED_DNF",
                message=f"CAR RETIRED (DNF): {reason}",
                metric_value=0.0,
                rate_of_change=0.0
            ))
            return RuleReport(
                faults=faults,
                highest_severity="CRITICAL_DNF",
                strategy_recommendation="CAR RETIRED - DNF",
                driver_directive="SYSTEMS FROZEN - AWAITING PIT RECOVERY",
                timestamp=packet.get("timestamp", time.time())
            )

        # ---------------------------------------------------------------------
        # 1. WEATHER & TIRE STRATEGY ENGINE
        # ---------------------------------------------------------------------
        rain_pct = float(packet.get("Track_Rain_%", 0.0))
        active_compound = str(packet.get("Tire_Compound", "SOFT")).upper()
        
        if rain_pct > 65.0:
            strategy_rec = f"HEAVY RAIN ({rain_pct:.0f}%) - RECOMMEND PIT FOR FULL WET TIRES"
            if active_compound in ["SOFT", "MEDIUM", "HARD", "INTERMEDIATE"]:
                faults.append(AnomalyFault(
                    category="STRATEGY",
                    severity="CRITICAL_BOX",
                    code="WEATHER_HEAVY_RAIN_BOX",
                    message=f"STRATEGY: Heavy Rain ({rain_pct:.0f}%) - Pit for Full Wets",
                    metric_value=rain_pct,
                    rate_of_change=0.0
                ))
        elif rain_pct > 30.0:
            strategy_rec = f"TRACK WETNESS HIGH ({rain_pct:.0f}%) - RECOMMEND PIT FOR INTERMEDIATE TIRES"
            if active_compound in ["SOFT", "MEDIUM", "HARD"]:
                faults.append(AnomalyFault(
                    category="STRATEGY",
                    severity="WARNING",
                    code="WEATHER_WET_INTERMEDIATE_BOX",
                    message=f"STRATEGY: Track Wetness High ({rain_pct:.0f}%) - Pit for Intermediates",
                    metric_value=rain_pct,
                    rate_of_change=0.0
                ))

        # ---------------------------------------------------------------------
        # 2. TIRE SYSTEM & BLISTERING EVALUATION
        # ---------------------------------------------------------------------
        corners = ["FL", "FR", "RL", "RR"]
        thermal_warning_triggered = False

        for corner in corners:
            temp_key = f"{corner}_Tire_Temp" if f"{corner}_Tire_Temp" in packet else f"Tire_Temp_{corner}"
            wear_key = f"{corner}_Tire_Wear" if f"{corner}_Tire_Wear" in packet else f"Tire_Wear_{corner}"
            pres_key = f"{corner}_Tire_Pressure"

            if wear_key in packet:
                wear = float(packet[wear_key])
                if wear > 88.0:
                    faults.append(AnomalyFault(
                        category="TIRE",
                        severity="CRITICAL_BOX",
                        code=f"{corner}_TIRE_WEAR_CRITICAL",
                        message=f"BOX THIS LAP: {corner} Wear Critical ({wear:.1f}%)",
                        metric_value=wear,
                        rate_of_change=0.0
                    ))
                elif wear > 75.0:
                    faults.append(AnomalyFault(
                        category="TIRE",
                        severity="WARNING",
                        code=f"{corner}_TIRE_WEAR_HIGH",
                        message=f"WARNING: {corner} Wear High ({wear:.1f}%)",
                        metric_value=wear,
                        rate_of_change=0.0
                    ))

            if temp_key in packet:
                temp = float(packet[temp_key])
                temp_rate = rates.get(temp_key, 0.0)
                wear = float(packet.get(wear_key, 0.0))

                if temp_rate > 2.0 and wear > 60.0:
                    faults.append(AnomalyFault(
                        category="TIRE",
                        severity="CRITICAL_BOX",
                        code=f"{corner}_TIRE_BLISTERING_RISK",
                        message=f"PIT STOP REQUIRED - {corner} BLISTERING RISK (+{temp_rate:.1f}°C/s)",
                        metric_value=temp,
                        rate_of_change=temp_rate
                    ))
                elif temp > 115.0:
                    thermal_warning_triggered = True
                    faults.append(AnomalyFault(
                        category="TIRE",
                        severity="WARNING",
                        code=f"{corner}_TIRE_OVERHEAT",
                        message=f"TIRE DEGRADATION HIGH - {corner} Overheating ({temp:.1f}°C)",
                        metric_value=temp,
                        rate_of_change=temp_rate
                    ))

        # ---------------------------------------------------------------------
        # 3. ENGINE MECHANICAL EVALUATION
        # ---------------------------------------------------------------------
        oil_pressure = float(packet.get("Engine_Oil_Pressure", 72.0))
        engine_temp = float(packet.get("Engine_Temp", 108.0))
        oil_drop_rate = -rates.get("Engine_Oil_Pressure", 0.0)
        temp_rise_rate = rates.get("Engine_Temp", 0.0)

        if oil_drop_rate > 0.3 and engine_temp > 115.0:
            faults.append(AnomalyFault(
                category="ENGINE",
                severity="CRITICAL_SHUTDOWN",
                code="ENGINE_CRITICAL_OIL_LOSS",
                message=f"CRITICAL ENGINE FAILURE - SHUTDOWN NOW (Oil Drop {oil_drop_rate:.2f} PSI/s)",
                metric_value=oil_pressure,
                rate_of_change=-oil_drop_rate
            ))

        if oil_pressure < 35.0:
            faults.append(AnomalyFault(
                category="ENGINE",
                severity="CRITICAL_SHUTDOWN",
                code="ENGINE_LOW_OIL_PRESSURE",
                message=f"CRITICAL OIL PRESSURE BELOW SAFE LIMIT ({oil_pressure:.1f} PSI)",
                metric_value=oil_pressure,
                rate_of_change=-oil_drop_rate
            ))

        if engine_temp > 122.0 or temp_rise_rate > 0.5:
            thermal_warning_triggered = True
            sev = "CRITICAL_SHUTDOWN" if engine_temp > 138.0 else "WARNING"
            faults.append(AnomalyFault(
                category="ENGINE",
                severity=sev,
                code="ENGINE_THERMAL_DRIFT",
                message=f"ENGINE OVERHEAT ALERT ({engine_temp:.1f}°C, Rise +{temp_rise_rate:.2f}°C/s)",
                metric_value=engine_temp,
                rate_of_change=temp_rise_rate
            ))

        # LIFT & COAST DIRECTIVE LOGIC
        if thermal_warning_triggered:
            driver_dir = "THERMAL WARNING: APPLY LIFT & COAST 150M BEFORE BRAKING ZONES"

        # ---------------------------------------------------------------------
        # 4. BRAKE BIAS & THERMAL BALANCE EVALUATION
        # ---------------------------------------------------------------------
        fl_brake = float(packet.get("Brake_Temp_FL", packet.get("FL_Brake_Temp", 580.0)))
        fr_brake = float(packet.get("Brake_Temp_FR", packet.get("FR_Brake_Temp", 610.0)))
        rl_brake = float(packet.get("Brake_Temp_RL", packet.get("RL_Brake_Temp", 540.0)))
        rr_brake = float(packet.get("Brake_Temp_RR", packet.get("RR_Brake_Temp", 550.0)))

        avg_front_brake = (fl_brake + fr_brake) / 2.0
        avg_rear_brake = (rl_brake + rr_brake) / 2.0

        if (avg_front_brake - avg_rear_brake) > 150.0:
            faults.append(AnomalyFault(
                category="BRAKE",
                severity="WARNING",
                code="BRAKE_BIAS_FRONT_RUNAWAY",
                message="FRONT BRAKE THERMAL RUNAWAY -> SHIFT BRAKE BIAS REAR (-1.5%)",
                metric_value=avg_front_brake - avg_rear_brake,
                rate_of_change=0.0
            ))

        for corner, btemp in [("FL", fl_brake), ("FR", fr_brake), ("RL", rl_brake), ("RR", rr_brake)]:
            if btemp > 1000.0:
                faults.append(AnomalyFault(
                    category="BRAKE",
                    severity="CRITICAL_BOX",
                    code=f"{corner}_BRAKE_FADE_RISK",
                    message=f"CRITICAL: {corner} Brake Fade Risk ({btemp:.0f}°C)",
                    metric_value=btemp,
                    rate_of_change=rates.get(f"{corner}_Brake_Temp", 0.0)
                ))

        # Calculate highest severity
        highest_sev = "NORMAL"
        for fault in faults:
            if SEVERITY_HIERARCHY.get(fault.severity, 0) > SEVERITY_HIERARCHY.get(highest_sev, 0):
                highest_sev = fault.severity

        return RuleReport(
            faults=faults,
            highest_severity=highest_sev,
            strategy_recommendation=strategy_rec,
            driver_directive=driver_dir,
            timestamp=packet.get("timestamp", time.time())
        )

class DeterministicRuleEngine(RuleEngine):
    pass


def generate_gemini_race_advice(
    telemetry_summary: Dict[str, Any],
    driver_query: Optional[str] = None,
    api_key: Optional[str] = None
) -> str:
    """
    Calls Google Gemini API using the official google-genai Python SDK
    to provide Scuderia Ferrari race engineer insights.
    Handles exceptions, rate limits, and missing API keys gracefully.
    """
    key = api_key or os.getenv("GEMINI_API_KEY")
    if not key:
        return (
            "⚠️ **Gemini API Key Not Detected**\n\n"
            "To enable real-time Gemini AI race strategy and deep diagnostic insights, set the `GEMINI_API_KEY` "
            "environment variable or provide a key in the setup panel.\n\n"
            "**Deterministic Rule-Engine Fallback Advisory:**\n"
            f"- Powertrain Status: **{telemetry_summary.get('system_state', 'NOMINAL')}**\n"
            f"- Active Directive: **{telemetry_summary.get('driver_dir', telemetry_summary.get('strategy_rec', 'Maintain standard stint delta.'))}**\n"
            f"- Recommended Action: {telemetry_summary.get('strategy_rec', 'STAY OUT - Optimum pace delta maintained.')}"
        )

    if not GENAI_AVAILABLE:
        return (
            "⚠️ **`google-genai` package not installed**\n\n"
            "Install the official SDK with `pip install google-genai` to activate AI race engineering."
        )

    try:
        client = genai.Client(api_key=key)
        
        system_instruction = (
            "You are the Chief Race Strategist and Senior Powertrain Diagnostics Engineer for Scuderia Ferrari F1 Team "
            "(callsign: ApexGuard Pit Wall AI). You speak to the race engineer and driver (Charles Leclerc #16 or Lewis Hamilton #44) "
            "with high technical accuracy, concise F1 racing radio terminology, and decisive strategy commands. "
            "Assess tyre thermal degradation, oil pressure and engine temperature rates of change (dT/dt and dP/dt), "
            "fuel delta, ERS energy management, and recommend optimal pit windows, engine modes (PUSH, SAVE_FUEL, OVERTAKE), "
            "and tactical driving directives (e.g. Lift and Coast, Brake Bias adjustments)."
        )

        user_prompt = f"""
Current Live F1 Telemetry Snapshot:
- Driver: {telemetry_summary.get('driver', 'C. LECLERC [16] - SCUDERIA FERRARI')}
- Circuit: {telemetry_summary.get('circuit', 'Autodromo Nazionale Monza')}
- Lap: {telemetry_summary.get('lap', 1)} | Fuel Mass: {telemetry_summary.get('fuel_mass_kg', 105.0):.1f} kg
- Speed: {telemetry_summary.get('speed_kmh', 300.0):.0f} km/h | Gear: {telemetry_summary.get('gear', 7)} | RPM: {telemetry_summary.get('rpm', 12000)} | DRS: {telemetry_summary.get('drs', 'OFF')}
- Engine Mode: {telemetry_summary.get('engine_mode', 'PUSH')} | ERS SoC: {telemetry_summary.get('ers_soc', 80.0):.0f}%
- Engine Temp: {telemetry_summary.get('engine_temp_c', 104.0):.1f} °C (Rate: {telemetry_summary.get('d_temp_dt', 0.0):+.2f} °C/s)
- Oil Pressure: {telemetry_summary.get('oil_press_bar', 4.8):.2f} bar (Rate: {telemetry_summary.get('d_oil_dt', 0.0):+.2f} bar/s)
- Brake Temp: {telemetry_summary.get('brake_temp_c', 600.0):.0f} °C
- 4-Wheel Tyre Temps (°C): FL={telemetry_summary.get('fl_temp', 95.0):.1f}, FR={telemetry_summary.get('fr_temp', 98.0):.1f}, RL={telemetry_summary.get('rl_temp', 92.0):.1f}, RR={telemetry_summary.get('rr_temp', 94.0):.1f}
- 4-Wheel Tyre Wear (%): FL={telemetry_summary.get('fl_wear', 20.0):.1f}%, FR={telemetry_summary.get('fr_wear', 22.0):.1f}%, RL={telemetry_summary.get('rl_wear', 18.0):.1f}%, RR={telemetry_summary.get('rr_wear', 19.0):.1f}%
- Active Tyre Compound: {telemetry_summary.get('tyre_compound', 'MEDIUM (C4 - Balanced)')}
- System Fault State: {telemetry_summary.get('system_state', 'NOMINAL')}
- Rule Engine Directive: {telemetry_summary.get('strategy_rec', 'NOMINAL')}

Driver / Pit Wall Query:
{driver_query if driver_query else "Provide a complete tactical telemetry debrief, powertrain health evaluation, and immediate strategic pit window recommendation."}

Format your response in a crisp, high-contrast Scuderia Ferrari debrief format:
1. 🏎️ **PIT WALL DIRECTIVE & RADIO CALL** (One clear direct instruction)
2. 🔍 **MECHANICAL & THERMAL DIAGNOSTICS** (Analysis of oil pressure, temperatures, and derivatives)
3. 🛞 **TYRE DEGRADATION & PACE OUTLOOK** (Tire life, surface vs core thermals, graining/blistering risks)
4. ⏱️ **STRATEGY & PIT WINDOW RECOMMENDATION** (Target lap to box, compound choice Plan A/B/C, undercut/overcut advice)
"""

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=user_prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=0.4,
                max_output_tokens=700
            )
        )
        return response.text if response.text else "Telemetry processed with no remarks."
    except Exception as e:
        return f"⚠️ **Gemini API Error Encountered:** {str(e)}\n\n*Rule-based fallback strategy active.*"

