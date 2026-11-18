from django.contrib import messages
from django.contrib.auth import login, views as auth_views
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse_lazy

from audit.services import log
from core.utils import get_client_ip

from .forms import (CitizenSignupForm, DataRequestForm, FamiliarSignupForm, LoginForm,
                    ResubmitVerificationForm)
from .models import ConsentRecord, User


class LoginView(auth_views.LoginView):
    authentication_form = LoginForm
    template_name = 'accounts/login.html'
    redirect_authenticated_user = True


def _registrar_consentimiento(user, request):
    ConsentRecord.objects.create(usuario=user, tipo=ConsentRecord.Tipo.TRATAMIENTO, ip=get_client_ip(request))


def registro_ciudadano(request):
    form = CitizenSignupForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = form.save()
        _registrar_consentimiento(user, request)
        log(user, 'crear', 'usuario', user.pk, detalle='Registro de ciudadano', request=request)
        login(request, user)
        messages.success(request, '¡Su cuenta fue creada! Ya puede reportar avistamientos.')
        return redirect('cases:home')
    return render(request, 'accounts/registro.html', {'form': form, 'titulo': 'Crear cuenta de ciudadano', 'familiar': False})


def registro_familiar(request):
    form = FamiliarSignupForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = form.save()
        _registrar_consentimiento(user, request)
        log(user, 'crear', 'usuario', user.pk, detalle='Registro de familiar (verificación pendiente)', request=request)
        login(request, user)
        messages.success(request, 'Su cuenta fue creada. Un moderador revisará sus datos; cuando su identidad esté verificada podrá publicar casos.')
        return redirect('cases:home')
    return render(request, 'accounts/registro.html', {'form': form, 'titulo': 'Registro de familiar o representante legal', 'familiar': True})


@login_required
def reenviar_verificacion(request):
    user = request.user
    if user.rol != User.Rol.FAMILIAR or user.verificacion not in (User.Verificacion.RECHAZADA, User.Verificacion.PENDIENTE):
        raise Http404
    form = ResubmitVerificationForm(request.POST or None, usuario=user)
    if request.method == 'POST' and form.is_valid():
        d = form.cleaned_data
        user.nombre, user.cedula, user.telefono = d['nombre'], d['cedula'], d['telefono']
        user.verificacion = User.Verificacion.PENDIENTE
        user.verificacion_motivo = ''
        user.save()
        log(user, 'editar', 'usuario', user.pk, detalle='Corrección de datos de verificación', request=request)
        messages.success(request, 'Recibimos sus datos. Un moderador los revisará en las próximas horas.')
        return redirect('cases:home')
    return render(request, 'accounts/reenviar_verificacion.html', {'form': form, 'usuario': user})


@login_required
def mis_datos(request):
    form = DataRequestForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        solicitud = form.save(commit=False)
        solicitud.usuario = request.user
        solicitud.save()
        log(request.user, 'crear', 'solicitud', solicitud.pk, detalle=f'Solicitud de datos: {solicitud.tipo}', request=request)
        messages.success(request, 'Su solicitud fue registrada. Un administrador la atenderá.')
        return redirect('accounts:mis_datos')
    return render(request, 'accounts/mis_datos.html', {
        'form': form, 'solicitudes': request.user.solicitudes_datos.all(),
        'consentimientos': request.user.consentimientos.all()[:10]})


class PasswordResetView(auth_views.PasswordResetView):
    template_name = 'accounts/password_reset.html'
    email_template_name = 'accounts/emails/password_reset.txt'
    subject_template_name = 'accounts/emails/password_reset_subject.txt'
    success_url = reverse_lazy('accounts:password_reset_done')


class PasswordResetDoneView(auth_views.PasswordResetDoneView):
    template_name = 'accounts/password_reset_done.html'


class PasswordResetConfirmView(auth_views.PasswordResetConfirmView):
    template_name = 'accounts/password_reset_confirm.html'
    success_url = reverse_lazy('accounts:password_reset_complete')


class PasswordResetCompleteView(auth_views.PasswordResetCompleteView):
    template_name = 'accounts/password_reset_complete.html'
