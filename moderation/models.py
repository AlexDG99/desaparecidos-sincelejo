from django.conf import settings
from django.db import models
from django.db.models import Q


class ContentReport(models.Model):
    """Reporte ciudadano de contenido falso, duplicado o inapropiado (HU-10)."""

    class Motivo(models.TextChoices):
        FALSO = 'falso', 'Falso'
        DUPLICADO = 'duplicado', 'Duplicado'
        INAPROPIADO = 'inapropiado', 'Inapropiado'
        OTRO = 'otro', 'Otro'

    class Estado(models.TextChoices):
        PENDIENTE = 'pendiente', 'Pendiente'
        MANTENIDO = 'mantenido', 'Contenido mantenido'
        EDITADO = 'editado', 'Contenido editado'
        RETIRADO = 'retirado', 'Contenido retirado'

    reportero = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='reportes_contenido')
    caso = models.ForeignKey('cases.Case', null=True, blank=True, on_delete=models.CASCADE, related_name='reportes')
    avistamiento = models.ForeignKey('sightings.Sighting', null=True, blank=True, on_delete=models.CASCADE, related_name='reportes')
    motivo = models.CharField(max_length=12, choices=Motivo.choices)
    comentario = models.TextField(blank=True)
    estado = models.CharField(max_length=10, choices=Estado.choices, default=Estado.PENDIENTE, db_index=True)
    resuelto_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    resuelto_en = models.DateTimeField(null=True, blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['creado_en']
        constraints = [
            models.UniqueConstraint(fields=['reportero', 'caso'], condition=Q(caso__isnull=False), name='un_reporte_por_caso'),
            models.UniqueConstraint(fields=['reportero', 'avistamiento'], condition=Q(avistamiento__isnull=False), name='un_reporte_por_avistamiento'),
            models.CheckConstraint(condition=Q(caso__isnull=False) ^ Q(avistamiento__isnull=False), name='reporte_un_solo_objetivo'),
        ]

    @property
    def objetivo(self):
        return self.caso or self.avistamiento
