# 🏎️ ApexGuard — Scuderia Ferrari F1 Real-Time Telemetry & Mechanical Failure Early Warning System

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python&logoColor=white)](https://python.org)
[![Gradio](https://img.shields.io/badge/Gradio-6.0%2B-orange?logo=gradio&logoColor=white)](app.py)
[![Google Gemini API](https://img.shields.io/badge/Google%20Gemini-AI%20Race%20Strategist-4285F4?logo=google&logoColor=white)](https://aistudio.google.com/)
[![ZeroGPU](https://img.shields.io/badge/Hugging%20Face-ZeroGPU%20Ready-yellow?logo=huggingface)](app.py)
[![Plotly](https://img.shields.io/badge/Visualization-Plotly%20%26%202D%20Vector-purple?logo=plotly)](app.py)
[![License: CC BY-NC 4.0](https://img.shields.io/badge/License-CC%20BY--NC%204.0-lightgrey.svg)](https://creativecommons.org/licenses/by-nc/4.0/)

**ApexGuard** is a high-frequency F1 telemetry simulation, digital signal processing (DSP), rate-of-change ($\Delta y / \Delta t$) mathematical derivative analyzer, mechanical failure early warning system, and **Google Gemini AI Race Strategy Advisor** styled in Scuderia Ferrari's racing visual identity (**Rosso Corsa `#CE2B37`**, **Giallo Modena `#FFD700`**, and **Italian Tricolore**).

ApexGuard combines safety-critical automotive engineering (track curvature dynamics, 1D Kalman signal filtering, numerical derivatives, tyre thermal degradation matrices) with **Google Gemini 2.5 Flash** for tactical pit stop windows, fuel delta optimization, and deep powertrain diagnostics.

---

## 🌟 Key Capabilities

### 1. 🧠 Google Gemini AI Pit Wall Race Strategist (`google-genai`)
- **Real-Time Telemetry Debriefs**: Evaluates instantaneous telemetry packets (temperatures, pressures, wear rates, lap progress, fuel burn) and delivers Scuderia Ferrari race engineer directives.
- **Custom Driver Queries**: Ask tactical questions in natural language (e.g., *"Can we extend this stint 5 more laps?"*, *"Analyze oil pressure drop and recommend engine mode"*).
- **Graceful Deterministic Fallback**: If the API key is not configured or network drops occur, the system automatically falls back to deterministic rule evaluations without interrupting the 10 Hz telemetry stream.

### 2. ⚙️ Deterministic Physics & Telemetry Engine (`app.py`)
- **Autodromo Nazionale Monza Geometry**:
  - Continuous 2D vector spline coordinates with real-time heading angles ($\theta = \text{atan2}(\Delta y, \Delta x)$).
  - Track-position-dependent speed profiling: Straights reaching **345+ km/h** with DRS, braking chicanes dropping to **~110 km/h**, and dynamic 8-gear shift mapping.
- **Dynamic Physics Parameters**:
  - **Tyre Compounds**: SOFT (C5 - high grip, fast wear), MEDIUM (C4 - balanced), and HARD (C3 - high durability) with compound-specific heat generation and friction coefficients.
  - **Fuel Mass Depletion**: Simulates fuel burn (~2.4 kg/lap) lightening car mass over stint distance, dynamically improving corner acceleration.
  - **DRS Aero Drag Reduction**: Automatically opens on Rettifilo and Serraglio straights (+12.5 km/h top speed boost).

### 3. 🧮 Rate-of-Change ($\frac{d}{dt}$) & Early Failure Warning Engine
- **Derivative Tracking**: Continuously computes second-order numerical rates of change ($\frac{dT}{dt}$ in $^\circ\text{C/s}$ and $\frac{dP}{dt}$ in $\text{bar/s}$).
- **Proactive Early Warning**: Detects anomalous trends (e.g., thermal spike $\frac{dT}{dt} > 1.8^\circ\text{C/s}$ accompanied by oil pressure drop $\frac{dP}{dt} < -0.25\text{ bar/s}$) **before** absolute thresholds are breached.
- **Critical Failure Alert**: Escalates to immediate shutdown mandate if absolute safety envelopes are exceeded ($T > 115^\circ\text{C}$ or $P < 1.0\text{ bar}$).
- **Pit Strategy Advisory**: Real-time evaluation of cumulative tyre wear triggering automated pit window calls (e.g., `BOX BOX: Tyre Wear Exceeds 70% Limit`).

### 4. 📊 Interactive Visualizations (Plotly & Vector Splines)
- **Monza 2D Vector Map**: Rotated top-down vector sprite of Charles Leclerc's #16 Ferrari car navigating the track with dynamic heading alignment.
- **G-Force Friction Traction Circle (G-G Diagram)**: Real-time Plotly scatter plot rendering lateral cornering loads ($G_{\text{lat}}$) vs longitudinal braking/acceleration loads ($G_{\text{lon}}$) within concentric friction limits ($1.5g$, $3.0g$, $4.5g$).
- **4-Wheel Thermal Matrix & Powertrain Dashboard**: Live FL, FR, RL, RR tyre temps and wear percentages alongside oil pressure, engine temp, brake temp, and ERS battery state of charge.

### 5. 🛠️ Interactive Fault Injections & Blackbox Export
- Real-time interactive triggers:
  - `PUSH MODE (ERS)` / `SAVE FUEL` / `OVERTAKE`
  - `⚠️ INJECT OIL LEAK` (simulates pressure line breach)
  - `⚠️ INJECT ENGINE OVERHEAT` (simulates radiator blockage)
  - `✅ RESET ALL FAULTS` (recalibrates baseline nominal telemetry)
- **Blackbox Telemetry (.CSV) Export**: Instant single-click export of full session telemetry records for engineering debriefs.

---

## 🔑 Setup & Configuration (Google Gemini API)

ApexGuard uses the official `google-genai` Python SDK to communicate with Google Gemini models.

### Step 1: Obtain a Free Gemini API Key
1. Go to [Google AI Studio](https://aistudio.google.com/).
2. Sign in with your Google account.
3. Click **"Get API key"** and create a new API key.

### Step 2: Set the Environment Variable

#### On Linux / macOS / Bash:
```bash
export GEMINI_API_KEY="your_actual_gemini_api_key_here"
```

#### On Windows (PowerShell):
```powershell
$env:GEMINI_API_KEY="your_actual_gemini_api_key_here"
```

#### On Windows (Command Prompt):
```cmd
set GEMINI_API_KEY=your_actual_gemini_api_key_here
```

#### Using a `.env` file:
Create a `.env` file in the root directory:
```env
GEMINI_API_KEY=your_actual_gemini_api_key_here
```

#### On Hugging Face Spaces:
1. Navigate to your Space's **Settings** tab.
2. Under **Variables and secrets**, click **New secret**.
3. Set **Name** to `GEMINI_API_KEY` and **Value** to your API key.

---

## 📐 System Architecture & Data Flow

```
   ┌────────────────────────────────────────────────────────┐
   │ 2D Monza Vector Geometry & Curvature Profile (Spline)  │
   └──────────────────────────┬─────────────────────────────┘
                              │
                              ▼
   ┌────────────────────────────────────────────────────────┐
   │ Deterministic Telemetry & Vehicle Physics Core         │
   │  ├── Curvature-to-Speed & Shift Mapping (Gears 1-8)   │
   │  ├── Fuel Mass Burn & Mass Acceleration Dynamics      │
   │  ├── Tyre Compound Models (Soft C5, Med C4, Hard C3)  │
   │  └── DRS Drag Reduction & ERS Battery Management      │
   └──────────────────────────┬─────────────────────────────┘
                              │
                              ▼
   ┌────────────────────────────────────────────────────────┐
   │ Rate-of-Change (d/dt) & Proactive Failure Rule Engine  │
   │  ├── Numerical Derivatives (dT/dt, dP/dt)              │
   │  ├── Early Warning Detection (Thermal/Pressure Spike)  │
   │  ├── Critical Boundary Threshold Alerts                │
   │  └── Pit Strategy & Tyre Wear Advisory Engine          │
   └─────────────┬────────────────────────────┬─────────────┘
                 │                            │
                 ▼                            ▼
   ┌───────────────────────────┐ ┌──────────────────────────┐
   │ Google Gemini 2.5 Flash   │ │ User Interfaces          │
   │  ├── Live Telemetry Prompt│ │  ├── Hugging Face Spaces │
   │  ├── Tactical Radio Calls │ │  ├── React 19 Dashboard  │
   │  └── Undercut Strategies  │ │  └── Native CustomTkinter│
   └───────────────────────────┘ └──────────────────────────┘
```

---

## 📂 Repository File Structure

```
.
├── app.py           # Hugging Face Spaces entrypoint (Gradio 6.0+, ZeroGPU, Plotly & Gemini AI)
├── simulator.py     # High-frequency UDP telemetry generator (20 Hz)
├── network.py       # Asynchronous UDP socket listener & watchdog thread
├── rules.py         # Deterministic physics rule engine, derivatives & Gemini integration
├── fsm.py           # Finite State Machine with hysteresis & terminal DNF locks
├── filters.py       # 1D Kalman Filter digital signal processing
├── gui.py           # Native CustomTkinter desktop interface (3-column layout)
├── main.py          # Native Python desktop application orchestrator
├── requirements.txt # Python dependencies (google-genai, gradio, spaces, numpy, plotly)
├── src/             # Web Telemetry Console (React 19 + Tailwind CSS)
│   ├── App.tsx      # Main telemetry dashboard component
│   └── main.tsx     # React DOM entrypoint
├── metadata.json    # Application metadata
└── package.json     # Web environment configuration
```

---

## 🚀 Quick Start & Deployment Guide

### Option 1: Deploy to Hugging Face Spaces (Gradio, ZeroGPU & Gemini)

1. Create a new Space on [Hugging Face Spaces](https://huggingface.co/spaces) and select **Gradio** as the SDK.
2. Upload `app.py` and `requirements.txt`.
3. In Space Settings, add the `GEMINI_API_KEY` secret.
4. Hugging Face Spaces will automatically launch the Scuderia Ferrari Telemetry Console.

---

### Option 2: Run Python App Locally

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Export your Gemini API key
export GEMINI_API_KEY="your_api_key_here"

# 3. Run the Gradio application
python app.py
```
Open `http://localhost:7860` in your web browser.

---

### Option 3: Web Dashboard (React 19 + Vite)

```bash
npm install
npm run dev
```
Open `http://localhost:3000` in your browser.

---

### Option 4: Native Desktop Application (Python & CustomTkinter)

```bash
pip install customtkinter pandas numpy google-genai python-dotenv
python main.py
```

---

## 🎮 Failure Injections & Operating States

| Injected Event | Physical Telemetry Response | System State Escalation | Gemini AI Action |
|---|---|---|---|
| **Nominal Lap** | Oil: 4.85 bar, Temp: 104°C, Wear: Normal | `✅ NOMINAL` | Pushes pace delta & optimizes stint window |
| **Early Warning** | $\frac{dT}{dt} > 1.8^\circ\text{C/s}$ and $\frac{dP}{dt} < -0.25\text{ bar/s}$ | `⚠️ EARLY_WARNING` | Diagnoses line leak & issues Lift/Coast call |
| **Oil Pressure Breach** | Oil drops below $1.0\text{ bar}$ | `🚨 CRITICAL` | Issues emergency retirement radio command |
| **Engine Overheat** | Engine temp surges $> 115^\circ\text{C}$ | `🚨 CRITICAL` | Commands immediate powertrain shutdown |
| **High Tyre Degradation** | Maximum tyre wear $> 70\%$ | `🚨 STRATEGY` | Calls `BOX BOX` for compound swap (Plan B) |

---

## 📑 License

This project is licensed under the **Creative Commons Attribution-NonCommercial 4.0 International (CC BY-NC 4.0)** License. See the [Creative Commons License Details](https://creativecommons.org/licenses/by-nc/4.0/) for full terms.

---
*Scuderia Ferrari racing aesthetic and visual styling used for technical simulation and educational purposes.*
