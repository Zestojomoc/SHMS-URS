import os
import sys
from dataclasses import dataclass
from typing import List, Optional, Tuple

# ------------------------------------------------------------
# Django setup
# ------------------------------------------------------------
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(PROJECT_ROOT)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django  # noqa: E402

django.setup()

import numpy as np  # noqa: E402
from obspy import UTCDateTime  # noqa: E402
from obspy.clients.fdsn import Client  # noqa: E402
from scipy.signal import butter, csd, find_peaks, hilbert, sosfiltfilt  # noqa: E402
from core.models import NFDResult, NFDHistory
from django.utils.timezone import now # noqa: E402

# ------------------------------------------------------------
# CONFIG
# ------------------------------------------------------------
FDSN_CLIENT = "RASPISHAKE"

NETWORK = "AM"
STATION = "RA909"
LOCATION = "00"
CHANNEL_PATTERNS = ["EHZ", "ENE", "ENN", "ENZ"]

FETCH_WINDOW_SECONDS = 500   # 8.33 minutes (SAFE AND CONSISTENT TONG STREAM LINE DATA NA TO)
FETCH_DELAY_SECONDS = 1000   # 16.66 minutes delayed fetch

ETABS_BASELINE_FREQ_HZ = 5.671
ETABS_MODES = [
    {"mode": 1, "freq": 5.671},
    {"mode": 2, "freq": 8.210},
    {"mode": 3, "freq": 8.896},
    {"mode": 4, "freq": 9.170},
    {"mode": 5, "freq": 9.200},
    {"mode": 6, "freq": 9.345},
    {"mode": 7, "freq": 9.476},
    {"mode": 8, "freq": 9.532},
    {"mode": 9, "freq": 9.676},
    {"mode": 10, "freq": 9.710},
    {"mode": 11, "freq": 10.066},
    {"mode": 12, "freq": 10.154},
    {"mode": 13, "freq": 10.216},
    {"mode": 14, "freq": 12.157},
    {"mode": 15, "freq": 12.219},
    {"mode": 16, "freq": 12.387},
]

MAX_FFT_POINTS_TO_SAVE = 1000
MIN_VALID_FREQ_HZ = 0.5
FREQUENCY_ALERT_THRESHOLD_PERCENT = 5.0
MAX_REASONABLE_DAMPING = 0.10   # 10%

FDD_NPERSEG = 1024
FDD_OVERLAP_RATIO = 0.5
FDD_BAND_MAX_HZ = 20.0
MIN_CHANNELS_FOR_FDD = 2


# ------------------------------------------------------------
# DATA STRUCTURES
# ------------------------------------------------------------
@dataclass
class AnalysisResult:
    peak_acceleration: float
    dominant_frequency_hz: float               # display in current DF window (FDD)
    damping_ratio: Optional[float]             # display in current damping window (SSI-style)
    peak_amplitude: float                      # from FFT reference graph
    half_power_left_hz: Optional[float]
    half_power_right_hz: Optional[float]
    baseline_frequency_hz: float
    frequency_diff_hz: float
    frequency_diff_percent: float
    status: str
    fft_frequencies: list
    fft_amplitudes: list
    fft_frequency_hz: Optional[float]
    fdd_frequency_hz: Optional[float]
    ssi_frequency_hz: Optional[float]
    channel_names: List[str]
    matched_mode_number: int


# ------------------------------------------------------------
# FETCH LIVE DATA
# ------------------------------------------------------------
def _pick_preferred_traces(stream):
    traces = [tr.copy() for tr in stream if getattr(tr.stats, "npts", 0) > 0]
    if not traces:
        raise ValueError("No waveform traces were returned.")

    # keep only the most common sampling rate
    sr_counts = {}
    for tr in traces:
        sr = float(tr.stats.sampling_rate)
        sr_counts[sr] = sr_counts.get(sr, 0) + 1
    preferred_sr = max(sr_counts, key=sr_counts.get)
    traces = [tr for tr in traces if float(tr.stats.sampling_rate) == preferred_sr]

    # keep one best trace per channel code
    by_channel = {}
    for tr in traces:
        ch = tr.stats.channel
        old = by_channel.get(ch)
        if old is None or tr.stats.npts > old.stats.npts:
            by_channel[ch] = tr
    traces = list(by_channel.values())

    # prioritize geophone-like orthogonal channels when available
    suffix_priority = {"E": 0, "N": 1, "Z": 2, "1": 3, "2": 4, "X": 5, "Y": 6}
    traces.sort(key=lambda tr: (suffix_priority.get(tr.stats.channel[-1], 99), tr.stats.channel))

    return traces


def _trim_and_stack_traces(traces):
    common_start = max(tr.stats.starttime for tr in traces)
    common_end = min(tr.stats.endtime for tr in traces)
    if common_end <= common_start:
        raise ValueError("Selected channels do not overlap in time.")

    aligned = []
    for tr in traces:
        tr2 = tr.copy()
        tr2.trim(common_start, common_end, nearest_sample=False)
        aligned.append(tr2)

    min_len = min(len(tr.data) for tr in aligned)
    if min_len < 256:
        raise ValueError("Not enough overlapping samples across channels.")

    data = np.vstack([
        np.asarray(tr.data[:min_len], dtype=np.float64)
        for tr in aligned
    ])
    channel_names = [tr.stats.channel for tr in aligned]
    fs = float(aligned[0].stats.sampling_rate)
    return data, fs, channel_names


def fetch_live_waveforms():
    client = Client(FDSN_CLIENT)

    end = UTCDateTime() - FETCH_DELAY_SECONDS
    start = end - FETCH_WINDOW_SECONDS

    print(f"Fetching waveform window from {start} to {end}")

    try:
        # ✅ Correct multi-channel request
        stream = client.get_waveforms(
            NETWORK,
            STATION,
            LOCATION,
            ",".join(CHANNEL_PATTERNS),
            start,
            end
        )

        # ✅ Debug print
        print("========== RAW FETCHED TRACES ==========")
        for tr in stream:
            print(f"Channel: {tr.stats.channel}, Samples: {len(tr.data)}, Sampling rate: {tr.stats.sampling_rate}")
        print("========================================")

        # ✅ Clean and prioritize traces
        traces = _pick_preferred_traces(stream)

        if not traces:
            raise ValueError("No valid traces after filtering.")

        # ✅ Select up to 3 channels for FDD/SSI
        selected = traces[:3]

        # ✅ Align and stack
        data, fs, channel_names = _trim_and_stack_traces(selected)

        return data, fs, channel_names


    except Exception as exc:
        raise ValueError(f"Fetch failed: {exc}")


# ------------------------------------------------------------
# SIGNAL HELPERS
# ------------------------------------------------------------
def preprocess_signal(samples: np.ndarray) -> np.ndarray:
    x = np.asarray(samples, dtype=np.float64)
    if x.size < 16:
        raise ValueError("Signal too short for analysis.")

    x = x - np.mean(x)
    n = np.arange(x.size, dtype=np.float64)
    coeff = np.polyfit(n, x, 1)
    trend = coeff[0] * n + coeff[1]
    x = x - trend
    x = x * np.hanning(x.size)
    return x



def preprocess_multichannel(data: np.ndarray) -> np.ndarray:
    return np.vstack([preprocess_signal(ch) for ch in data])



def compute_fft(samples: np.ndarray, sampling_rate: float) -> Tuple[np.ndarray, np.ndarray]:
    fft_complex = np.fft.rfft(samples)
    freqs = np.fft.rfftfreq(samples.size, d=1.0 / sampling_rate)
    amps = np.abs(fft_complex)
    return freqs, amps



def remove_near_zero_freqs(freqs: np.ndarray, amps: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    mask = freqs >= MIN_VALID_FREQ_HZ
    freqs2 = freqs[mask]
    amps2 = amps[mask]
    if freqs2.size == 0:
        raise ValueError("No frequency bins remained after filtering low frequencies.")
    return freqs2, amps2



def reduce_fft_for_storage(freqs: np.ndarray, amps: np.ndarray, max_points: int) -> Tuple[np.ndarray, np.ndarray]:
    if freqs.size <= max_points:
        return freqs, amps
    idx = np.linspace(0, freqs.size - 1, max_points, dtype=int)
    return freqs[idx], amps[idx]



def find_dominant_peak(freqs: np.ndarray, amps: np.ndarray) -> Tuple[int, float, float]:
    if len(freqs) < 3:
        idx = int(np.argmax(amps))
        return idx, float(freqs[idx]), float(amps[idx])

    peak_indices, _ = find_peaks(amps)
    if peak_indices.size == 0:
        idx = int(np.argmax(amps))
        return idx, float(freqs[idx]), float(amps[idx])

    best_idx = int(peak_indices[np.argmax(amps[peak_indices])])
    return best_idx, float(freqs[best_idx]), float(amps[best_idx])



def choose_reference_channel(data: np.ndarray, channel_names: List[str]) -> int:
    for preferred in ("EHZ", "ENE", "ENN", "ENZ"):
        if preferred in channel_names:
            return channel_names.index(preferred)
    rms = np.sqrt(np.mean(np.square(data), axis=1))
    return int(np.argmax(rms))


# ------------------------------------------------------------
# FDD
# ------------------------------------------------------------
def compute_fdd_frequency(data: np.ndarray, fs: float) -> Tuple[Optional[float], Optional[np.ndarray], Optional[np.ndarray], Optional[np.ndarray]]:
    n_channels, n_samples = data.shape
    if n_channels < MIN_CHANNELS_FOR_FDD:
        return None, None, None, None

    nperseg = min(FDD_NPERSEG, n_samples)
    if nperseg < 256:
        return None, None, None, None
    noverlap = int(nperseg * FDD_OVERLAP_RATIO)

    freqs = None
    psd_matrix = None

    for i in range(n_channels):
        for j in range(n_channels):
            f, pxy = csd(data[i], data[j], fs=fs, nperseg=nperseg, noverlap=noverlap, scaling="density")
            if freqs is None:
                freqs = f
                psd_matrix = np.zeros((n_channels, n_channels, len(freqs)), dtype=np.complex128)
            psd_matrix[i, j, :] = pxy

    mask = (freqs >= MIN_VALID_FREQ_HZ) & (freqs <= min(FDD_BAND_MAX_HZ, fs / 2.0))
    freqs = freqs[mask]
    if freqs.size == 0:
        return None, None, None, None

    psd_matrix = psd_matrix[:, :, mask]
    singular_values = np.zeros((len(freqs), n_channels), dtype=np.float64)
    mode_shapes = np.zeros((len(freqs), n_channels), dtype=np.complex128)

    for k in range(len(freqs)):
        u, s, _ = np.linalg.svd(psd_matrix[:, :, k], hermitian=False)
        singular_values[k, : len(s)] = s.real
        mode_shapes[k, :] = u[:, 0]

    first_sv = singular_values[:, 0]
    peak_idx, dominant_freq_hz, _ = find_dominant_peak(freqs, first_sv)
    dominant_mode_shape = mode_shapes[peak_idx, :]

    return float(dominant_freq_hz), freqs, first_sv, dominant_mode_shape


# ------------------------------------------------------------
# SSI-STYLE DAMPING ESTIMATE FOR UI DAMPING WINDOW
# ------------------------------------------------------------
def bandpass_filter(signal: np.ndarray, fs: float, center_hz: float) -> np.ndarray:
    low = max(0.1, center_hz * 0.80)
    high = min(fs / 2.0 - 0.1, center_hz * 1.20)

    if high <= low:
        low = max(0.1, center_hz - 0.4)
        high = min(fs / 2.0 - 0.1, center_hz + 0.4)

    if high <= low:
        return signal

    sos = butter(4, [low, high], btype="bandpass", fs=fs, output="sos")
    return sosfiltfilt(sos, signal)



def compute_log_decrement_damping(envelope_peaks: np.ndarray) -> Optional[float]:
    if envelope_peaks.size < 4:
        return None

    valid = envelope_peaks[envelope_peaks > 0]
    if valid.size < 4:
        return None

    deltas = np.log(valid[:-1] / valid[1:])
    deltas = deltas[np.isfinite(deltas) & (deltas > 0)]
    if deltas.size == 0:
        return None

    delta = float(np.median(deltas))
    zeta = delta / np.sqrt((2.0 * np.pi) ** 2 + delta ** 2)

    if zeta <= 0 or zeta > MAX_REASONABLE_DAMPING:
        return None
    return float(zeta)



def compute_ssi_damping(data: np.ndarray, fs: float, target_freq_hz: float, mode_shape: Optional[np.ndarray]) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    if target_freq_hz is None or target_freq_hz <= 0:
        return None, None, None

    if mode_shape is not None and mode_shape.size == data.shape[0]:
        weights = np.real(mode_shape)
        if np.allclose(weights, 0):
            response = data[0]
        else:
            weights = weights / (np.linalg.norm(weights) + 1e-12)
            response = np.dot(weights, data)
    else:
        response = data[0]

    filtered = bandpass_filter(response, fs, target_freq_hz)
    envelope = np.abs(hilbert(filtered))

    min_distance = max(1, int(fs / max(target_freq_hz, 0.1)))
    prominence = max(np.std(envelope) * 0.10, np.max(envelope) * 0.02)
    peaks, _ = find_peaks(envelope, distance=min_distance, prominence=prominence)

    if peaks.size < 4:
        return None, None, None

    # use early peaks only so damping reflects the clearer decay part
    peak_vals = envelope[peaks[:10]]
    zeta = compute_log_decrement_damping(peak_vals)
    if zeta is None:
        return None, None, None

    # keep left/right placeholders for compatibility with your summary printout
    bandwidth = 2.0 * zeta * target_freq_hz
    f1 = max(MIN_VALID_FREQ_HZ, target_freq_hz - bandwidth / 2.0)
    f2 = target_freq_hz + bandwidth / 2.0
    return float(zeta), float(f1), float(f2)


# ------------------------------------------------------------
# FFT HALF-POWER FALLBACK (only when SSI-style estimate fails)
# ------------------------------------------------------------
def interpolate_crossing(f_a, a_a, f_b, a_b, target_amp):
    if a_b == a_a:
        return float(f_a)
    ratio = (target_amp - a_a) / (a_b - a_a)
    return float(f_a + ratio * (f_b - f_a))



def compute_half_power_damping(freqs: np.ndarray, amps: np.ndarray, peak_idx: int) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    fn = float(freqs[peak_idx])
    a_peak = float(amps[peak_idx])
    if fn <= 0 or a_peak <= 0:
        return None, None, None

    a_half = a_peak / np.sqrt(2.0)
    f1 = None
    f2 = None

    for i in range(peak_idx, 0, -1):
        if amps[i - 1] <= a_half <= amps[i] or amps[i - 1] >= a_half >= amps[i]:
            f1 = interpolate_crossing(freqs[i - 1], amps[i - 1], freqs[i], amps[i], a_half)
            break

    for i in range(peak_idx, len(amps) - 1):
        if amps[i] >= a_half >= amps[i + 1] or amps[i] <= a_half <= amps[i + 1]:
            f2 = interpolate_crossing(freqs[i], amps[i], freqs[i + 1], amps[i + 1], a_half)
            break

    if f1 is None or f2 is None or f2 <= f1:
        return None, f1, f2

    bandwidth = f2 - f1
    zeta = bandwidth / (2.0 * fn)
    if zeta <= 0 or zeta > MAX_REASONABLE_DAMPING:
        return None, f1, f2

    return float(zeta), float(f1), float(f2)


# ------------------------------------------------------------
# COMPARISON
# ------------------------------------------------------------
def find_closest_mode(measured_freq_hz: float):
    closest = None
    min_diff = float("inf")

    for mode in ETABS_MODES:
        diff = abs(measured_freq_hz - mode["freq"])
        if diff < min_diff:
            min_diff = diff
            closest = mode

    return closest


def compare_with_baseline(measured_freq_hz: float) -> Tuple[float, float, float, int, str]:
    closest_mode = find_closest_mode(measured_freq_hz)

    baseline_freq_hz = float(closest_mode["freq"])
    matched_mode_number = int(closest_mode["mode"])

    diff_hz = measured_freq_hz - baseline_freq_hz
    diff_pct = (diff_hz / baseline_freq_hz) * 100.0 if baseline_freq_hz else 0.0

    if diff_pct > 100:
        diff_pct = 100.0
    elif diff_pct < -100:
        diff_pct = -100.0

    abs_pct = abs(diff_pct)
    if abs_pct <= FREQUENCY_ALERT_THRESHOLD_PERCENT:
        status = "Normal"
    elif abs_pct <= 10.0:
        status = "Watch"
    else:
        status = "Alert"

    return float(baseline_freq_hz), float(diff_hz), float(diff_pct), matched_mode_number, status


# ------------------------------------------------------------
# MAIN ANALYSIS
# ------------------------------------------------------------
def analyze_waveform(data: np.ndarray, sampling_rate: float, channel_names: List[str]) -> AnalysisResult:
    data_preprocessed = preprocess_multichannel(data)

    ref_idx = choose_reference_channel(data_preprocessed, channel_names)
    ref_samples = data_preprocessed[ref_idx]

    # ================= SHM PEAK ACCELERATION =================
    magnitude = np.sqrt(np.sum(data**2, axis=0))
    magnitude_g = magnitude / 1_000_000
    peak_acc = float(np.max(magnitude_g))
# ========================================================

    # FFT reference only
    fft_freqs, fft_amps = compute_fft(ref_samples, sampling_rate)
    fft_freqs, fft_amps = remove_near_zero_freqs(fft_freqs, fft_amps)
    fft_peak_idx, fft_peak_freq_hz, peak_amplitude = find_dominant_peak(fft_freqs, fft_amps)

    # FDD main result
    fdd_freq_hz, fdd_freqs, fdd_sv, mode_shape = compute_fdd_frequency(data_preprocessed, sampling_rate)

    if fdd_freq_hz is None:
        dominant_freq_hz = fft_peak_freq_hz
        graph_freqs = fft_freqs
        graph_amps = fft_amps
    else:
        dominant_freq_hz = fdd_freq_hz
        graph_freqs = fdd_freqs
        graph_amps = fdd_sv

    damping_ratio, f1, f2 = compute_ssi_damping(
        data_preprocessed,
        sampling_rate,
        dominant_freq_hz,
        mode_shape,
    )

    if damping_ratio is None:
        damping_ratio, f1, f2 = compute_half_power_damping(fft_freqs, fft_amps, fft_peak_idx)

    baseline_freq_hz, diff_hz, diff_pct, matched_mode_number, status = compare_with_baseline(dominant_freq_hz)

    # store graph data (now FDD when available)
    freqs_small, amps_small = reduce_fft_for_storage(graph_freqs, graph_amps, MAX_FFT_POINTS_TO_SAVE)

    return AnalysisResult(
        peak_acceleration=peak_acc,
        
        dominant_frequency_hz=float(dominant_freq_hz),
        damping_ratio=damping_ratio,
        peak_amplitude=float(peak_amplitude),
        half_power_left_hz=f1,
        half_power_right_hz=f2,
        baseline_frequency_hz=baseline_freq_hz,
        frequency_diff_hz=diff_hz,
        frequency_diff_percent=diff_pct,
        status=status,
        fft_frequencies=freqs_small.tolist(),
        fft_amplitudes=amps_small.tolist(),
        fft_frequency_hz=float(fft_peak_freq_hz),
        fdd_frequency_hz=float(fdd_freq_hz) if fdd_freq_hz is not None else None,
        ssi_frequency_hz=float(dominant_freq_hz),
        channel_names=channel_names,
        matched_mode_number=matched_mode_number,
    )


def save_result_to_database(result: AnalysisResult) -> NFDResult:

    # ✅ Save main result (existing)
    db_result = NFDResult.objects.create(
        dominant_frequency=result.dominant_frequency_hz,
        damping_ratio=result.damping_ratio,
        etabs_frequency=result.baseline_frequency_hz,
        frequency_difference=result.frequency_diff_hz,
        frequency_difference_percent=result.frequency_diff_percent,
        status=result.status,
        fft_frequencies=result.fft_frequencies,
        fft_amplitudes=result.fft_amplitudes,

        peak_acceleration=result.peak_acceleration,
    )

    # ================= SAVE TO HISTORY (PROCESSOR BASED) =================
    last_record = NFDHistory.objects.order_by('-timestamp').first()

    should_save = False

    if not last_record:
        should_save = True
    else:
        time_diff = (now() - last_record.timestamp).total_seconds()
        freq_change = abs(last_record.dominant_frequency - result.dominant_frequency_hz)
        status_change = last_record.status != result.status

    # ✅ MUST BE INSIDE ELSE
        if (
          time_diff >= 60
          or freq_change >= 0.5
          or status_change
    ):
          should_save = True

    if should_save:

        # 🛑 Prevent duplicate values
        if last_record:
            same_freq = abs(last_record.dominant_frequency - result.dominant_frequency_hz) < 0.01
            if same_freq:
                return db_result

        NFDHistory.objects.create(
            dominant_frequency=result.dominant_frequency_hz,
            damping_ratio=(result.damping_ratio or 0) * 100,
            matched_mode=f"Mode {result.matched_mode_number}",
            etabs_frequency=result.baseline_frequency_hz,
            frequency_difference_percent=result.frequency_diff_percent or 0,
            classification="Ambient",
            status=result.status if result.status else "Normal",
            
            peak_acceleration=result.peak_acceleration,
            
        )

    return db_result



def print_summary(result: AnalysisResult) -> None:
    print("\n================ NFD ANALYSIS RESULT ================")
    print(f"Channels Used           : {', '.join(result.channel_names)}")
    print(f"FFT Peak (reference)    : {result.fft_frequency_hz:.4f} Hz" if result.fft_frequency_hz is not None else "FFT Peak (reference)    : N/A")
    print(f"Displayed DF (FDD)      : {result.dominant_frequency_hz:.4f} Hz")
    print(f"FDD Frequency           : {result.fdd_frequency_hz:.4f} Hz" if result.fdd_frequency_hz is not None else "FDD Frequency           : N/A")
    print(f"Peak Amplitude          : {result.peak_amplitude:.4f}")

    if result.damping_ratio is not None:
        print(f"Displayed Damping       : {result.damping_ratio:.6f} ({result.damping_ratio * 100:.3f}%)")
        if result.half_power_left_hz is not None and result.half_power_right_hz is not None:
            print(f"Bandwidth Left          : {result.half_power_left_hz:.4f} Hz")
            print(f"Bandwidth Right         : {result.half_power_right_hz:.4f} Hz")
    else:
        print("Displayed Damping       : Could not be computed reliably")

    print(f"ETABS Baseline          : {result.baseline_frequency_hz:.4f} Hz")
    print(f"Matched Mode            : Mode {result.matched_mode_number}")
    print(f"Frequency Difference    : {result.frequency_diff_hz:.4f} Hz")
    print(f"Difference Percent      : {result.frequency_diff_percent:.2f}%")
    print(f"Status                  : {result.status}")
    print("=====================================================\n")

# goods na goods na

def main() -> None:
    print("Starting NFD processor...")

    data, sampling_rate, channel_names = fetch_live_waveforms()

    print(f"Sampling rate           : {sampling_rate} Hz")
    print(f"Channels fetched        : {', '.join(channel_names)}")
    print(f"Samples per channel     : {data.shape[1]}")
    print(f"Window length           : {FETCH_WINDOW_SECONDS} seconds")
    print(f"Minimum valid freq      : {MIN_VALID_FREQ_HZ} Hz")

    result = analyze_waveform(data, sampling_rate, channel_names)
    print_summary(result)

    db_result = save_result_to_database(result)
    print(f"Saved to database       : ID={db_result.id}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"\nNFD processor failed: {exc}")
        raise
