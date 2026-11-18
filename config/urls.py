from django.contrib import admin
from django.urls import include, path

from core import views as core_views

handler403 = 'core.views.error_403'
handler404 = 'core.views.error_404'

urlpatterns = [
    path('admin/', admin.site.urls),
    path('salud/', core_views.health, name='health'),
    path('estadisticas/', core_views.estadisticas, name='estadisticas'),
    path('cuentas/', include('accounts.urls')),
    path('notificaciones/', include('notifications.urls')),
    path('moderacion/', include('moderation.urls')),
    path('auditoria/', include('audit.urls')),
    path('', include('sightings.urls')),
    path('', include('cases.urls')),
]
