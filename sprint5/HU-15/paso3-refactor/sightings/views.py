from datetime import timedelta

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, render
from django.utils import timezone

from audit.services import log
from cases.models import Case
from core.utils import get_client_ip

from .forms import SightingForm
from .models import Sighting, SightingMedia


def limite_excedido(user, ip):
    """HU-04 CA6 / RNF-10: máximo de avistamientos por hora por cuenta y por dirección IP."""
    desde = timezone.now() - timedelta(hours=1)
    por_cuenta = Sighting.objects.filter(autor=user, creado_en__gte=desde).count()
    por_ip = Sighting.objects.filter(ip=ip, creado_en__gte=desde).count() if ip else 0
    return (por_cuenta >= settings.SIGHTING_RATE_LIMIT_PER_HOUR
            or por_ip >= settings.SIGHTING_IP_RATE_LIMIT_PER_HOUR)


@login_required
def crear(request, codigo):
    caso = get_object_or_404(Case, codigo=codigo)
    if not (caso.es_publico and caso.esta_activo):
        raise Http404
    form = SightingForm(request.POST or None, request.FILES or None, caso=caso)
    if request.method == 'POST':
        if limite_excedido(request.user, get_client_ip(request)):
            return render(request, 'sightings/limite.html', {'caso': caso, 'limite': settings.SIGHTING_RATE_LIMIT_PER_HOUR}, status=429)
        if form.is_valid():
            av = form.save(autor=request.user, request=request)
            log(request.user, 'crear', 'avistamiento', av.pk, caso_id=caso.pk, detalle=f'Avistamiento en {caso.codigo}', request=request)
            return render(request, 'sightings/creado.html', {'caso': caso, 'avistamiento': av})
    return render(request, 'sightings/form.html', {
        'form': form, 'caso': caso, 'centro': settings.MAP_DEFAULT_CENTER})


def media(request, pk):
    """Entrega evidencias descifradas. El público solo accede cuando el avistamiento fue aprobado (HU-05 CA5)."""
    m = get_object_or_404(SightingMedia.objects.select_related('avistamiento__caso'), pk=pk)
    av, caso, u = m.avistamiento, m.avistamiento.caso, request.user
    privilegiado = u.is_authenticated and (u.es_moderador or av.autor_id == u.pk or caso.familiar_id == u.pk)
    publico = av.es_publico and caso.es_publico and caso.esta_activo
    if not (publico or privilegiado):
        raise Http404
    tipo = 'video/mp4' if m.tipo == SightingMedia.Tipo.VIDEO else ('image/png' if m.archivo.name.endswith('png') else 'image/jpeg')
    resp = FileResponse(m.archivo.open('rb'), content_type=tipo)
    resp['Cache-Control'] = 'private, max-age=300'
    return resp


@login_required
def mis_avistamientos(request):
    """HU-15: el usuario consulta el estado de los avistamientos que ha enviado."""
    avistamientos = Sighting.objects.de_autor(request.user)
    return render(request, 'sightings/mis_avistamientos.html', {'avistamientos': avistamientos})
