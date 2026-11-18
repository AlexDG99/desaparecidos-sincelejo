from django.urls import path

from . import views

app_name = 'notifications'

urlpatterns = [
    path('', views.listado, name='listado'),
    path('<int:pk>/abrir/', views.abrir, name='abrir'),
    path('<int:pk>/leida/', views.marcar_leida, name='leida'),
    path('marcar-todas/', views.marcar_todas, name='todas'),
]
