from django.db import models
from django.utils import timezone
from django.core.validators import MinValueValidator, MaxValueValidator


# Base class for common fields
class TimestampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


# ==================== SHM Models ====================
class Sensor(TimestampedModel):
    """Raspberry Shake or other sensors for vibration monitoring"""
    SENSOR_TYPES = [
        ('raspberry_shake', 'Raspberry Shake 4D'),
        ('accelerometer', 'Accelerometer'),
        ('seismometer', 'Seismometer'),
        ('other', 'Other'),
    ]
    
    name = models.CharField(max_length=255)
    sensor_type = models.CharField(max_length=50, choices=SENSOR_TYPES)
    location = models.CharField(max_length=255, help_text="Building location/floor")
    is_active = models.BooleanField(default=True)
    installation_date = models.DateTimeField()
    last_reading = models.DateTimeField(null=True, blank=True)
    calibration_factor = models.FloatField(default=1.0)

    def __str__(self):
        return f"{self.name} ({self.location})"


class SensorReading(TimestampedModel):
    """Real-time vibration data from sensors"""
    sensor = models.ForeignKey(Sensor, on_delete=models.CASCADE, related_name='readings')
    timestamp = models.DateTimeField(db_index=True)
    
    # Acceleration components (e.g., in g or m/s²)
    acceleration_x = models.FloatField()
    acceleration_y = models.FloatField()
    acceleration_z = models.FloatField()
    
    # Derived metrics
    magnitude = models.FloatField()  # sqrt(x² + y² + z²)
    
    def __str__(self):
        return f"{self.sensor.name} - {self.timestamp}"


class Event(TimestampedModel):
    """Detected seismic or human-induced events"""
    EVENT_TYPES = [
        ('earthquake', 'Earthquake'),
        ('blast', 'Blast/Explosion'),
        ('footfall', 'Footfall/Impact'),
        ('wind', 'Wind-Induced'),
        ('traffic', 'Traffic-Induced'),
        ('other', 'Other'),
    ]
    
    SEVERITY_LEVELS = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('critical', 'Critical'),
    ]
    
    sensor = models.ForeignKey(Sensor, on_delete=models.CASCADE, related_name='events')
    event_type = models.CharField(max_length=50, choices=EVENT_TYPES)
    severity = models.CharField(max_length=20, choices=SEVERITY_LEVELS)
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    peak_acceleration = models.FloatField(help_text="Peak acceleration magnitude during event")
    description = models.TextField(blank=True)
    
    def __str__(self):
        return f"{self.event_type.upper()} - {self.start_time}"


class SHMTrend(TimestampedModel):
    """Long-term behavioral trends for SHM"""
    sensor = models.ForeignKey(Sensor, on_delete=models.CASCADE, related_name='trends')
    date = models.DateField(unique_for_month=True)
    
    avg_acceleration = models.FloatField()
    max_acceleration = models.FloatField()
    min_acceleration = models.FloatField()
    event_count = models.IntegerField(default=0)
    
    notes = models.TextField(blank=True)

    class Meta:
        unique_together = ('sensor', 'date')
        ordering = ['-date']

    def __str__(self):
        return f"{self.sensor.name} - {self.date}"


# ==================== NFD Models ====================
class ETABSBaseline(TimestampedModel):
    """ETABS model baseline for comparison"""
    name = models.CharField(max_length=255, help_text="e.g., Building Model v1.0")
    description = models.TextField(blank=True)
    
    is_active = models.BooleanField(default=True)
    uploaded_date = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class NaturalFrequency(TimestampedModel):
    """Fundamental natural frequencies identified via FFT analysis"""
    baseline = models.ForeignKey(
        ETABSBaseline, on_delete=models.CASCADE, related_name='frequencies', null=True, blank=True
    )
    
    mode_number = models.IntegerField(help_text="e.g., 1st mode, 2nd mode")
    frequency_hz = models.FloatField(help_text="Frequency in Hertz")
    frequency_source = models.CharField(
        max_length=50,
        choices=[('analytical', 'Analytical (ETABS)'), ('experimental', 'Experimental (FFT)')],
        default='experimental'
    )
    
    damping_ratio = models.FloatField(
        help_text="Damping ratio (0-1 or percentage)",
        validators=[MinValueValidator(0), MaxValueValidator(1)]
    )
    
    last_measured = models.DateTimeField(auto_now=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['mode_number']

    def __str__(self):
        return f"Mode {self.mode_number}: {self.frequency_hz} Hz"


class FFTAnalysis(TimestampedModel):
    """FFT analysis results from sensor data"""
    sensor = models.ForeignKey(Sensor, on_delete=models.CASCADE, related_name='fft_analyses')
    analysis_date = models.DateTimeField()
    
    frequency_range_min = models.FloatField(help_text="Min frequency analyzed (Hz)")
    frequency_range_max = models.FloatField(help_text="Max frequency analyzed (Hz)")
    
    primary_frequency = models.FloatField(help_text="Dominant frequency found (Hz)")
    primary_amplitude = models.FloatField()
    
    analysis_notes = models.TextField(blank=True)

    def __str__(self):
        return f"FFT - {self.sensor.name} ({self.analysis_date})"


class FrequencyComparison(TimestampedModel):
    """Live vs Baseline frequency comparison"""
    baseline_frequency = models.ForeignKey(NaturalFrequency, on_delete=models.CASCADE, related_name='comparisons')
    analysis = models.ForeignKey(FFTAnalysis, on_delete=models.CASCADE)
    
    frequency_diff = models.FloatField(help_text="Difference in Hz (can be negative)")
    frequency_diff_percent = models.FloatField(help_text="Percentage difference")
    
    status = models.CharField(
        max_length=50,
        choices=[('normal', 'Normal'), ('degraded', 'Degraded'), ('alert', 'Alert')],
        default='normal'
    )
    
    assessment = models.TextField(blank=True)

    def __str__(self):
        return f"Comparison - {self.status.upper()}"


# ==================== Drift Monitoring Models ====================
class FloorLevel(models.Model):
    """Define floor levels in the building"""
    floor_number = models.IntegerField(help_text="e.g., 1, 2, 3 or -1 for basement")
    floor_name = models.CharField(max_length=100, help_text="e.g., 'Ground Floor', 'Level 3'")
    height_above_ground = models.FloatField(help_text="Height in meters above ground")

    class Meta:
        ordering = ['floor_number']

    def __str__(self):
        return f"Floor {self.floor_number}: {self.floor_name}"


class DriftMeasurement(TimestampedModel):
    """Inter-story displacement measurements"""
    lower_floor = models.ForeignKey(FloorLevel, on_delete=models.CASCADE, related_name='drift_lower')
    upper_floor = models.ForeignKey(FloorLevel, on_delete=models.CASCADE, related_name='drift_upper')
    
    measurement_time = models.DateTimeField(db_index=True)
    
    # Displacement in millimeters or inches
    displacement_x = models.FloatField()  # Lateral drift
    displacement_y = models.FloatField()  # Perpendicular lateral drift
    
    # Derived metrics
    total_displacement = models.FloatField()  # sqrt(x² + y²)
    inter_story_drift_ratio = models.FloatField(help_text="Displacement / Story Height")
    
    event_related = models.ForeignKey(
        Event, on_delete=models.SET_NULL, null=True, blank=True, 
        help_text="Link to seismic/event trigger if applicable"
    )

    def __str__(self):
        return f"Drift {self.lower_floor.floor_name} -> {self.upper_floor.floor_name} ({self.measurement_time})"


class DriftSafetyThreshold(models.Model):
    """Allowable drift limits per building code (e.g., NSCP 2010)"""
    lower_floor = models.ForeignKey(FloorLevel, on_delete=models.CASCADE, related_name='safety_thresholds')
    upper_floor = models.ForeignKey(FloorLevel, on_delete=models.CASCADE, related_name='safety_thresholds_upper')
    
    max_inter_story_drift_ratio = models.FloatField(
        help_text="Maximum allowable drift ratio (e.g., 0.02 for 2%)",
        validators=[MinValueValidator(0), MaxValueValidator(1)]
    )
    
    building_code = models.CharField(
        max_length=100,
        default='NSCP 2010',
        help_text="e.g., NSCP 2010, IBC 2021"
    )
    
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ('lower_floor', 'upper_floor')

    def __str__(self):
        return f"{self.lower_floor.floor_name} -> {self.upper_floor.floor_name} (max: {self.max_inter_story_drift_ratio})"


class DriftAlert(TimestampedModel):
    """Alerts when drift exceeds safe limits"""
    ALERT_STATUS = [
        ('warning', 'Warning'),
        ('critical', 'Critical'),
        ('cleared', 'Cleared'),
    ]
    
    measurement = models.ForeignKey(DriftMeasurement, on_delete=models.CASCADE, related_name='alerts')
    threshold = models.ForeignKey(DriftSafetyThreshold, on_delete=models.CASCADE)
    
    alert_status = models.CharField(max_length=20, choices=ALERT_STATUS, default='warning')
    exceeded_by_percent = models.FloatField(help_text="How much threshold was exceeded (%)")
    alert_triggered_time = models.DateTimeField(auto_now_add=True)
    resolved_time = models.DateTimeField(null=True, blank=True)
    
    action_taken = models.TextField(blank=True)

    def __str__(self):
        return f"Alert - {self.alert_status.upper()}"


# ==================== System Configuration ====================
class SystemSettings(models.Model):
    """Global system configuration"""
    dashboard_name = models.CharField(
        max_length=50,
        choices=[('shm', 'SHM'), ('nfd', 'NFD'), ('drift', 'Drift')],
        unique=True
    )
    
    sampling_rate = models.IntegerField(help_text="Hz", default=50)
    measurement_units = models.CharField(
        max_length=50,
        choices=[('metric', 'Metric (m, m/s², Hz)'), ('imperial', 'Imperial (ft, g, Hz)')],
        default='metric'
    )
    
    alert_email = models.CharField(max_length=255, blank=True, help_text="Send alerts to this email")
    maintenance_mode = models.BooleanField(default=False)
    
    last_calibrated = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name_plural = "System Settings"

    def __str__(self):
        return f"Settings - {self.get_dashboard_name_display()}"


class Alert(TimestampedModel):
    """Generic system alerts and thresholds"""
    ALERT_TYPES = [
        ('sensor_offline', 'Sensor Offline'),
        ('high_acceleration', 'High Acceleration'),
        ('frequency_shift', 'Frequency Shift Detected'),
        ('drift_exceeded', 'Drift Threshold Exceeded'),
        ('system_error', 'System Error'),
    ]
    
    alert_type = models.CharField(max_length=50, choices=ALERT_TYPES)
    is_active = models.BooleanField(default=True)
    
    threshold_value = models.FloatField(null=True, blank=True)
    description = models.TextField()
    
    def __str__(self):
        return f"{self.alert_type} - {self.description[:50]}"
    
    # ================= NFD Results =================

class NFDResult(models.Model):

    timestamp = models.DateTimeField(auto_now_add=True)

    dominant_frequency = models.FloatField()
    damping_ratio = models.FloatField(null=True, blank=True)

    # ETABS comparison
    peak_acceleration = models.FloatField(null=True, blank=True)
    etabs_frequency = models.FloatField(default=5.671)
    frequency_difference = models.FloatField(null=True, blank=True)
    frequency_difference_percent = models.FloatField(null=True, blank=True)

    status = models.CharField(max_length=20, default="Normal")

    # FFT data for chart
    fft_frequencies = models.JSONField(default=list)
    fft_amplitudes = models.JSONField(default=list)

    def __str__(self):
        return f"NFD Result {self.id} - {self.dominant_frequency:.3f} Hz"


# last DELETED!

class NFDHistory(models.Model):
    timestamp = models.DateTimeField(auto_now_add=True)

    # Core Results
    dominant_frequency = models.FloatField()
    damping_ratio = models.FloatField()

    # Baseline Comparison
    matched_mode = models.CharField(max_length=50, null=True, blank=True)
    etabs_frequency = models.FloatField(null=True, blank=True)
    frequency_difference_percent = models.FloatField(null=True, blank=True)
    

    # Classification & Status
    classification = models.CharField(max_length=50, default="Ambient")
    status = models.CharField(max_length=20, default="Normal")
    
    peak_acceleration = models.FloatField(null=True, blank=True)

    def __str__(self):
        return f"{self.timestamp} - {self.dominant_frequency} Hz"
    
    
class SHMHistory(models.Model):
    timestamp = models.DateTimeField(auto_now_add=True)

    # Core SHM metrics
    peak_frequency = models.FloatField()
    baseline_frequency = models.FloatField(null=True, blank=True)

    residual = models.FloatField(null=True, blank=True)
    stiffness = models.FloatField(null=True, blank=True)

    drift_assessment = models.CharField(max_length=50)
    structural_condition = models.CharField(max_length=50)

    peak_acceleration = models.FloatField(null=True, blank=True)

    classification = models.CharField(max_length=50, default="Ambient")
    status = models.CharField(max_length=20, default="Normal")

    def __str__(self):
        return f"{self.timestamp} | {self.peak_frequency} Hz"
    

class DriftHistory(models.Model):
    timestamp = models.DateTimeField(auto_now_add=True)

    # ===== FLOOR 1 =====
    f1_mdr = models.FloatField(default=0)
    f1_drift_x = models.FloatField(default=0)
    f1_drift_y = models.FloatField(default=0)
    f1_acc_x = models.FloatField(default=0)
    f1_acc_y = models.FloatField(default=0)
    f1_base_x = models.FloatField(default=0)
    f1_base_y = models.FloatField(default=0)
    f1_diff = models.FloatField(default=0)

    # ===== FLOOR 2 =====
    f2_mdr = models.FloatField(default=0)
    f2_drift_x = models.FloatField(default=0)
    f2_drift_y = models.FloatField(default=0)
    f2_acc_x = models.FloatField(default=0)
    f2_acc_y = models.FloatField(default=0)
    f2_base_x = models.FloatField(default=0)
    f2_base_y = models.FloatField(default=0)
    f2_diff = models.FloatField(default=0)

    # ===== FLOOR 3 =====
    f3_mdr = models.FloatField(default=0)
    f3_drift_x = models.FloatField(default=0)
    f3_drift_y = models.FloatField(default=0)
    f3_acc_x = models.FloatField(default=0)
    f3_acc_y = models.FloatField(default=0)
    f3_base_x = models.FloatField(default=0)
    f3_base_y = models.FloatField(default=0)
    f3_diff = models.FloatField(default=0)

    overall_status = models.CharField(max_length=20, default="Normal")

    def __str__(self):
        return f"{self.timestamp} | F1:{self.f1_mdr:.4f} F2:{self.f2_mdr:.4f} F3:{self.f3_mdr:.4f}"
