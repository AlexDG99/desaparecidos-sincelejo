from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from audit.services import log
from core.permissions import admin_required
from core.utils import normalizar

from .exports import caso_a_csv, caso_a_pdf
from .forms import CaseFilterForm, CaseForm, CloseCaseForm
from .models import Case, CasePhoto


def _puede_ver_todo(user, caso):
    """El familiar titular, los moderadores y los administradores ven el caso completo en cualquier estado."""
    return user.is_authenticated and (user.es_moderador or caso.familiar_id == user.pk)


def _caso_visible_o_404(request, codigo):
    caso = get_object_or_404(Case.objects.select_related('familiar'), codigo=codigo)
    if not caso.es_publico and not _puede_ver_todo(request.user, caso):
        raise Http404
    return caso


def home(request):
    recientes = (Case.objects.filter(moderacion=Case.Moderacion.PUBLICADO, estado=Case.Estado.ACTIVO)
                 .prefetch_related('fotos')[:6])
    return render(request, 'cases/home.html', {
        'recientes': recientes,
        'total_activos': Case.objects.filter(moderacion=Case.Moderacion.PUBLICADO, estado=Case.Estado.ACTIVO).count()})


def listado(request):
    """HU-03: casos publicados, con búsqueda por nombre y filtros combinables; 12 por página."""
    form = CaseFilterForm(request.GET or None)
    qs = Case.objects.filter(moderacion=Case.Moderacion.PUBLICADO).prefetch_related('fotos')
    datos = form.cleaned_data if form.is_valid() else {}
    qs = qs.filter(estado=datos.get('estado') or Case.Estado.ACTIVO)
    if datos.get('q'):
        qs = qs.filter(nombre_norm__contains=normalizar(datos['q']))
    if datos.get('zona'):
        qs = qs.filter(zona_norm__contains=normalizar(datos['zona']))
    if datos.get('desde'):
        qs = qs.filter(fecha_desaparicion__gte=datos['desde'])
    if datos.get('hasta'):
        qs = qs.filter(fecha_desaparicion__lte=datos['hasta'])
    page = Paginator(qs, settings.CASES_PER_PAGE).get_page(request.GET.get('page'))
    params = request.GET.copy()
    params.pop('page', None)
    return render(request, 'cases/listado.html', {
        'form': form, 'page': page, 'querystring': params.urlencode(),
        'hay_filtros': any(v for k, v in request.GET.items() if k != 'page')})


def detalle(request, codigo):
    caso = _caso_visible_o_404(request, codigo)
    es_titular_o_mod = _puede_ver_todo(request.user, caso)
    # Un caso cerrado solo conserva nombre y estado para el público (HU-09 CA4)
    ficha_completa = caso.muestra_ficha_completa or es_titular_o_mod
    avistamientos = []
    if ficha_completa:
        qs = caso.avistamientos.select_related('autor').prefetch_related('archivos')
        if not es_titular_o_mod:
            qs = qs.filter(moderacion='publicado')
        avistamientos = list(qs)
    historial = []
    if request.user.is_authenticated and request.user.es_administrador:  # HU-12 CA3
        from audit.models import AuditEvent
        historial = list(AuditEvent.objects.filter(caso_id=caso.pk).order_by('-creado_en', '-id'))
    return render(request, 'cases/detalle.html', {
        'historial': historial,
        'caso': caso, 'ficha_completa': ficha_completa, 'avistamientos': avistamientos,
        'es_titular': request.user.is_authenticated and caso.familiar_id == request.user.pk,
        'es_titular_o_mod': es_titular_o_mod,
        'puede_reportar': caso.es_publico and caso.esta_activo,
        'n_aprobados': caso.avistamientos.filter(moderacion='publicado').count()})


@login_required
def crear(request):
    user = request.user
    if user.rol != user.Rol.FAMILIAR:
        raise PermissionDenied
    if not user.es_familiar_verificado:  # HU-01 CA3
        return render(request, 'cases/no_verificado.html', {'usuario': user}, status=403)
    form = CaseForm(request.POST or None, request.FILES or None)
    if request.method == 'POST' and form.is_valid():
        caso = form.save(familiar=user, request=request)
        log(user, 'crear', 'caso', caso.pk, caso_id=caso.pk, detalle=f'Caso {caso.codigo} creado (menor={caso.es_menor})', request=request)
        return render(request, 'cases/creado.html', {'caso': caso})
    return render(request, 'cases/form.html', {'form': form})


@login_required
def mis_casos(request):
    casos = request.user.casos.all() if request.user.rol == request.user.Rol.FAMILIAR else Case.objects.none()
    return render(request, 'cases/mis_casos.html', {'casos': casos})


@login_required
def cerrar(request, codigo):
    caso = get_object_or_404(Case, codigo=codigo)
    if not (caso.familiar_id == request.user.pk or request.user.es_administrador):
        raise PermissionDenied  # HU-09 CA5
    if not caso.es_publico or not caso.esta_activo:
        messages.error(request, 'Solo se pueden cerrar casos publicados y activos.')
        return redirect(caso.get_absolute_url())
    form = CloseCaseForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        caso.estado = form.cleaned_data['resultado']
        caso.cerrado_en = timezone.now()
        caso.save(update_fields=['estado', 'cerrado_en', 'actualizado_en'])
        log(request.user, 'cerrar', 'caso', caso.pk, caso_id=caso.pk, detalle=f'Resultado: {caso.get_estado_display()}', request=request)
        messages.success(request, 'El caso fue cerrado y su historial quedó archivado.')
        return redirect(caso.get_absolute_url())
    return render(request, 'cases/cerrar.html', {'caso': caso, 'form': form})


@admin_required
@require_POST
def reabrir(request, codigo):
    caso = get_object_or_404(Case, codigo=codigo)
    caso.estado = Case.Estado.ACTIVO
    caso.cerrado_en = None
    caso.save(update_fields=['estado', 'cerrado_en', 'actualizado_en'])
    log(request.user, 'reabrir', 'caso', caso.pk, caso_id=caso.pk, request=request)
    messages.success(request, 'El caso fue reabierto.')
    return redirect(caso.get_absolute_url())


def foto(request, codigo, pk):
    """Entrega una fotografía descifrada solo si el caso es público y activo, o a titular/moderadores."""
    caso = _caso_visible_o_404(request, codigo)
    if not caso.muestra_ficha_completa and not _puede_ver_todo(request.user, caso):
        raise Http404
    f = get_object_or_404(CasePhoto, pk=pk, caso=caso)
    resp = FileResponse(f.imagen.open('rb'), content_type='image/png' if f.imagen.name.endswith('png') else 'image/jpeg')
    resp['Cache-Control'] = 'private, max-age=300'
    return resp


def datos_mapa(request, codigo):
    """HU-08: solo avistamientos aprobados, con ubicación redondeada (≈100 m) para el público."""
    caso = _caso_visible_o_404(request, codigo)
    if not caso.muestra_ficha_completa and not _puede_ver_todo(request.user, caso):
        raise Http404
    puntos = []
    qs = caso.avistamientos.filter(moderacion='publicado', latitud__isnull=False, longitud__isnull=False).order_by('fecha', 'hora')
    for i, a in enumerate(qs, 1):
        puntos.append({
            'n': i, 'lat': round(float(a.latitud), settings.PUBLIC_MAP_COORD_DECIMALS),
            'lng': round(float(a.longitud), settings.PUBLIC_MAP_COORD_DECIMALS),
            'fecha': a.fecha.strftime('%d/%m/%Y'), 'hora': a.hora.strftime('%H:%M'),
            'descripcion': (a.descripcion[:160] + '…') if len(a.descripcion) > 160 else a.descripcion,
            'ubicacion': a.direccion or 'Ubicación aproximada',
        })
    return JsonResponse({'puntos': puntos, 'radio': settings.PUBLIC_MAP_RADIUS_METERS,
                         'centro': list(settings.MAP_DEFAULT_CENTER)})


def mapa(request, codigo):
    caso = _caso_visible_o_404(request, codigo)
    if not caso.muestra_ficha_completa and not _puede_ver_todo(request.user, caso):
        raise Http404
    return render(request, 'cases/mapa.html', {'caso': caso})


@admin_required
def exportar(request, codigo, formato):
    """HU-11: exportación de la ficha del caso en PDF o CSV; solo administradores."""
    caso = get_object_or_404(Case.objects.select_related('familiar'), codigo=codigo)
    if formato == 'csv':
        resp = caso_a_csv(caso)
    elif formato == 'pdf':
        resp = caso_a_pdf(caso)
    else:
        raise Http404
    log(request.user, 'exportar', 'caso', caso.pk, caso_id=caso.pk, detalle=f'Exportación en {formato.upper()}', request=request)
    return resp
