from django.urls import path

from . import views

app_name = 'moderation'

urlpatterns = [
    path('', views.cola, name='cola'),
    path('caso/<int:pk>/', views.detalle_caso, name='caso'),
    path('avistamiento/<int:pk>/', views.detalle_avistamiento, name='avistamiento'),
    path('verificaciones/', views.verificaciones, name='verificaciones'),
    path('verificaciones/<int:pk>/', views.verificacion_detalle, name='verificacion'),
    path('reportes/', views.reportes, name='reportes'),
    path('reportes/<str:tipo>/<int:pk>/', views.reporte_resolver, name='reporte_resolver'),
    path('reportar/caso/<int:pk>/', views.reportar_caso, name='reportar_caso'),
    path('reportar/avistamiento/<int:pk>/', views.reportar_avistamiento, name='reportar_avistamiento'),
    path('solicitudes-datos/', views.solicitudes_datos, name='solicitudes'),
    path('solicitudes-datos/<int:pk>/atender/', views.atender_solicitud, name='atender_solicitud'),
]
