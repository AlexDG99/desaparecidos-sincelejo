from django.contrib import admin

from .models import Case, CasePhoto


class CasePhotoInline(admin.TabularInline):
    model = CasePhoto
    extra = 0
    readonly_fields = ('imagen',)


@admin.register(Case)
class CaseAdmin(admin.ModelAdmin):
    list_display = ('codigo', 'nombre', 'edad', 'zona', 'moderacion', 'estado', 'creado_en')
    list_filter = ('moderacion', 'estado', 'es_menor')
    search_fields = ('codigo', 'nombre')
    inlines = [CasePhotoInline]
