from datetime import timedelta
import re

from django import forms
from django.conf import settings
from django.contrib.auth import authenticate, password_validation
from django.contrib.auth.forms import AuthenticationForm
from django.core.exceptions import ValidationError
from django.utils import timezone

from core.forms import BootstrapFormMixin

from .models import DataRequest, User

PARENTESCOS = [('', 'Seleccione…'), ('Madre/Padre', 'Madre / Padre'), ('Hijo/a', 'Hijo/a'),
               ('Hermano/a', 'Hermano/a'), ('Cónyuge o compañero/a', 'Cónyuge o compañero/a'),
               ('Abuelo/a', 'Abuelo/a'), ('Tío/a', 'Tío/a'), ('Representante legal', 'Representante legal'),
               ('Otro familiar', 'Otro familiar')]


class LoginForm(BootstrapFormMixin, AuthenticationForm):
    username = forms.EmailField(label='Correo electrónico', widget=forms.EmailInput(attrs={'autofocus': True, 'autocomplete': 'email'}))
    password = forms.CharField(label='Contraseña', strip=False, widget=forms.PasswordInput(attrs={'autocomplete': 'current-password'}))

    def _mensaje_bloqueo(self, user):
        minutos = max(1, int((user.bloqueado_hasta - timezone.now()).total_seconds() // 60) + 1)
        return ValidationError(
            f'La cuenta está bloqueada temporalmente por demasiados intentos fallidos. '
            f'Intente de nuevo en {minutos} minuto{"s" if minutos != 1 else ""}.', code='locked')

    def clean(self):
        email = (self.cleaned_data.get('username') or '').strip().lower()
        password = self.cleaned_data.get('password')
        if not email or not password:
            return self.cleaned_data
        user = User.objects.filter(email=email).first()
        if user:
            if user.esta_bloqueado:
                raise self._mensaje_bloqueo(user)
            if user.bloqueado_hasta:  # el bloqueo venció: se reinicia el contador
                user.bloqueado_hasta, user.intentos_fallidos = None, 0
                user.save(update_fields=['bloqueado_hasta', 'intentos_fallidos'])
        self.user_cache = authenticate(self.request, username=email, password=password)
        if self.user_cache is None:
            if user:
                user.intentos_fallidos += 1
                if user.intentos_fallidos >= settings.LOGIN_MAX_FAILED_ATTEMPTS:
                    user.bloqueado_hasta = timezone.now() + timedelta(minutes=settings.LOGIN_LOCK_MINUTES)
                    user.intentos_fallidos = 0
                    user.save(update_fields=['intentos_fallidos', 'bloqueado_hasta'])
                    raise self._mensaje_bloqueo(user)
                user.save(update_fields=['intentos_fallidos'])
            raise self.get_invalid_login_error()
        self.confirm_login_allowed(self.user_cache)
        if self.user_cache.intentos_fallidos:
            self.user_cache.intentos_fallidos = 0
            self.user_cache.save(update_fields=['intentos_fallidos'])
        return self.cleaned_data


class BaseSignupForm(BootstrapFormMixin, forms.ModelForm):
    password1 = forms.CharField(label='Contraseña', strip=False, widget=forms.PasswordInput(attrs={'autocomplete': 'new-password'}),
                                help_text='Mínimo 8 caracteres; no use contraseñas comunes ni solo números.')
    password2 = forms.CharField(label='Confirme la contraseña', strip=False, widget=forms.PasswordInput(attrs={'autocomplete': 'new-password'}))
    acepta_politica = forms.BooleanField(
        label='Acepto la política de tratamiento de datos personales (Ley 1581 de 2012)', required=True,
        error_messages={'required': 'Debe aceptar la política de tratamiento de datos personales.'})

    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise ValidationError('Ya existe una cuenta con este correo electrónico.')
        return email

    def clean(self):
        data = super().clean()
        p1, p2 = data.get('password1'), data.get('password2')
        if p1 and p2 and p1 != p2:
            self.add_error('password2', 'Las contraseñas no coinciden.')
        elif p1:
            try:
                password_validation.validate_password(p1, User(email=data.get('email', ''), nombre=data.get('nombre', '')))
            except ValidationError as e:
                self.add_error('password1', e)
        return data


class CitizenSignupForm(BaseSignupForm):
    class Meta:
        model = User
        fields = ['nombre', 'email']
        labels = {'nombre': 'Nombre completo', 'email': 'Correo electrónico'}

    def save(self, commit=True):
        user = User.objects.create_user(self.cleaned_data['email'], self.cleaned_data['password1'],
                                        nombre=self.cleaned_data['nombre'], rol=User.Rol.CIUDADANO)
        return user


class FamiliarSignupForm(BaseSignupForm):
    parentesco = forms.ChoiceField(label='Parentesco con la persona desaparecida', choices=PARENTESCOS)

    class Meta:
        model = User
        fields = ['nombre', 'cedula', 'email', 'telefono', 'parentesco']
        labels = {'nombre': 'Nombres completos', 'cedula': 'Número de cédula', 'email': 'Correo electrónico',
                  'telefono': 'Teléfono celular'}

    field_order = ['nombre', 'cedula', 'email', 'telefono', 'parentesco', 'password1', 'password2', 'acepta_politica']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['cedula'].required = True
        self.fields['telefono'].required = True

    def clean_cedula(self):
        cedula = re.sub(r'[\s.]', '', self.cleaned_data['cedula'])
        if not cedula.isdigit() or not 5 <= len(cedula) <= 12:
            raise ValidationError('Ingrese un número de cédula válido (solo dígitos).')
        if User.objects.filter(cedula=cedula).exists():
            raise ValidationError('Ya existe una cuenta con este número de cédula.')
        return cedula

    def save(self, commit=True):
        d = self.cleaned_data
        user = User.objects.create_user(
            d['email'], d['password1'], nombre=d['nombre'], rol=User.Rol.FAMILIAR, cedula=d['cedula'],
            telefono=d['telefono'], parentesco=d['parentesco'], verificacion=User.Verificacion.PENDIENTE)
        return user


class ResubmitVerificationForm(BootstrapFormMixin, forms.Form):
    """Permite corregir los datos de identidad cuando la verificación fue rechazada (no se solicitan documentos)."""
    nombre = forms.CharField(label='Nombres completos', max_length=150)
    cedula = forms.CharField(label='Número de cédula', max_length=15)
    telefono = forms.CharField(label='Teléfono celular', max_length=20)

    def __init__(self, *args, usuario=None, **kwargs):
        self.usuario = usuario
        super().__init__(*args, **kwargs)
        if usuario is not None and not self.is_bound:
            self.initial = {'nombre': usuario.nombre, 'cedula': usuario.cedula, 'telefono': usuario.telefono}

    def clean_cedula(self):
        cedula = re.sub(r'[\s.]', '', self.cleaned_data['cedula'])
        if not cedula.isdigit() or not 5 <= len(cedula) <= 12:
            raise ValidationError('Ingrese un número de cédula válido (solo dígitos).')
        if User.objects.filter(cedula=cedula).exclude(pk=self.usuario.pk).exists():
            raise ValidationError('Ya existe una cuenta con este número de cédula.')
        return cedula


class DataRequestForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = DataRequest
        fields = ['tipo', 'mensaje']
        labels = {'tipo': 'Tipo de solicitud', 'mensaje': 'Describa su solicitud'}
        widgets = {'mensaje': forms.Textarea(attrs={'rows': 4})}
