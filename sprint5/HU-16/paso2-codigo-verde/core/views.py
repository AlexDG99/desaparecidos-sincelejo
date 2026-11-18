from django.db import connection
from django.http import JsonResponse
from django.shortcuts import render

from accounts.models import User
from cases.models import Case
from core.permissions import admin_required
from sightings.models import Sighting


def health(request):
    """Punto de monitoreo de disponibilidad (RNF-01)."""
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
        return JsonResponse({'estado': 'ok'})
    except Exception:  # pragma: no cover
        return JsonResponse({'estado': 'error'}, status=503)


def error_403(request, exception=None):
    return render(request, '403.html', status=403)


def error_404(request, exception=None):
    return render(request, '404.html', status=404)


def csrf_failure(request, reason=''):
    return render(request, '403.html', {'motivo': 'La sesión del formulario expiró. Recargue la página e intente de nuevo.'}, status=403)


@admin_required
def estadisticas(request):
    """HU-16: panel de estadísticas generales para el administrador."""
    resumen = {
        'casos_activos': Case.objects.filter(moderacion='publicado', estado='activo').count(),
        'casos_pendientes': Case.objects.filter(moderacion='pendiente').count(),
        'casos_cerrados': Case.objects.exclude(estado='activo').count(),
        'avistamientos_publicados': Sighting.objects.filter(moderacion='publicado').count(),
        'avistamientos_pendientes': Sighting.objects.filter(moderacion='pendiente').count(),
        'usuarios': {rol: User.objects.filter(rol=rol).count() for rol in ('ciudadano', 'familiar', 'moderador', 'administrador')},
    }
    return render(request, 'core/estadisticas.html', {'resumen': resumen})
