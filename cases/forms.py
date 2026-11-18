from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from accounts.models import ConsentRecord
from core.forms import BootstrapFormMixin
from core.utils import MultipleFileField, MultipleFileInput, get_client_ip, procesar_imagen

from .models import Case, CasePhoto

CALIDADES = [('', 'Seleccione…'), ('Representante legal', 'Representante legal'), ('Familiar', 'Familiar')]


class CaseForm(BootstrapFormMixin, forms.ModelForm):
    fotos = MultipleFileField(
        label=f'Fotografías (JPG o PNG, máx. 5 MB cada una; de 1 a {settings.MAX_CASE_PHOTOS})',
        widget=MultipleFileInput(attrs={'accept': 'image/jpeg,image/png'}))
    calidad_declarada = forms.ChoiceField(label='Calidad con la que actúa (obligatorio si es menor de edad)', choices=CALIDADES, required=False)
    autorizacion_menor = forms.BooleanField(
        required=False,
        label='Declaro que cuento con la autorización legal para difundir la fotografía y los datos del menor de edad')
    acepta_politica = forms.BooleanField(
        label='Acepto la política de tratamiento de datos personales (Ley 1581 de 2012)',
        error_messages={'required': 'Debe aceptar la política de tratamiento de datos personales.'})

    class Meta:
        model = Case
        fields = ['nombre', 'edad', 'sexo', 'fecha_desaparicion', 'hora_aproximada', 'zona', 'lugar', 'senas',
                  'vestimenta', 'numero_denuncia', 'calidad_declarada', 'autorizacion_menor']
        widgets = {
            'fecha_desaparicion': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
            'hora_aproximada': forms.TimeInput(attrs={'type': 'time'}, format='%H:%M'),
            'senas': forms.Textarea(attrs={'rows': 3}),
            'vestimenta': forms.Textarea(attrs={'rows': 2}),
            'edad': forms.NumberInput(attrs={'min': 0, 'max': 120}),
        }
        labels = {'nombre': 'Nombre completo', 'edad': 'Edad', 'sexo': 'Sexo'}
        help_texts = {'zona': 'Ej.: Barrio Majagual, Comuna 3', 'numero_denuncia': 'Opcional.'}

    field_order = ['nombre', 'edad', 'sexo', 'fecha_desaparicion', 'hora_aproximada', 'zona', 'lugar', 'senas', 'vestimenta',
                   'numero_denuncia', 'fotos', 'calidad_declarada', 'autorizacion_menor', 'acepta_politica']

    def clean_edad(self):
        edad = self.cleaned_data['edad']
        if edad > 120:
            raise ValidationError('Ingrese una edad válida.')
        return edad

    def clean_fecha_desaparicion(self):
        fecha = self.cleaned_data['fecha_desaparicion']
        if fecha > timezone.localdate():
            raise ValidationError('La fecha de desaparición no puede ser futura.')
        return fecha

    def clean_fotos(self):
        archivos = self.cleaned_data.get('fotos') or []
        if not archivos:
            raise ValidationError('Adjunte al menos una fotografía.')
        if len(archivos) > settings.MAX_CASE_PHOTOS:
            raise ValidationError(f'Puede adjuntar máximo {settings.MAX_CASE_PHOTOS} fotografías.')
        procesadas = []
        errores = []
        for f in archivos:
            try:
                procesadas.append(procesar_imagen(f))
            except ValidationError as e:
                errores.extend(e.messages)
        if errores:
            raise ValidationError(errores)
        self._fotos_procesadas = procesadas
        return archivos

    def clean(self):
        data = super().clean()
        edad = data.get('edad')
        if edad is not None and edad < 18:  # HU-14 CA2
            if not data.get('calidad_declarada'):
                self.add_error('calidad_declarada', 'Declare su calidad de representante legal o familiar del menor.')
            if not data.get('autorizacion_menor'):
                self.add_error('autorizacion_menor', 'Debe confirmar la autorización para difundir la fotografía y los datos del menor.')
        return data

    @transaction.atomic
    def save(self, familiar, request=None):
        caso = super().save(commit=False)
        caso.familiar = familiar
        if caso.edad >= 18:
            caso.calidad_declarada = ''
            caso.autorizacion_menor = False
        caso.save()
        for i, (contenido, ext) in enumerate(self._fotos_procesadas):
            foto = CasePhoto(caso=caso, orden=i)
            foto.imagen.save(f'foto.{ext}', contenido, save=False)
            foto.save()
        ip = get_client_ip(request) if request else None
        ConsentRecord.objects.create(usuario=familiar, tipo=ConsentRecord.Tipo.TRATAMIENTO, caso_id=caso.pk, ip=ip)
        if caso.es_menor:
            ConsentRecord.objects.create(usuario=familiar, tipo=ConsentRecord.Tipo.MENOR, caso_id=caso.pk, ip=ip)
        return caso


class CloseCaseForm(BootstrapFormMixin, forms.Form):
    resultado = forms.ChoiceField(
        label='Resultado',
        choices=[(Case.Estado.VIVO, 'Encontrado con vida'), (Case.Estado.MUERTO, 'Encontrado sin vida'),
                 (Case.Estado.CERRADO, 'Cerrado por otro motivo')])
    confirmar = forms.BooleanField(label='Confirmo que deseo cerrar este caso',
                                   error_messages={'required': 'Debe confirmar el cierre del caso.'})


class CaseFilterForm(BootstrapFormMixin, forms.Form):
    q = forms.CharField(label='Nombre', required=False)
    zona = forms.CharField(label='Zona (barrio o comuna)', required=False)
    desde = forms.DateField(label='Desde', required=False, widget=forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'))
    hasta = forms.DateField(label='Hasta', required=False, widget=forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'))
    estado = forms.ChoiceField(label='Estado', required=False, choices=Case.Estado.choices, initial=Case.Estado.ACTIVO)
