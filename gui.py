"""
F1 Telemetry System - Dual-View CustomTkinter GUI (gui.py)
Implements:
- 3-Column Grid Layout (3 : 4 : 3 weight ratio)
- Scuderia Ferrari Visual Identity (Rosso Corsa #E8002D, Giallo Modena #FFEB00, Matte Carbon #0F0F0F)
- Driver & Track Selector Dropdowns with real-time header update
- 2D Vector Track Map Canvas with moving glowing car dot & dynamic sector coloring
- Race Conditions & Weather Strategy Card
- Interactive Engine Mode Selection Buttons (PUSH, SAVE FUEL, OVERTAKE)
- Telemetry Blackbox CSV Export
- Pre-instantiated zero-ghosting labels updated via .configure(text=...)
- Thread-safe queue polling via root.after(16, ...)
"""

import sys
import os
import time
import csv
import queue
import math
import tkinter as tk
try:
    import customtkinter as ctk
    ctk.set_appearance_mode("Dark")
    ctk.set_default_color_theme("dark-blue")
except ImportError:
    ctk = tk # Fallback if run standalone without ctk

from filters import TelemetryFilterBank
from rules import DeterministicRuleEngine, RuleReport
from fsm import VehicleFSM, VehicleState, UIStateTheme

# Scuderia Ferrari Color Constants
ROSSO_CORSA = "#E8002D"
GIALLO_MODENA = "#FFEB00"
MATTE_CARBON = "#0F0F0F"
CARBON_CARD = "#1A1A1A"
CARBON_BORDER = "#2A2A2A"
NORMAL_GREEN = "#00FF66"
CYAN_ERS = "#00E5FF"
TEXT_WHITE = "#FFFFFF"
TEXT_MUTED = "#888888"

class F1TelemetryGUI:
    def __init__(self, telemetry_queue: queue.Queue, simulator_ref=None):
        self.queue = telemetry_queue
        self.simulator = simulator_ref
        self.rule_engine = DeterministicRuleEngine()
        self.fsm = VehicleFSM(hysteresis_seconds=0.5)
        self.filter_bank = TelemetryFilterBank()

        # Buffer for Blackbox CSV Export
        self.telemetry_history = []
        self.max_history_length = 2000

        # Root Window
        if hasattr(ctk, 'CTk'):
            self.root = ctk.CTk()
        else:
            self.root = tk.Tk()

        self.root.title("SCUDERIA FERRARI F1 TELEMETRY CONSOLE")
        self.root.geometry("1400x880")
        self.root.configure(bg=MATTE_CARBON)

        # Performance Monitoring
        self.start_time = time.time()
        self.frame_count = 0
        self.last_fps_calc = time.time()
        self.current_fps = 60.0

        # Build UI Architecture
        self._build_header()
        self._build_main_grid()
        self._build_footer()

        # Start 60 FPS Event Loop
        self.root.after(16, self._gui_update_loop)

    def _build_header(self):
        """Top Header Bar with Ferrari Branding & Selectors."""
        header_frame = ctk.CTkFrame(self.root, fg_color=CARBON_CARD, border_color=CARBON_BORDER, border_width=1, corner_radius=10)
        header_frame.pack(fill="x", padx=10, pady=(10, 5))

        # Italian Tricolore Top Accent Line
        tricolore_frame = ctk.CTkFrame(header_frame, height=4, fg_color="transparent")
        tricolore_frame.pack(fill="x")
        ctk.CTkFrame(tricolore_frame, width=100, height=4, fg_color="#009246").pack(side="left", fill="x", expand=True)
        ctk.CTkFrame(tricolore_frame, width=100, height=4, fg_color="#FFFFFF").pack(side="left", fill="x", expand=True)
        ctk.CTkFrame(tricolore_frame, width=100, height=4, fg_color="#CE2B37").pack(side="left", fill="x", expand=True)

        content = ctk.CTkFrame(header_frame, fg_color="transparent")
        content.pack(fill="x", padx=15, pady=8)

        # SF Badge & Title
        left_box = ctk.CTkFrame(content, fg_color="transparent")
        left_box.pack(side="left")

        self.lbl_team_badge = ctk.CTkLabel(
            left_box, text="SF", font=("Helvetica", 16, "bold"),
            fg_color=ROSSO_CORSA, text_color=GIALLO_MODENA, width=36, height=36, corner_radius=6
        )
        self.lbl_team_badge.pack(side="left", padx=(0, 10))

        title_sub_box = ctk.CTkFrame(left_box, fg_color="transparent")
        title_sub_box.pack(side="left")

        self.lbl_header_driver = ctk.CTkLabel(
            title_sub_box, text="C. LECLERC [16]", font=("Helvetica", 18, "bold"), text_color=TEXT_WHITE, anchor="w"
        )
        self.lbl_header_driver.pack(anchor="w")

        self.lbl_header_team = ctk.CTkLabel(
            title_sub_box, text="SCUDERIA FERRARI - HP", font=("Helvetica", 11, "bold"), text_color=GIALLO_MODENA, anchor="w"
        )
        self.lbl_header_team.pack(anchor="w")

        # Selectors Middle Box
        mid_box = ctk.CTkFrame(content, fg_color="transparent")
        mid_box.pack(side="left", expand=True)

        # Driver Dropdown
        self.opt_driver = ctk.CTkOptionMenu(
            mid_box,
            values=[
                "C. LECLERC [16] - SCUDERIA FERRARI",
                "L. HAMILTON [44] - SCUDERIA FERRARI",
                "M. VERSTAPPEN [1] - RED BULL RACING",
                "L. NORRIS [4] - MCLAREN F1",
                "C. SAINZ [55] - WILLIAMS RACING"
            ],
            command=self._on_driver_changed,
            fg_color=CARBON_CARD, button_color=ROSSO_CORSA, text_color=TEXT_WHITE,
            width=220, dropdown_fg_color=CARBON_CARD
        )
        self.opt_driver.pack(side="left", padx=10)

        # Track Dropdown
        self.opt_track = ctk.CTkOptionMenu(
            mid_box,
            values=[
                "MONZA - ITALY (HOME RACE)",
                "SPA-FRANCORCHAMPS",
                "SILVERSTONE - UK",
                "JEDDAH CORNICHE",
                "MONACO"
            ],
            command=self._on_track_changed,
            fg_color=CARBON_CARD, button_color=ROSSO_CORSA, text_color=TEXT_WHITE,
            width=220, dropdown_fg_color=CARBON_CARD
        )
        self.opt_track.pack(side="left", padx=10)

        # Live Status Badge & Delta Box
        right_box = ctk.CTkFrame(content, fg_color="transparent")
        right_box.pack(side="right")

        self.lbl_header_lap = ctk.CTkLabel(
            right_box, text="LAP 14/53  |  POS: P1  |  DELTA: +0.142",
            font=("Consolas", 13, "bold"), text_color=TEXT_WHITE
        )
        self.lbl_header_lap.pack(anchor="e", pady=(0, 2))

        self.lbl_live_status = ctk.CTkLabel(
            right_box, text="● LIVE TELEMETRY (20Hz)", font=("Helvetica", 11, "bold"),
            text_color=NORMAL_GREEN, fg_color="#003311", padx=10, pady=3, corner_radius=12
        )
        self.lbl_live_status.pack(anchor="e")

    def _build_main_grid(self):
        """3-Column Grid Layout (3 : 4 : 3 weight ratio)."""
        grid_container = ctk.CTkFrame(self.root, fg_color="transparent")
        grid_container.pack(fill="both", expand=True, padx=10, pady=5)

        grid_container.grid_columnconfigure(0, weight=3) # Left: Tires & Engine
        grid_container.grid_columnconfigure(1, weight=4) # Center: Performance Core (DDU)
        grid_container.grid_columnconfigure(2, weight=3) # Right: Track Map & Strategy

        grid_container.grid_rowconfigure(0, weight=1)

        # ---------------------------------------------------------------------
        # LEFT COLUMN (Tires & Engine)
        # ---------------------------------------------------------------------
        col_left = ctk.CTkFrame(grid_container, fg_color="transparent")
        col_left.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)

        # 4-Wheel Thermal Cards Frame
        tire_card = ctk.CTkFrame(col_left, fg_color=CARBON_CARD, border_color=CARBON_BORDER, border_width=1, corner_radius=10)
        tire_card.pack(fill="x", pady=(0, 10))

        lbl_tire_title = ctk.CTkLabel(tire_card, text="4-WHEEL THERMAL & WEAR MATRIX", font=("Helvetica", 12, "bold"), text_color=GIALLO_MODENA)
        lbl_tire_title.pack(anchor="w", padx=12, pady=(10, 5))

        # 2x2 Grid for Tires
        tires_grid = ctk.CTkFrame(tire_card, fg_color="transparent")
        tires_grid.pack(fill="x", padx=10, pady=5)
        tires_grid.columnconfigure(0, weight=1)
        tires_grid.columnconfigure(1, weight=1)

        self.tire_widgets = {}
        corners = [("FL", 0, 0), ("FR", 0, 1), ("RL", 1, 0), ("RR", 1, 1)]
        for name, r, c in corners:
            box = ctk.CTkFrame(tires_grid, fg_color=MATTE_CARBON, border_color=CARBON_BORDER, border_width=1, corner_radius=8)
            box.grid(row=r, column=c, padx=5, pady=5, sticky="nsew")

            lbl_name = ctk.CTkLabel(box, text=f"TIRE {name}", font=("Helvetica", 11, "bold"), text_color=TEXT_MUTED)
            lbl_name.pack(anchor="w", padx=8, pady=(6, 2))

            lbl_val = ctk.CTkLabel(box, text="92.0°C | 23.5 PSI", font=("Consolas", 12, "bold"), text_color=TEXT_WHITE)
            lbl_val.pack(anchor="w", padx=8)

            lbl_wear = ctk.CTkLabel(box, text="WEAR: 35.0%", font=("Helvetica", 10, "bold"), text_color=NORMAL_GREEN)
            lbl_wear.pack(anchor="w", padx=8, pady=(2, 6))

            self.tire_widgets[name] = {"val": lbl_val, "wear": lbl_wear, "box": box}

        # Progress Bars for Max Brake Temp & Avg Wear Level
        bars_frame = ctk.CTkFrame(tire_card, fg_color="transparent")
        bars_frame.pack(fill="x", padx=12, pady=(5, 12))

        ctk.CTkLabel(bars_frame, text="MAX BRAKE TEMP", font=("Helvetica", 10, "bold"), text_color=TEXT_MUTED).pack(anchor="w")
        self.bar_brake_temp = ctk.CTkProgressBar(bars_frame, height=8, progress_color=ROSSO_CORSA)
        self.bar_brake_temp.pack(fill="x", pady=(2, 8))
        self.bar_brake_temp.set(0.6)

        ctk.CTkLabel(bars_frame, text="AVG TIRE WEAR LEVEL", font=("Helvetica", 10, "bold"), text_color=TEXT_MUTED).pack(anchor="w")
        self.bar_avg_wear = ctk.CTkProgressBar(bars_frame, height=8, progress_color=GIALLO_MODENA)
        self.bar_avg_wear.pack(fill="x", pady=(2, 2))
        self.bar_avg_wear.set(0.35)

        # Engine & Hydraulics Panel
        engine_card = ctk.CTkFrame(col_left, fg_color=CARBON_CARD, border_color=CARBON_BORDER, border_width=1, corner_radius=10)
        engine_card.pack(fill="both", expand=True)

        ctk.CTkLabel(engine_card, text="POWERTRAIN & HYDRAULICS", font=("Helvetica", 12, "bold"), text_color=GIALLO_MODENA).pack(anchor="w", padx=12, pady=(10, 5))

        eng_grid = ctk.CTkFrame(engine_card, fg_color="transparent")
        eng_grid.pack(fill="x", padx=12, pady=5)

        self.lbl_oil_pres = ctk.CTkLabel(eng_grid, text="OIL PRES: 72.0 PSI", font=("Consolas", 13, "bold"), text_color=NORMAL_GREEN, anchor="w")
        self.lbl_oil_pres.pack(fill="x", pady=3)

        self.lbl_oil_temp = ctk.CTkLabel(eng_grid, text="OIL TEMP: 108.0 °C", font=("Consolas", 13, "bold"), text_color=TEXT_WHITE, anchor="w")
        self.lbl_oil_temp.pack(fill="x", pady=3)

        self.lbl_hyd_pres = ctk.CTkLabel(eng_grid, text="HYD PRES: 2850 PSI", font=("Consolas", 13, "bold"), text_color=TEXT_WHITE, anchor="w")
        self.lbl_hyd_pres.pack(fill="x", pady=3)

        self.lbl_fuel_flow = ctk.CTkLabel(eng_grid, text="FUEL FLOW: 98.5 kg/h", font=("Consolas", 13, "bold"), text_color=TEXT_WHITE, anchor="w")
        self.lbl_fuel_flow.pack(fill="x", pady=3)

        # ---------------------------------------------------------------------
        # CENTER COLUMN (Performance Core - DDU)
        # ---------------------------------------------------------------------
        col_center = ctk.CTkFrame(grid_container, fg_color=CARBON_CARD, border_color=CARBON_BORDER, border_width=1, corner_radius=10)
        col_center.grid(row=0, column=1, sticky="nsew", padx=5, pady=5)

        # Driver Warning Banner
        self.banner_frame = ctk.CTkFrame(col_center, fg_color="#0F0F0F", corner_radius=8, border_color=NORMAL_GREEN, border_width=2)
        self.banner_frame.pack(fill="x", padx=15, pady=12)

        self.lbl_banner_title = ctk.CTkLabel(self.banner_frame, text="SYSTEMS OPTIMAL", font=("Helvetica", 16, "bold"), text_color=NORMAL_GREEN)
        self.lbl_banner_title.pack(pady=(8, 2))

        self.lbl_banner_subtitle = ctk.CTkLabel(self.banner_frame, text="STAY OUT - PUSH MODE ACTIVE", font=("Helvetica", 11, "bold"), text_color=TEXT_WHITE, wraplength=420)
        self.lbl_banner_subtitle.pack(pady=(0, 8))

        # RPM Shift Light Bar
        shift_frame = ctk.CTkFrame(col_center, fg_color="transparent")
        shift_frame.pack(fill="x", padx=20, pady=5)

        self.shift_lights = []
        for i in range(12):
            color = NORMAL_GREEN if i < 5 else (GIALLO_MODENA if i < 9 else ROSSO_CORSA)
            led = ctk.CTkFrame(shift_frame, width=24, height=14, fg_color="#222222", corner_radius=3)
            led.pack(side="left", expand=True, padx=2)
            self.shift_lights.append((led, color))

        # Massive Gear & Speed Display
        gear_frame = ctk.CTkFrame(col_center, fg_color=MATTE_CARBON, border_color=CARBON_BORDER, border_width=1, corner_radius=12)
        gear_frame.pack(fill="x", padx=20, pady=10)

        self.lbl_gear_val = ctk.CTkLabel(gear_frame, text="7", font=("Helvetica", 72, "bold"), text_color=GIALLO_MODENA)
        self.lbl_gear_val.pack(pady=(5, 0))

        ctk.CTkLabel(gear_frame, text="GEAR", font=("Helvetica", 12, "bold"), text_color=TEXT_MUTED).pack(pady=(0, 5))

        metrics_sub = ctk.CTkFrame(gear_frame, fg_color="transparent")
        metrics_sub.pack(fill="x", padx=15, pady=10)

        self.lbl_speed_val = ctk.CTkLabel(metrics_sub, text="285 KM/H", font=("Consolas", 24, "bold"), text_color=TEXT_WHITE)
        self.lbl_speed_val.pack(side="left", expand=True)

        self.lbl_rpm_val = ctk.CTkLabel(metrics_sub, text="12200 RPM", font=("Consolas", 24, "bold"), text_color=TEXT_WHITE)
        self.lbl_rpm_val.pack(side="right", expand=True)

        # DRS & ERS Panel
        drs_ers_frame = ctk.CTkFrame(col_center, fg_color="transparent")
        drs_ers_frame.pack(fill="x", padx=20, pady=5)

        self.lbl_drs_status = ctk.CTkLabel(
            drs_ers_frame, text="DRS ACTIVE", font=("Helvetica", 12, "bold"),
            fg_color="#003311", text_color=NORMAL_GREEN, padx=12, pady=6, corner_radius=8
        )
        self.lbl_drs_status.pack(side="left", padx=(0, 10))

        ers_sub = ctk.CTkFrame(drs_ers_frame, fg_color="transparent")
        ers_sub.pack(side="right", fill="x", expand=True)

        self.lbl_ers_status = ctk.CTkLabel(ers_sub, text="ERS SoC: 82% [DEPLOYING]", font=("Consolas", 11, "bold"), text_color=CYAN_ERS, anchor="e")
        self.lbl_ers_status.pack(anchor="e", pady=(0, 2))

        self.bar_ers_soc = ctk.CTkProgressBar(ers_sub, height=8, progress_color=CYAN_ERS)
        self.bar_ers_soc.pack(fill="x")
        self.bar_ers_soc.set(0.82)

        # Engine Mode Selector Buttons
        mode_btn_frame = ctk.CTkFrame(col_center, fg_color="transparent")
        mode_btn_frame.pack(fill="x", padx=20, pady=12)

        ctk.CTkLabel(mode_btn_frame, text="ENGINE MODES & ERS MAPS", font=("Helvetica", 11, "bold"), text_color=TEXT_MUTED).pack(anchor="w", pady=(0, 5))

        modes_box = ctk.CTkFrame(mode_btn_frame, fg_color="transparent")
        modes_box.pack(fill="x")

        self.btn_push = ctk.CTkButton(
            modes_box, text="PUSH MODE", font=("Helvetica", 11, "bold"),
            fg_color=ROSSO_CORSA, hover_color="#B30022", command=lambda: self._set_engine_mode("PUSH")
        )
        self.btn_push.pack(side="left", expand=True, padx=2)

        self.btn_save = ctk.CTkButton(
            modes_box, text="SAVE FUEL", font=("Helvetica", 11, "bold"),
            fg_color="#333333", hover_color="#444444", command=lambda: self._set_engine_mode("SAVE_FUEL")
        )
        self.btn_save.pack(side="left", expand=True, padx=2)

        self.btn_overtake = ctk.CTkButton(
            modes_box, text="OVERTAKE", font=("Helvetica", 11, "bold"),
            fg_color="#006699", hover_color="#0088CC", command=lambda: self._set_engine_mode("OVERTAKE")
        )
        self.btn_overtake.pack(side="left", expand=True, padx=2)

        # ---------------------------------------------------------------------
        # RIGHT COLUMN (Track Map & Strategy)
        # ---------------------------------------------------------------------
        col_right = ctk.CTkFrame(grid_container, fg_color="transparent")
        col_right.grid(row=0, column=2, sticky="nsew", padx=5, pady=5)

        # 2D Interactive Track Map Visualizer
        map_card = ctk.CTkFrame(col_right, fg_color=CARBON_CARD, border_color=CARBON_BORDER, border_width=1, corner_radius=10)
        map_card.pack(fill="x", pady=(0, 10))

        ctk.CTkLabel(map_card, text="2D VECTOR TRACK MAP (MONZA)", font=("Helvetica", 12, "bold"), text_color=GIALLO_MODENA).pack(anchor="w", padx=12, pady=(8, 4))

        self.map_canvas = tk.Canvas(map_card, height=150, bg=MATTE_CARBON, highlightthickness=0)
        self.map_canvas.pack(fill="x", padx=10, pady=(0, 8))
        self._draw_track_outline()

        # Weather Strategy Card
        weather_card = ctk.CTkFrame(col_right, fg_color=CARBON_CARD, border_color=CARBON_BORDER, border_width=1, corner_radius=10)
        weather_card.pack(fill="x", pady=(0, 10))

        ctk.CTkLabel(weather_card, text="RACE CONDITIONS & PIT STRATEGY", font=("Helvetica", 12, "bold"), text_color=GIALLO_MODENA).pack(anchor="w", padx=12, pady=(8, 4))

        weath_grid = ctk.CTkFrame(weather_card, fg_color="transparent")
        weath_grid.pack(fill="x", padx=12, pady=2)

        self.lbl_weath_info = ctk.CTkLabel(weath_grid, text="TRACK TEMP: 38°C  |  RAIN: 0%", font=("Consolas", 11, "bold"), text_color=TEXT_WHITE, anchor="w")
        self.lbl_weath_info.pack(anchor="w")

        self.lbl_compound_badge = ctk.CTkLabel(weath_grid, text="COMPOUND: SOFT [SLICK]", font=("Helvetica", 10, "bold"), text_color=GIALLO_MODENA, anchor="w")
        self.lbl_compound_badge.pack(anchor="w", pady=(2, 4))

        self.lbl_strategy_rec = ctk.CTkLabel(weath_grid, text="STRATEGY: STAY OUT - NOMINAL", font=("Helvetica", 10, "bold"), text_color=NORMAL_GREEN, anchor="w", wraplength=320)
        self.lbl_strategy_rec.pack(anchor="w", pady=(0, 6))

        # Fault Injection & Blackbox Exporter Panel
        fault_card = ctk.CTkFrame(col_right, fg_color=CARBON_CARD, border_color=CARBON_BORDER, border_width=1, corner_radius=10)
        fault_card.pack(fill="both", expand=True)

        ctk.CTkLabel(fault_card, text="SIMULATOR FAULT INJECTION", font=("Helvetica", 12, "bold"), text_color=GIALLO_MODENA).pack(anchor="w", padx=12, pady=(8, 4))

        btn_grid1 = ctk.CTkFrame(fault_card, fg_color="transparent")
        btn_grid1.pack(fill="x", padx=10, pady=2)

        ctk.CTkButton(btn_grid1, text="OIL LEAK", font=("Helvetica", 10, "bold"), fg_color="#661111", hover_color="#991111", command=self._trigger_oil_leak).pack(side="left", expand=True, padx=2)
        ctk.CTkButton(btn_grid1, text="TIRE OVERHEAT", font=("Helvetica", 10, "bold"), fg_color="#661111", hover_color="#991111", command=self._trigger_tire_overheat).pack(side="left", expand=True, padx=2)

        btn_grid2 = ctk.CTkFrame(fault_card, fg_color="transparent")
        btn_grid2.pack(fill="x", padx=10, pady=4)

        ctk.CTkButton(btn_grid2, text="BRAKE RUNAWAY", font=("Helvetica", 10, "bold"), fg_color="#661111", hover_color="#991111", command=self._trigger_brake_runaway).pack(side="left", expand=True, padx=2)
        ctk.CTkButton(btn_grid2, text="RESET SYSTEMS", font=("Helvetica", 10, "bold"), fg_color="#006622", hover_color="#009933", command=self._reset_faults).pack(side="left", expand=True, padx=2)

        ctk.CTkButton(
            fault_card, text="EXPORT BLACKBOX LOG (.CSV)", font=("Helvetica", 11, "bold"),
            fg_color="#333333", hover_color="#555555", command=self.export_blackbox_log
        ).pack(fill="x", padx=12, pady=(6, 8))

    def _build_footer(self):
        """Bottom Footer Bar with System Diagnostics."""
        footer_frame = ctk.CTkFrame(self.root, fg_color=CARBON_CARD, height=28, corner_radius=0)
        footer_frame.pack(fill="x", side="bottom")

        self.lbl_footer_sys = ctk.CTkLabel(
            footer_frame, text="SYSTEM STATUS: NOMINAL  |  CPU: 4.2%  |  RAM: 182 MB  |  UPTIME: 00:02:14  |  RATE: 20 Hz (60 FPS)",
            font=("Consolas", 10, "bold"), text_color=TEXT_MUTED
        )
        self.lbl_footer_sys.pack(side="left", padx=15, pady=4)

    def _draw_track_outline(self):
        """Draws Monza 2D vector outline on Canvas."""
        self.map_canvas.delete("all")
        # Monza closed vector polygon coordinates
        self.track_points = [
            (30, 120), (120, 120), (220, 120), (310, 100), (330, 70),
            (300, 30), (200, 30), (140, 50), (90, 30), (40, 50), (30, 120)
        ]
        
        # Smooth polygon
        flat_pts = [c for p in self.track_points for c in p]
        self.track_line = self.map_canvas.create_line(flat_pts, fill="#444444", width=4, smooth=True)
        
        # Car dot marker
        self.car_dot = self.map_canvas.create_oval(25, 115, 35, 125, fill=ROSSO_CORSA, outline="#FFFFFF", width=2)

    def _update_car_on_map(self, progress: float, is_warning: bool = False):
        """Moves glowing car dot along the 2D vector track canvas."""
        n = len(self.track_points) - 1
        idx = progress * n
        i = int(idx)
        t = idx - i
        i2 = min(i + 1, n)

        x1, y1 = self.track_points[i]
        x2, y2 = self.track_points[i2]

        cx = x1 + (x2 - x1) * t
        cy = y1 + (y2 - y1) * t

        self.map_canvas.coords(self.car_dot, cx - 6, cy - 6, cx + 6, cy + 6)
        
        dot_color = ROSSO_CORSA if not is_warning else GIALLO_MODENA
        self.map_canvas.itemconfig(self.car_dot, fill=dot_color)

    def _on_driver_changed(self, choice: str):
        if self.simulator:
            self.simulator.set_driver_and_track(choice, self.opt_track.get())
        if "HAMILTON" in choice:
            self.lbl_header_driver.configure(text="L. HAMILTON [44]")
        elif "VERSTAPPEN" in choice:
            self.lbl_header_driver.configure(text="M. VERSTAPPEN [1]")
            self.lbl_header_team.configure(text="RED BULL RACING")
        elif "NORRIS" in choice:
            self.lbl_header_driver.configure(text="L. NORRIS [4]")
            self.lbl_header_team.configure(text="MCLAREN F1")
        elif "SAINZ" in choice:
            self.lbl_header_driver.configure(text="C. SAINZ [55]")
            self.lbl_header_team.configure(text="WILLIAMS RACING")
        else:
            self.lbl_header_driver.configure(text="C. LECLERC [16]")
            self.lbl_header_team.configure(text="SCUDERIA FERRARI - HP")

    def _on_track_changed(self, choice: str):
        if self.simulator:
            self.simulator.set_driver_and_track(self.opt_driver.get(), choice)

    def _set_engine_mode(self, mode: str):
        if self.simulator:
            self.simulator.set_engine_mode(mode)
        self.btn_push.configure(fg_color=ROSSO_CORSA if mode == "PUSH" else "#333333")
        self.btn_save.configure(fg_color=ROSSO_CORSA if mode == "SAVE_FUEL" else "#333333")
        self.btn_overtake.configure(fg_color=CYAN_ERS if mode == "OVERTAKE" else "#333333")

    def _trigger_oil_leak(self):
        if self.simulator:
            self.simulator.trigger_oil_leak()

    def _trigger_tire_overheat(self):
        if self.simulator:
            self.simulator.trigger_tire_overheat()

    def _trigger_brake_runaway(self):
        if self.simulator:
            self.simulator.trigger_brake_runaway()

    def _reset_faults(self):
        if self.simulator:
            self.simulator.reset_faults()

    def export_blackbox_log(self):
        """Saves telemetry frames in buffer to timestamped CSV file."""
        if not self.telemetry_history:
            print("[BLACKBOX EXPORT] Buffer empty, nothing to write.")
            return

        filename = f"ferrari_blackbox_log_{int(time.time())}.csv"
        try:
            keys = self.telemetry_history[0].keys()
            with open(filename, 'w', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=keys)
                writer.writeheader()
                writer.writerows(self.telemetry_history)
            print(f"[BLACKBOX EXPORT SUCCESS] Telemetry log saved to {filename}")
        except Exception as e:
            print(f"[BLACKBOX EXPORT ERROR] {e}")

    def _gui_update_loop(self):
        """Thread-safe 60 FPS update loop polling queue."""
        packets_processed = 0
        latest_packet = None

        while not self.queue.empty() and packets_processed < 20:
            try:
                packet = self.queue.get_nowait()
                latest_packet = packet
                packets_processed += 1

                # Record in Blackbox buffer
                if len(self.telemetry_history) >= self.max_history_length:
                    self.telemetry_history.pop(0)
                self.telemetry_history.append(packet)

            except queue.Empty:
                break

        if latest_packet:
            # Apply Kalman Filter
            filtered_pkt = self.filter_bank.filter_packet(latest_packet)
            
            # Evaluate Rules & Update FSM
            report = self.rule_engine.evaluate(filtered_pkt)
            theme = self.fsm.update_state(report)

            # Update UI Widgets strictly via .configure(text=...)
            self._update_ui_views(filtered_pkt, report, theme)

        # Schedule Next Frame (~16 ms = 60 FPS)
        self.root.after(16, self._gui_update_loop)

    def _update_ui_views(self, pkt: dict, report: RuleReport, theme: UIStateTheme):
        # Header Info
        lap = pkt.get("lap", 14)
        tot_laps = pkt.get("total_laps", 53)
        pos = pkt.get("position", "P1")
        delta = pkt.get("delta_time", 0.142)
        self.lbl_header_lap.configure(text=f"LAP {lap}/{tot_laps}  |  POS: {pos}  |  DELTA: +{delta:.3f}")

        # Driver Warning Banner
        self.banner_frame.configure(border_color=theme.accent_color)
        self.lbl_banner_title.configure(text=theme.status_text, text_color=theme.accent_color)
        
        directive_text = report.driver_directive if theme.state_name == "NORMAL" else theme.primary_fault_msg
        self.lbl_banner_subtitle.configure(text=directive_text)

        # Gear, Speed, RPM
        gear = pkt.get("Gear", 7)
        speed = pkt.get("Speed", 285.0)
        rpm = pkt.get("RPM", 12200)

        self.lbl_gear_val.configure(text=str(gear) if gear > 0 else "N")
        self.lbl_speed_val.configure(text=f"{speed:.0f} KM/H")
        self.lbl_rpm_val.configure(text=f"{rpm} RPM")

        # Shift Lights
        rpm_ratio = min(1.0, max(0.0, (rpm - 8500) / (14500 - 8500)))
        active_leds = int(rpm_ratio * 12)
        for i, (led, color) in enumerate(self.shift_lights):
            led.configure(fg_color=color if i < active_leds else "#222222")

        # DRS & ERS
        drs = pkt.get("DRS", 0)
        self.lbl_drs_status.configure(
            text="DRS ACTIVE" if drs == 1 else "DRS OFF",
            fg_color="#003311" if drs == 1 else "#331111",
            text_color=NORMAL_GREEN if drs == 1 else TEXT_MUTED
        )

        ers_soc = pkt.get("ERS_SoC_%", 82.0)
        ers_state = pkt.get("ERS_State", "HARVESTING")
        self.lbl_ers_status.configure(text=f"ERS SoC: {ers_soc:.0f}% [{ers_state}]")
        self.bar_ers_soc.set(ers_soc / 100.0)

        # 4 Tires
        corners = ["FL", "FR", "RL", "RR"]
        for c in corners:
            temp = pkt.get(f"Tire_Temp_{c}", pkt.get(f"{c}_Tire_Temp", 92.0))
            pres = pkt.get(f"{c}_Tire_Pressure", 23.5)
            wear = pkt.get(f"Tire_Wear_{c}", pkt.get(f"{c}_Tire_Wear", 35.0))

            w_dict = self.tire_widgets[c]
            w_dict["val"].configure(text=f"{temp:.1f}°C | {pres:.1f} PSI")
            w_dict["wear"].configure(text=f"WEAR: {wear:.1f}%")

            # Color coding for wear
            wear_color = NORMAL_GREEN if wear < 60 else (GIALLO_MODENA if wear < 80 else ROSSO_CORSA)
            w_dict["wear"].configure(text_color=wear_color)

        # Powertrain
        oil_p = pkt.get("Engine_Oil_Pressure", 72.0)
        oil_t = pkt.get("Engine_Temp", 108.0)
        hyd_p = pkt.get("Hydraulic_Pressure", 2850.0)
        fuel_f = pkt.get("Fuel_Flow_Rate", 98.5)

        self.lbl_oil_pres.configure(text=f"OIL PRES: {oil_p:.1f} PSI", text_color=NORMAL_GREEN if oil_p > 45 else ROSSO_CORSA)
        self.lbl_oil_temp.configure(text=f"ENGINE TEMP: {oil_t:.1f} °C", text_color=TEXT_WHITE if oil_t < 120 else ROSSO_CORSA)
        self.lbl_hyd_pres.configure(text=f"HYD PRES: {hyd_p:.0f} PSI")
        self.lbl_fuel_flow.configure(text=f"FUEL FLOW: {fuel_f:.1f} kg/h")

        # 2D Track Map
        progress = pkt.get("lap_progress", 0.0)
        self._update_car_on_map(progress, is_warning=(theme.state_name != "NORMAL"))

        # Weather Strategy Card
        trk_t = pkt.get("Track_Temp_C", 38.0)
        rain_p = pkt.get("Track_Rain_%", 0.0)
        cmpd = pkt.get("Tire_Compound", "SOFT")
        self.lbl_weath_info.configure(text=f"TRACK TEMP: {trk_t:.1f}°C  |  RAIN: {rain_p:.0f}%")
        self.lbl_compound_badge.configure(text=f"COMPOUND: {cmpd}")
        self.lbl_strategy_rec.configure(text=f"STRATEGY: {report.strategy_recommendation}")

        # System Footer
        uptime_sec = int(time.time() - self.start_time)
        hrs = uptime_sec // 3600
        mins = (uptime_sec % 3600) // 60
        secs = uptime_sec % 60
        self.lbl_footer_sys.configure(
            text=f"SYSTEM STATUS: NOMINAL  |  CPU: 3.8%  |  RAM: 184 MB  |  UPTIME: {hrs:02d}:{mins:02d}:{secs:02d}  |  RATE: 20 Hz (60 FPS)"
        )

    def run(self):
        self.root.mainloop()


# CSS styling for Scuderia Ferrari / ApexGuard theme
CUSTOM_CSS = """
body, .gradio-container {
    background-color: #0F0F0F !important;
    color: #FFFFFF !important;
    font-family: 'Segoe UI', Roboto, Helvetica, sans-serif !important;
}
.ferrari-header {
    background: linear-gradient(90deg, #CE2B37 0%, #181818 100%) !important;
    padding: 14px 20px !important;
    border-radius: 8px !important;
    margin-bottom: 12px !important;
    border-left: 6px solid #FFD700 !important;
    box-shadow: 0 4px 12px rgba(206, 43, 55, 0.2) !important;
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
.status-normal {
    border: 2px solid #00FF66 !important;
    background-color: rgba(0, 255, 102, 0.08) !important;
    color: #00FF66 !important;
}
.status-warning {
    border: 2px solid #FFD700 !important;
    background-color: rgba(255, 215, 0, 0.08) !important;
    color: #FFD700 !important;
}
.status-critical {
    border: 2px solid #CE2B37 !important;
    background-color: rgba(206, 43, 55, 0.15) !important;
    color: #CE2B37 !important;
}
"""


def create_gui(
    process_telemetry_tick_fn,
    change_driver_track_fn,
    change_engine_mode_fn,
    inject_oil_leak_fn,
    inject_tire_overheat_fn,
    inject_brake_runaway_fn,
    inject_engine_overheat_fn,
    reset_all_faults_fn,
    export_blackbox_fn
):
    """
    Constructs and returns the Gradio Blocks UI interface compliant with Gradio 6.0 standards.
    """
    import gradio as gr

    with gr.Blocks() as demo:
        gr.HTML('<div class="tricolore-bar"></div>')
        
        with gr.Row(elem_classes=["ferrari-header"]):
            with gr.Column(scale=3):
                gr.Markdown(
                    "## 🏎️ **APEXGUARD** | Scuderia Ferrari F1 Real-Time Telemetry & Failure Warning System"
                )
            with gr.Column(scale=1):
                gr.Markdown("### **20 Hz DSP & Safety Engine**")

        # Driver & Track Selectors
        with gr.Row():
            driver_dropdown = gr.Dropdown(
                choices=[
                    "C. LECLERC [16] - SCUDERIA FERRARI",
                    "L. HAMILTON [44] - SCUDERIA FERRARI",
                    "M. VERSTAPPEN [1] - RED BULL RACING",
                    "L. NORRIS [4] - MCLAREN F1",
                    "C. SAINZ [55] - WILLIAMS RACING"
                ],
                value="C. LECLERC [16] - SCUDERIA FERRARI",
                label="SELECT DRIVER"
            )
            track_dropdown = gr.Dropdown(
                choices=[
                    "MONZA - ITALY (HOME RACE)",
                    "SPA-FRANCORCHAMPS",
                    "SILVERSTONE - UK",
                    "JEDDAH CORNICHE",
                    "MONACO"
                ],
                value="MONZA - ITALY (HOME RACE)",
                label="SELECT CIRCUIT"
            )
            selector_output = gr.Textbox(label="Config Status", value="Active Setup: C. LECLERC | MONZA", interactive=False)

        driver_dropdown.change(change_driver_track_fn, inputs=[driver_dropdown, track_dropdown], outputs=selector_output)
        track_dropdown.change(change_driver_track_fn, inputs=[driver_dropdown, track_dropdown], outputs=selector_output)

        # Dynamic Status Banner
        status_banner = gr.HTML(value="<div class='metric-box status-normal'>INITIALIZING TELEMETRY...</div>")

        # Main Metrics Display with 2D Track Map
        with gr.Row():
            with gr.Column(scale=1):
                speed_metric = gr.Textbox(label="SPEED", value="285 km/h", interactive=False)
                gear_metric = gr.Textbox(label="GEAR", value="7", interactive=False)
                rpm_metric = gr.Textbox(label="RPM", value="12200 RPM", interactive=False)
                drs_metric = gr.Textbox(label="DRS STATUS", value="DRS ACTIVE", interactive=False)
                ers_metric = gr.Textbox(label="ERS SoC", value="SoC 82%", interactive=False)

            with gr.Column(scale=1):
                gr.Markdown("### 🛞 4-Wheel Thermal Matrix")
                tires_html_box = gr.HTML()
                gr.Markdown("### ⚡ Powertrain & Hydraulics")
                powertrain_html_box = gr.HTML()

            with gr.Column(scale=1):
                gr.Markdown("### 🗺️ 2D Vector Track Map")
                track_map_box = gr.Plot(label="Track Map")

        # Interactive Control Panels
        gr.Markdown("### 🛠️ Race Controls & Simulator Fault Injection")
        with gr.Row():
            btn_push = gr.Button("PUSH MODE", variant="primary")
            btn_save = gr.Button("SAVE FUEL")
            btn_overtake = gr.Button("OVERTAKE (ERS)")

        btn_push.click(fn=lambda: change_engine_mode_fn("PUSH"), outputs=selector_output)
        btn_save.click(fn=lambda: change_engine_mode_fn("SAVE_FUEL"), outputs=selector_output)
        btn_overtake.click(fn=lambda: change_engine_mode_fn("OVERTAKE"), outputs=selector_output)

        with gr.Row():
            btn_oil = gr.Button("⚠️ INJECT OIL LEAK", variant="stop")
            btn_tire = gr.Button("⚠️ INJECT TIRE OVERHEAT", variant="stop")
            btn_brake = gr.Button("⚠️ INJECT BRAKE RUNAWAY", variant="stop")
            btn_eng = gr.Button("⚠️ INJECT ENGINE OVERHEAT", variant="stop")
            btn_reset = gr.Button("✅ RESET ALL FAULTS")

        log_box = gr.Textbox(label="Action Log", value="System operational.", interactive=False)

        btn_oil.click(inject_oil_leak_fn, outputs=log_box)
        btn_tire.click(inject_tire_overheat_fn, outputs=log_box)
        btn_brake.click(inject_brake_runaway_fn, outputs=log_box)
        btn_eng.click(inject_engine_overheat_fn, outputs=log_box)
        btn_reset.click(reset_all_faults_fn, outputs=log_box)

        with gr.Row():
            btn_export = gr.Button("📥 EXPORT BLACKBOX TELEMETRY LOG (.CSV)")
            file_download = gr.File(label="Download CSV")

        btn_export.click(export_blackbox_fn, outputs=file_download)

        # High-Frequency Periodic Timer (~20 Hz / 50ms)
        timer = gr.Timer(0.05)
        timer.tick(
            fn=process_telemetry_tick_fn,
            inputs=[driver_dropdown, track_dropdown],
            outputs=[
                status_banner,
                speed_metric,
                gear_metric,
                rpm_metric,
                drs_metric,
                ers_metric,
                tires_html_box,
                powertrain_html_box,
                track_map_box,
            ]
        )

    return demo

