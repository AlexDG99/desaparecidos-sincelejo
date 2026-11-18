from datetime import datetime

from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from core.forms import BootstrapFormMixin
from core.utils import MultipleFileField, MultipleFileInput, get_client_ip, procesar_imagen, validar_video_mp4

from .models import Sighting, SightingMedia


class SightingForm(BootstrapFormMixin, forms.ModelForm):
    evidencias = MultipleFileField(
        required=False, label='Evidencia (opcional)',
        help_text=f'Hasta {settings.MAX_SIGHTING_MEDIA_FILES} archivos en total: imágenes JPG/PNG de máx. 5 MB y, como máximo, '
                  'un video MP4 de hasta 30 MB.',
        widget=MultipleFileInput(attrs={'accept': 'image/jpeg,image/png,video/mp4'}))

    class Meta:
        model = Sighting
        fields = ['fecha', 'hora', 'direccion', 'latitud', 'longitud', 'descripcion']
        widgets = {
            'fecha': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
            'hora': forms.TimeInput(attrs={'type': 'time'}, format='%H:%M'),
            'descripcion': forms.Textarea(attrs={'rows': 4, 'minlength': 20, 'maxlength': 1000}),
            'latitud': forms.HiddenInput(), 'longitud': forms.HiddenInput(),
        }
        help_texts = {'descripcion': 'Entre 20 y 1.000 caracteres: qué vio, con quién estaba, cómo iba vestida la persona, hacia dónde se dirigía.'}

    def __init__(self, *args, caso, **kwargs):
        super().__init__(*args, **kwargs)
        self.caso = caso
        self.fields['direccion'].required = False

    def clean_descripcion(self):
        d = self.cleaned_data['descripcion'].strip()
        if len(d) < 20:
            raise ValidationError('La descripción debe tener al menos 20 caracteres.')
        if len(d) > 1000:
            raise ValidationError('La descripción no puede superar los 1.000 caracteres.')
        return d

    def clean_evidencias(self):
        archivos = self.cleaned_data.get('evidencias') or []
        if len(archivos) > settings.MAX_SIGHTING_MEDIA_FILES:
            raise ValidationError(f'Puede adjuntar máximo {settings.MAX_SIGHTING_MEDIA_FILES} archivos.')
        procesados, errores, videos = [], [], 0
        for f in archivos:
            try:
                if f.name.lower().endswith('.mp4'):
                    videos += 1
                    if videos > 1:
                        raise ValidationError('Solo puede adjuntar un video por avistamiento.')
                    procesados.append((validar_video_mp4(f), 'mp4', SightingMedia.Tipo.VIDEO))
                else:
                    contenido, ext = procesar_imagen(f)  # elimina metadatos EXIF (HU-05 CA4)
                    procesados.append((contenido, ext, SightingMedia.Tipo.IMAGEN))
            except ValidationError as e:
                errores.extend(e.messages)
        if errores:
            raise ValidationError(errores)
        self._evidencias = procesados
        return archivos

    def clean(self):
        data = super().clean()
        fecha, hora = data.get('fecha'), data.get('hora')
        if fecha and hora:
            momento = timezone.make_aware(datetime.combine(fecha, hora))
            if momento > timezone.now():
                self.add_error('fecha', 'La fecha y hora del avistamiento no pueden ser posteriores al momento actual.')
            elif fecha < self.caso.fecha_desaparicion:
                self.add_error('fecha', 'La fecha del avistamiento no puede ser anterior a la fecha de desaparición.')
        if not data.get('direccion') and (data.get('latitud') is None or data.get('longitud') is None):
            self.add_error('direccion', 'Indique la ubicación: marque un punto en el mapa, use su ubicación actual o escriba una dirección o barrio.')
        return data

    @transaction.atomic
    def save(self, autor, request=None):
        av = super().save(commit=False)
        av.caso, av.autor = self.caso, autor
        av.ip = get_client_ip(request) if request else None
        av.save()
        for i, (contenido, ext, tipo) in enumerate(getattr(self, '_evidencias', [])):
            m = SightingMedia(avistamiento=av, tipo=tipo, orden=i)
            m.archivo.save(f'evidencia.{ext}', contenido, save=False)
            m.save()
        return av
