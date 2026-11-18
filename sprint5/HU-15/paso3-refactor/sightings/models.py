import uuid

from django.conf import settings
from django.db import models
from django.urls import reverse

from core.storage import get_private_storage


def _media_path(instance, filename):
    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else 'bin'
    return f'avistamientos/{uuid.uuid4().hex}.{ext}'


class SightingQuerySet(models.QuerySet):
    def de_autor(self, usuario):
        """Avistamientos enviados por un usuario, del más reciente al más antiguo."""
        return self.filter(autor=usuario).select_related('caso').order_by('-creado_en')


class Sighting(models.Model):
    class Moderacion(models.TextChoices):
        PENDIENTE = 'pendiente', 'Pendiente de moderación'
        PUBLICADO = 'publicado', 'Publicado'
        RECHAZADO = 'rechazado', 'Rechazado'
        SOSPECHOSO = 'sospechoso', 'Sospechoso (escalado)'

    caso = models.ForeignKey('cases.Case', on_delete=models.CASCADE, related_name='avistamientos')
    autor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='avistamientos')
    fecha = models.DateField('fecha del avistamiento')
    hora = models.TimeField('hora del avistamiento')
    latitud = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitud = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    direccion = models.CharField('dirección o barrio', max_length=200, blank=True)
    descripcion = models.TextField('descripción')
    moderacion = models.CharField(max_length=12, choices=Moderacion.choices, default=Moderacion.PENDIENTE, db_index=True)
    moderacion_motivo = models.TextField(blank=True)
    moderado_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    moderado_en = models.DateTimeField(null=True, blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    creado_en = models.DateTimeField(auto_now_add=True, db_index=True)

    objects = SightingQuerySet.as_manager()

    class Meta:
        ordering = ['-fecha', '-hora']
        indexes = [models.Index(fields=['caso', 'moderacion'])]

    def __str__(self):
        return f'Avistamiento #{self.pk} de {self.caso.codigo}'

    def get_absolute_url(self):
        return reverse('cases:detalle', args=[self.caso.codigo]) + f'#avistamiento-{self.pk}'

    @property
    def es_publico(self):
        return self.moderacion == self.Moderacion.PUBLICADO

    @property
    def ubicacion_resumen(self):
        """Ubicación aproximada para mostrar en notificaciones y listados."""
        return self.direccion or 'Ubicación marcada en el mapa'


class SightingMedia(models.Model):
    class Tipo(models.TextChoices):
        IMAGEN = 'imagen', 'Imagen'
        VIDEO = 'video', 'Video'

    avistamiento = models.ForeignKey(Sighting, on_delete=models.CASCADE, related_name='archivos')
    archivo = models.FileField(upload_to=_media_path, storage=get_private_storage)
    tipo = models.CharField(max_length=10, choices=Tipo.choices)
    orden = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ['orden', 'id']
