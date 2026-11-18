from django.urls import path

from . import views

app_name = 'cases'

urlpatterns = [
    path('', views.home, name='home'),
    path('casos/', views.listado, name='listado'),
    path('casos/nuevo/', views.crear, name='crear'),
    path('mis-casos/', views.mis_casos, name='mis_casos'),
    path('casos/<str:codigo>/', views.detalle, name='detalle'),
    path('casos/<str:codigo>/cerrar/', views.cerrar, name='cerrar'),
    path('casos/<str:codigo>/reabrir/', views.reabrir, name='reabrir'),
    path('casos/<str:codigo>/foto/<int:pk>/', views.foto, name='foto'),
    path('casos/<str:codigo>/mapa/', views.mapa, name='mapa'),
    path('casos/<str:codigo>/mapa-datos/', views.datos_mapa, name='mapa_datos'),
    path('casos/<str:codigo>/exportar/<str:formato>/', views.exportar, name='exportar'),
]
