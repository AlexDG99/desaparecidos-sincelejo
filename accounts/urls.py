from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

app_name = 'accounts'

urlpatterns = [
    path('ingresar/', views.LoginView.as_view(), name='login'),
    path('salir/', auth_views.LogoutView.as_view(), name='logout'),
    path('registro/', views.registro_ciudadano, name='registro'),
    path('registro-familiar/', views.registro_familiar, name='registro_familiar'),
    path('verificacion/reenviar/', views.reenviar_verificacion, name='reenviar_verificacion'),
    path('mis-datos/', views.mis_datos, name='mis_datos'),
    path('recuperar/', views.PasswordResetView.as_view(), name='password_reset'),
    path('recuperar/enviado/', views.PasswordResetDoneView.as_view(), name='password_reset_done'),
    path('recuperar/<uidb64>/<token>/', views.PasswordResetConfirmView.as_view(), name='password_reset_confirm'),
    path('recuperar/listo/', views.PasswordResetCompleteView.as_view(), name='password_reset_complete'),
]
