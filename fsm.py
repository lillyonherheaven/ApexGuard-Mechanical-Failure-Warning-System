"""
F1 Telemetry System - Vehicle Finite State Machine (fsm.py)
Manages vehicle operational risk states based on Rule Engine evaluations.
Applies time-based hysteresis to prevent rapid UI/Audio state flickering.
Supports terminal CRITICAL_DNF crash state.
"""

import time
from enum import Enum
from dataclasses import dataclass
from typing import Optional
from rules import RuleReport

class VehicleState(Enum):
    NORMAL = 0
    WARNING = 1
    CRITICAL_BOX = 2
    CRITICAL_SHUTDOWN = 3
    CRITICAL_DNF = 4

# Scuderia Ferrari Visual Branding Palette
COLOR_CHARCOAL_DARK = "#0F0F0F"
COLOR_CHARCOAL_PANEL = "#1A1A1A"
COLOR_PURE_WHITE = "#FFFFFF"
COLOR_ROSSO_CORSA = "#E8002D"
COLOR_MODENA_YELLOW = "#FFEB00"
COLOR_NORMAL_GREEN = "#00FF66"
COLOR_CYAN_ERS = "#00E5FF"

@dataclass
class UIStateTheme:
    state_name: str
    bg_color: str
    accent_color: str
    status_text: str
    primary_fault_msg: str
    pit_instruction: str
    audio_cue: bool
    flash_rate_ms: int

class VehicleFSM:
    """
    Finite State Machine with Hysteresis for vehicle risk state tracking.
    Guarantees state escalation happens instantly upon critical fault detection,
    while de-escalation requires a stable period to avoid UI flickering.
    Includes terminal lock for CRITICAL_DNF.
    """
    def __init__(self, hysteresis_seconds: float = 0.5):
        self.current_state = VehicleState.NORMAL
        self.last_transition_time = time.time()
        self.hysteresis_seconds = hysteresis_seconds
        self.last_primary_fault = ""
        self.transition_history = []

    def update_state(self, rule_report: RuleReport) -> UIStateTheme:
        now = time.time()
        requested_severity = rule_report.highest_severity

        # Preserve the latest primary fault message if present
        fault_messages = [f.message for f in rule_report.faults]
        if fault_messages:
            self.last_primary_fault = fault_messages[0]

        severity_map = {
            "NORMAL": VehicleState.NORMAL,
            "WARNING": VehicleState.WARNING,
            "CRITICAL_BOX": VehicleState.CRITICAL_BOX,
            "CRITICAL_SHUTDOWN": VehicleState.CRITICAL_SHUTDOWN,
            "CRITICAL_DNF": VehicleState.CRITICAL_DNF
        }

        target_state = severity_map.get(requested_severity, VehicleState.NORMAL)

        # Terminal DNF Lock
        if self.current_state == VehicleState.CRITICAL_DNF:
            if target_state != VehicleState.NORMAL: # Only reset when explicitly reset
                return self.get_ui_theme(rule_report)
            else:
                self.current_state = VehicleState.NORMAL
                self.last_primary_fault = ""

        # 1. Immediate Escalation
        if target_state.value > self.current_state.value:
            self.current_state = target_state
            self.last_transition_time = now
            self._log_transition(target_state, rule_report)

        # 2. Hysteresis-guarded De-escalation
        elif target_state.value < self.current_state.value:
            if (now - self.last_transition_time) >= self.hysteresis_seconds:
                self.current_state = target_state
                self.last_transition_time = now
                if target_state == VehicleState.NORMAL:
                    self.last_primary_fault = ""
                self._log_transition(target_state, rule_report)

        return self.get_ui_theme(rule_report)

    def get_ui_theme(self, rule_report: Optional[RuleReport] = None) -> UIStateTheme:
        fault_msg = self.last_primary_fault

        if self.current_state == VehicleState.NORMAL:
            return UIStateTheme(
                state_name="NORMAL",
                bg_color="#0F0F0F",
                accent_color=COLOR_NORMAL_GREEN,
                status_text="SYSTEMS OPTIMAL",
                primary_fault_msg="ALL METRICS WITHIN NOMINAL LIMITS",
                pit_instruction="STAY OUT - PUSH MODE ACTIVE",
                audio_cue=False,
                flash_rate_ms=0
            )

        elif self.current_state == VehicleState.WARNING:
            return UIStateTheme(
                state_name="WARNING",
                bg_color="#262000",
                accent_color=COLOR_MODENA_YELLOW,
                status_text="MECHANICAL WARNING",
                primary_fault_msg=fault_msg if fault_msg else "METRIC DEVIATION DETECTED",
                pit_instruction="MONITOR METRICS - PREPARE ALTERNATE STRATEGY",
                audio_cue=False,
                flash_rate_ms=1000
            )

        elif self.current_state == VehicleState.CRITICAL_BOX:
            return UIStateTheme(
                state_name="CRITICAL_BOX",
                bg_color="#330A00",
                accent_color="#FF4500",
                status_text="CRITICAL PIT ALERT",
                primary_fault_msg=fault_msg if fault_msg else "IMMINENT MECHANICAL FAILURE DETECTED",
                pit_instruction="BOX BOX BOX THIS LAP - PREPARE PIT CREW",
                audio_cue=True,
                flash_rate_ms=500
            )

        elif self.current_state == VehicleState.CRITICAL_SHUTDOWN:
            return UIStateTheme(
                state_name="CRITICAL_SHUTDOWN",
                bg_color="#400000",
                accent_color=COLOR_ROSSO_CORSA,
                status_text="ENGINE SHUTDOWN REQUIRED",
                primary_fault_msg=fault_msg if fault_msg else "CATASTROPHIC COMPONENT FAILURE",
                pit_instruction="STOP CAR SAFELY OFF TRACK IMMEDIATELY",
                audio_cue=True,
                flash_rate_ms=250
            )

        elif self.current_state == VehicleState.CRITICAL_DNF:
            return UIStateTheme(
                state_name="CRITICAL_DNF",
                bg_color="#1F0000",
                accent_color=COLOR_ROSSO_CORSA,
                status_text="CAR RETIRED (DNF)",
                primary_fault_msg=fault_msg if fault_msg else "TERMINAL IMPACT DETECTED",
                pit_instruction="SYSTEMS FROZEN - AWAITING PIT RECOVERY",
                audio_cue=True,
                flash_rate_ms=100
            )

        return UIStateTheme(
            state_name="UNKNOWN",
            bg_color="#0F0F0F",
            accent_color="#888888",
            status_text="UNKNOWN STATE",
            primary_fault_msg="",
            pit_instruction="",
            audio_cue=False,
            flash_rate_ms=0
        )

    def _log_transition(self, new_state: VehicleState, rule_report: RuleReport):
        timestamp_str = time.strftime("%H:%M:%S", time.localtime())
        log_entry = f"[{timestamp_str}] FSM Transition -> {new_state.name} | Primary Fault: {self.last_primary_fault}"
        self.transition_history.append(log_entry)
        print(f"[FSM STATE CHANGE] {log_entry}")
