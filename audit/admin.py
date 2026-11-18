from django.contrib import admin

from .models import AuditEvent


@admin.register(AuditEvent)
class AuditEventAdmin(admin.ModelAdmin):
    list_display = ('creado_en', 'usuario_email', 'rol', 'accion', 'entidad', 'entidad_id', 'ip')
    list_filter = ('accion', 'entidad')
    search_fields = ('usuario_email', 'detalle')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
