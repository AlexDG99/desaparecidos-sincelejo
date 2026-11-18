from django.urls import path

from . import views

app_name = 'sightings'

urlpatterns = [
    path('casos/<str:codigo>/avistamientos/nuevo/', views.crear, name='crear'),
    path('avistamientos/archivo/<int:pk>/', views.media, name='media'),
    path('mis-avistamientos/', views.mis_avistamientos, name='mis_avistamientos'),
]
