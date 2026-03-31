from django.utils.timezone import now
from core.models import NFDResult, SHMHistory

def save_shm_history():
    latest = NFDResult.objects.order_by('-timestamp').first()

    if not latest:
        return

    peak_freq = latest.dominant_frequency
    peak_acc = latest.peak_acceleration
    baseline_freq = 3.49

    residual = peak_freq - baseline_freq if baseline_freq else 0
    raw_stiffness = (peak_freq / baseline_freq) ** 2 * 100 if baseline_freq else 0

# 🔥 CAP AT 100%
    stiffness = min(raw_stiffness, 100)

    if peak_freq <= 10:
        drift = "Within Allowable Limits"
    elif peak_freq <= 15:
        drift = "Moderate Drift"
    else:
        drift = "Excessive Drift"

    condition = "UNSTABLE" if peak_freq > 20 else "STABLE"
    status = latest.status or "Normal"

    last = SHMHistory.objects.order_by('-timestamp').first()

    should_save = False

    if not last:
     should_save = True
    else:
        time_diff = (now() - last.timestamp).total_seconds()
        freq_change = abs(last.peak_frequency - peak_freq)
        acc_change = abs((last.peak_acceleration or 0) - (peak_acc or 0))

     # 🔥 BLOCK DUPLICATES
        if (
            freq_change < 0.001 and
            acc_change < 0.0001
     ):
            should_save = False

         # 🔥 SAVE IF REAL CHANGE
        elif freq_change >= 0.3 or acc_change >= 0.01:
            should_save = True

    # 🔥 TIME FALLBACK (only if slight change)
        elif time_diff >= 300 and (freq_change >= 0.05 or acc_change >= 0.002):
            should_save = True
            should_save = True

    if should_save:
        SHMHistory.objects.create(
            peak_frequency=peak_freq,
            baseline_frequency=baseline_freq,
            residual=residual,
            stiffness=stiffness,
            drift_assessment=drift,
            structural_condition=condition,
            peak_acceleration=peak_acc,
            classification="Ambient",
            status=status
        )