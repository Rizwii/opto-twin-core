import numpy as np

class PhotodetectorPhysicsEngine:
    """
    Optoelectronic Behavioral Physics Engine.
    Models temperature-dependent dark current drift, dynamic responsivity,
    saturation boundaries, SNR, and health index.
    """
    def __init__(self, baseline_dark_current_a=1e-9, ref_temp_k=298.15):
        self.I_d0 = baseline_dark_current_a  # Baseline dark current (1 nA at 25°C)
        self.T0 = ref_temp_k                # Reference temperature (298.15 K)
        self.max_current_threshold_a = 1e-2 # Physical saturation limit (10 mA)

    def compute_dark_current(self, temp_c: float) -> float:
        """Calculates temperature-dependent dark current drift (Id)."""
        temp_k = temp_c + 273.15
        if temp_k < 0:
            raise ValueError("Temperature in Kelvin cannot be below absolute zero.")
        # Exponential thermal dark current scaling
        return float(self.I_d0 * np.exp(0.07 * (temp_k - self.T0)))

    def compute_responsivity(self, bias_v: float, temp_c: float) -> float:
        """Calculates dynamic photodetector responsivity R (A/W)."""
        base_responsivity = 0.85  # Nominal responsivity for Si/InGaAs photodiode
        voltage_gain = 1.0 + (0.015 * bias_v)
        thermal_degradation = 1.0 - (0.0008 * (temp_c - 25.0))
        return float(base_responsivity * voltage_gain * thermal_degradation)

    def evaluate_state(self, temp_c: float, bias_v: float, optical_power_w: float) -> dict:
        """Computes complete Digital Twin state from telemetry inputs."""
        if optical_power_w < 0:
            raise ValueError("Optical power cannot be negative.")

        i_dark = self.compute_dark_current(temp_c)
        responsivity = self.compute_responsivity(bias_v, temp_c)
        i_photo = optical_power_w * responsivity
        total_current = i_photo + i_dark

        # Saturation check
        is_saturated = total_current >= self.max_current_threshold_a

        # Real-time Signal-to-Noise Ratio (SNR) in dB (1 MHz Bandwidth)
        shot_noise_sq = 2 * 1.602e-19 * (i_photo + i_dark) * 1e6
        snr_db = float(10 * np.log10((i_photo**2) / (shot_noise_sq + 1e-18))) if i_photo > 0 else 0.0

        # Health Index calculation (%) based on dark current drift relative to baseline
        health_index_pct = float(max(0.0, min(100.0, 100.0 - (i_dark / 1e-8) * 15.0)))

        return {
            "dark_current_a": i_dark,
            "responsivity_a_w": responsivity,
            "photocurrent_a": i_photo,
            "total_current_a": total_current,
            "snr_db": snr_db,
            "is_saturated": is_saturated,
            "health_index_pct": health_index_pct
        }