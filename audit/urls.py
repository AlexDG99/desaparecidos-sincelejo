from django.urls import path

from . import views

app_name = 'audit'

urlpatterns = [
    path('', views.listado, name='listado'),
    path('exportar.csv', views.exportar_csv, name='exportar'),
]
