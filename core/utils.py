"""Utilidades compartidas: normalización de texto, IP del cliente y procesamiento seguro de archivos."""
import io
import re
import unicodedata

from django import forms
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.exceptions import ValidationError
from PIL import Image, ImageOps, UnidentifiedImageError


def normalizar(texto):
    """Minúsculas, sin tildes ni espacios repetidos (búsqueda insensible a mayúsculas y tildes, HU-03 CA2)."""
    texto = unicodedata.normalize('NFKD', texto or '')
    texto = ''.join(c for c in texto if not unicodedata.combining(c))
    return re.sub(r'\s+', ' ', texto).strip().lower()


def get_client_ip(request):
    if settings.TRUST_X_FORWARDED_FOR:
        forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
        if forwarded:
            return forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR') or None


def procesar_imagen(archivo, max_bytes=None):
    """Valida que sea JPG/PNG de hasta 5 MB y devuelve un ContentFile sin metadatos (EXIF, perfiles, texto)."""
    max_bytes = max_bytes or settings.MAX_IMAGE_BYTES
    if archivo.size > max_bytes:
        raise ValidationError(f'«{archivo.name}» supera el tamaño máximo de {max_bytes // (1024 * 1024)} MB.')
    try:
        archivo.seek(0)
        img = Image.open(archivo)
        formato = img.format
        img.verify()
        archivo.seek(0)
        img = Image.open(archivo)
    except (UnidentifiedImageError, OSError, SyntaxError):
        raise ValidationError(f'«{archivo.name}» no es una imagen válida. Use JPG o PNG.')
    if formato not in ('JPEG', 'PNG'):
        raise ValidationError(f'«{archivo.name}» tiene un formato no permitido. Use JPG o PNG.')
    img = ImageOps.exif_transpose(img)  # respeta la orientación antes de descartar el EXIF
    salida = io.BytesIO()
    if formato == 'JPEG':
        img.convert('RGB').save(salida, 'JPEG', quality=90)  # sin exif= ni icc_profile= → se eliminan
        ext = 'jpg'
    else:
        img.save(salida, 'PNG')  # sin pnginfo → se eliminan los chunks de texto
        ext = 'png'
    return ContentFile(salida.getvalue()), ext


def validar_video_mp4(archivo):
    if archivo.size > settings.MAX_VIDEO_BYTES:
        raise ValidationError(
            f'«{archivo.name}» supera el tamaño máximo de {settings.MAX_VIDEO_BYTES // (1024 * 1024)} MB para videos.')
    archivo.seek(0)
    cabecera = archivo.read(12)
    archivo.seek(0)
    if not archivo.name.lower().endswith('.mp4') or cabecera[4:8] != b'ftyp':
        raise ValidationError(f'«{archivo.name}» no es un video MP4 válido.')
    return archivo


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    """Campo de varios archivos (patrón oficial de Django ≥ 4.2)."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault('widget', MultipleFileInput())
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        single = super().clean
        if isinstance(data, (list, tuple)):
            return [single(d, initial) for d in data if d]
        return [single(data, initial)] if data else []
