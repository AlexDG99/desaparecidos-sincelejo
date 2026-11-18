from django.contrib import admin

from .models import Sighting, SightingMedia


class MediaInline(admin.TabularInline):
    model = SightingMedia
    extra = 0
    readonly_fields = ('archivo',)


@admin.register(Sighting)
class SightingAdmin(admin.ModelAdmin):
    list_display = ('id', 'caso', 'autor', 'fecha', 'hora', 'moderacion')
    list_filter = ('moderacion',)
    inlines = [MediaInline]
