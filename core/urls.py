from django.urls import path
from . import views
from .views import latest_nfd_result

urlpatterns = [
    path('', views.landing, name='landing'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('public/nfd/', views.public_nfd, name='public_nfd'),
    path('about/', views.public_about, name='public_about'),
    path('contact/', views.public_contact, name='public_contact'),
    
    path('public/shm/', views.public_shm, name='public_shm'),
    path('public/drift/', views.public_drift, name='public_drift'),
    
    path("api/fft-spectrum/", views.fft_spectrum, name="fft_spectrum"),
    path("api/latest-nfd/", latest_nfd_result),
    path("api/nfd/latest/", views.latest_nfd_result),
    path("api/latest-nfd-waveforms/", views.latest_nfd_waveforms, name="latest_nfd_waveforms"),
    
    

    # Dashboards
    path('dashboard/shm/', views.dashboard_shm, name='dashboard_shm'),
    path('dashboard/nfd/', views.dashboard_nfd, name='dashboard_nfd'),
    path('dashboard/drift/', views.dashboard_drift, name='dashboard_drift'),

    # ==================== SHM API Endpoints ====================
    path('api/shm/sensors/', views.shm_api_sensors, name='shm_sensors'),
    path('api/shm/readings/', views.shm_api_readings, name='shm_readings'),
    path('api/shm/events/', views.shm_api_events, name='shm_events'),
    path('api/shm/events/add/', views.shm_api_add_event, name='shm_add_event'),
    path('api/peak/', views.get_peak_acceleration, name='get_peak_acceleration'),
    path('api/shm/report/', views.shm_report_api, name='shm_report_api'),
    path('api/shm/latest-metrics/', views.shm_latest_metrics),
    path('export/', views.export_shm_pdf, name='export_shm_pdf'),
    path('api/shm/search/', views.shm_search_analysis, name='shm_search_analysis'),
    path('export/shm-search-pdf/', views.export_shm_search_pdf, name='export_shm_search_pdf'),
    

    # ==================== NFD API Endpoints ====================
    path('api/nfd/frequencies/', views.nfd_api_frequencies, name='nfd_frequencies'),
    path('api/nfd/comparisons/', views.nfd_api_comparisons, name='nfd_comparisons'),
    path('api/nfd/frequencies/add/', views.nfd_api_add_frequency, name='nfd_add_frequency'),
    path('api/latest-frequency/', views.latest_frequency, name='latest_frequency'),

    path('api/shm/predictive/', views.shm_predictive_analytics, name='shm_predictive_analytics'), #last one deleted
    path('api/nfd/search/', views.nfd_search_analysis, name='nfd_search_analysis'),
    path('export/nfd-search-pdf/', views.export_nfd_search_pdf, name='export_nfd_search_pdf'),

    # ==================== Drift API Endpoints ====================
    path('api/drift/measurements/', views.drift_api_measurements, name='drift_measurements'),
    path('api/drift/alerts/', views.drift_api_alerts, name='drift_alerts'),
    path('api/drift/measurements/add/', views.drift_api_add_measurement, name='drift_add_measurement'),
    path('api/drift/alerts/add/', views.drift_api_create_alert, name='drift_create_alert'),
    path('api/drift/live-metrics/', views.drift_live_metrics, name='drift_live_metrics'),
    path('api/drift/search/', views.drift_search),
    path('export/drift/pdf/', views.export_drift_pdf, name='export_drift_pdf'),
    path('export/drift/search/pdf/', views.export_drift_search_pdf, name='export_drift_search_pdf'),

    # ==================== System API Endpoints ====================
    path('api/system/settings/', views.system_api_settings, name='system_settings'),

    # ==================== Export Endpoints ====================
    path('export/nfd/', views.export_data, name='export_data'),
]
