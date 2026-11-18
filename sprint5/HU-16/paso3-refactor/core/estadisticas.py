from accounts.models import User
from cases.models import Case
from sightings.models import Sighting

ROLES = ('ciudadano', 'familiar', 'moderador', 'administrador')


def calcular_resumen():
    """HU-16: conteos generales de casos, avistamientos y usuarios."""
    return {
        'casos_activos': Case.objects.filter(moderacion='publicado', estado='activo').count(),
        'casos_pendientes': Case.objects.filter(moderacion='pendiente').count(),
        'casos_cerrados': Case.objects.exclude(estado='activo').count(),
        'avistamientos_publicados': Sighting.objects.filter(moderacion='publicado').count(),
        'avistamientos_pendientes': Sighting.objects.filter(moderacion='pendiente').count(),
        'usuarios': {rol: User.objects.filter(rol=rol).count() for rol in ROLES},
    }
