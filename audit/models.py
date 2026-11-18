from django.db import models
from django.db.models.query import QuerySet


class AuditReadOnlyError(Exception):
    pass


class AuditQuerySet(QuerySet):
    """Los registros de auditoría son de solo lectura (HU-12 CA4)."""

    def update(self, **kwargs):
        raise AuditReadOnlyError('El registro de auditoría es de solo lectura.')

    def delete(self):
        raise AuditReadOnlyError('El registro de auditoría es de solo lectura.')

    def bulk_update(self, *args, **kwargs):
        raise AuditReadOnlyError('El registro de auditoría es de solo lectura.')


class AuditEvent(models.Model):
    class Accion(models.TextChoices):
        CREAR = 'crear', 'Crear'
        EDITAR = 'editar', 'Editar'
        APROBAR = 'aprobar', 'Aprobar'
        RECHAZAR = 'rechazar', 'Rechazar'
        SOSPECHOSO = 'sospechoso', 'Marcar como sospechoso'
        CERRAR = 'cerrar', 'Cerrar'
        REABRIR = 'reabrir', 'Reabrir'
        EXPORTAR = 'exportar', 'Exportar'
        ELIMINAR = 'eliminar', 'Eliminar'
        VERIFICAR = 'verificar', 'Verificar identidad'
        REPORTAR = 'reportar', 'Reportar contenido'

    usuario = models.ForeignKey('accounts.User', null=True, blank=True, on_delete=models.PROTECT, related_name='+')
    usuario_email = models.CharField(max_length=254, blank=True)
    rol = models.CharField(max_length=20, blank=True)
    accion = models.CharField(max_length=12, choices=Accion.choices, db_index=True)
    entidad = models.CharField(max_length=20, db_index=True)
    entidad_id = models.PositiveBigIntegerField(null=True, blank=True)
    caso_id = models.PositiveBigIntegerField(null=True, blank=True, db_index=True)
    detalle = models.TextField(blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    creado_en = models.DateTimeField(auto_now_add=True, db_index=True)

    objects = AuditQuerySet.as_manager()

    class Meta:
        ordering = ['-creado_en', '-id']
        verbose_name = 'evento de auditoría'
        verbose_name_plural = 'eventos de auditoría'

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise AuditReadOnlyError('El registro de auditoría es de solo lectura.')
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise AuditReadOnlyError('El registro de auditoría es de solo lectura.')

    def __str__(self):
        return f'{self.creado_en:%Y-%m-%d %H:%M} {self.usuario_email} {self.accion} {self.entidad}#{self.entidad_id}'
