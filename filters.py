"""
F1 Telemetry System - Digital Signal Processing & Kalman Filter (filters.py)
Provides 1D Kalman Filtering for real-time sensor noise suppression on high-frequency streams
(Vehicle Speed, RPM, Oil Pressure, Brake Temperatures, Tire Temperatures).

Mathematical State Update Model:
1. State Estimation Prediction:  P_k = P_{k-1} + Q
2. Kalman Gain Calculation:      K_k = P_k / (P_k + R)
3. Measurement Update:           x_k = x_k + K_k * (z_k - x_k)
4. Error Covariance Update:      P_k = (1 - K_k) * P_k
"""

import math

class KalmanFilter1D:
    """
    1D Kalman Filter optimized for high-frequency (20 Hz - 100 Hz) telemetry channels.
    Suppresses sensor noise and electrical interference without introducing phase lag.
    """
    def __init__(self, process_noise: float = 0.05, measurement_noise: float = 0.5, initial_value: float = 0.0):
        self.q = process_noise       # Process noise covariance (Q)
        self.r = measurement_noise   # Measurement noise covariance (R)
        self.x = initial_value       # State estimate
        self.p = 1.0                 # Estimation error covariance (P)

    def update(self, measurement: float) -> float:
        """
        Processes a raw noisy measurement z_k and returns the optimal state estimate x_k.
        Handles NaN/Inf safeguards gracefully.
        """
        if math.isnan(measurement) or math.isinf(measurement):
            return self.x  # Safeguard: Return previous estimate on corrupt sensor data

        # 1. Prediction Phase
        self.p = self.p + self.q

        # 2. Kalman Gain
        denominator = self.p + self.r
        if abs(denominator) < 1e-9:
            k = 0.0
        else:
            k = self.p / denominator

        # 3. Measurement Update
        self.x = self.x + k * (measurement - self.x)

        # 4. Error Covariance Update
        self.p = (1.0 - k) * self.p

        return self.x

    def reset(self, value: float = 0.0):
        """Resets state estimate and covariance baseline."""
        self.x = value
        self.p = 1.0


class TelemetryFilterBank:
    """
    Filter bank holding individual 1D Kalman filters for key telemetry metrics.
    """
    def __init__(self):
        self.filters = {
            "Speed": KalmanFilter1D(process_noise=0.1, measurement_noise=0.2, initial_value=0.0),
            "RPM": KalmanFilter1D(process_noise=5.0, measurement_noise=10.0, initial_value=0.0),
            "Engine_Oil_Pressure": KalmanFilter1D(process_noise=0.02, measurement_noise=0.1, initial_value=72.0),
            "Engine_Temp": KalmanFilter1D(process_noise=0.01, measurement_noise=0.05, initial_value=108.0),
            "Tire_Temp_FL": KalmanFilter1D(process_noise=0.05, measurement_noise=0.2, initial_value=92.0),
            "Tire_Temp_FR": KalmanFilter1D(process_noise=0.05, measurement_noise=0.2, initial_value=94.0),
            "Tire_Temp_RL": KalmanFilter1D(process_noise=0.05, measurement_noise=0.2, initial_value=89.0),
            "Tire_Temp_RR": KalmanFilter1D(process_noise=0.05, measurement_noise=0.2, initial_value=91.0),
            "Brake_Temp_FL": KalmanFilter1D(process_noise=0.2, measurement_noise=0.5, initial_value=580.0),
            "Brake_Temp_FR": KalmanFilter1D(process_noise=0.2, measurement_noise=0.5, initial_value=610.0),
            "Brake_Temp_RL": KalmanFilter1D(process_noise=0.2, measurement_noise=0.5, initial_value=540.0),
            "Brake_Temp_RR": KalmanFilter1D(process_noise=0.2, measurement_noise=0.5, initial_value=550.0),
        }

    def filter_packet(self, packet: dict) -> dict:
        """
        Applies Kalman filtering to all registered channels in a telemetry packet.
        """
        filtered_packet = packet.copy()
        for key, kf in self.filters.items():
            if key in packet and isinstance(packet[key], (int, float)):
                filtered_packet[key] = round(kf.update(float(packet[key])), 2)
        return filtered_packet
