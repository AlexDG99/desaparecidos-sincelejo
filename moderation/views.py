from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.models import DataRequest, User
from audit.services import log
from cases.models import Case
from core.permissions import admin_required, moderator_required
from notifications.services import notificar
from sightings.models import Sighting

from . import services
from .forms import ReportForm, ResolveReportForm
from .models import ContentReport
from .services import ModeracionError, puede_gestionar


def _estados_visibles(user):
    return ['pendiente', 'sospechoso'] if user.es_administrador else ['pendiente']


@moderator_required
def cola(request):
    """HU-06 CA1: cola de reportes pendientes (casos y avistamientos) del más antiguo al más reciente."""
    estados = _estados_visibles(request.user)
    ahora = timezone.now()
    sla = timedelta(hours=settings.MODERATION_SLA_HOURS)
    items = []
    for c in Case.objects.filter(moderacion__in=estados).select_related('familiar'):
        items.append({'tipo': 'Caso', 'etiqueta': c.codigo, 'resumen': f'{c.nombre}, {c.edad} años', 'autor': c.familiar,
                      'creado_en': c.creado_en, 'estado': c.get_moderacion_display(), 'menor': c.es_menor,
                      'url': f'/moderacion/caso/{c.pk}/', 'vencido': ahora - c.creado_en > sla})
    for a in Sighting.objects.filter(moderacion__in=estados).select_related('autor', 'caso'):
        items.append({'tipo': 'Avistamiento', 'etiqueta': f'#{a.pk}', 'resumen': f'En {a.caso.codigo}: {a.descripcion[:70]}',
                      'autor': a.autor, 'creado_en': a.creado_en, 'estado': a.get_moderacion_display(), 'menor': False,
                      'url': f'/moderacion/avistamiento/{a.pk}/', 'vencido': ahora - a.creado_en > sla})
    items.sort(key=lambda i: i['creado_en'])
    return render(request, 'moderation/cola.html', {
        'items': items,
        'n_verificaciones': User.objects.filter(rol=User.Rol.FAMILIAR, verificacion=User.Verificacion.PENDIENTE).count(),
        'n_reportes': len(services.grupos_de_reportes()),
        'n_solicitudes': DataRequest.objects.filter(estado=DataRequest.Estado.PENDIENTE).count() if request.user.es_administrador else None,
        'sla': settings.MODERATION_SLA_HOURS})


def _accion_moderacion(request, obj, tipo):
    accion = request.POST.get('accion')
    motivo = request.POST.get('motivo', '')
    if not puede_gestionar(request.user, obj):
        messages.error(request, 'Este elemento solo puede ser gestionado por un administrador.')
        return False
    try:
        if tipo == 'caso':
            {'aprobar': lambda: services.aprobar_caso(obj, request.user, request),
             'rechazar': lambda: services.rechazar_caso(obj, request.user, motivo, request),
             'sospechoso': lambda: services.sospechoso_caso(obj, request.user, request)}[accion]()
        else:
            {'aprobar': lambda: services.aprobar_avistamiento(obj, request.user, request),
             'rechazar': lambda: services.rechazar_avistamiento(obj, request.user, motivo, request),
             'sospechoso': lambda: services.sospechoso_avistamiento(obj, request.user, request)}[accion]()
    except KeyError:
        messages.error(request, 'Acción no válida.')
        return False
    except ModeracionError as e:
        messages.error(request, str(e))
        return False
    messages.success(request, {'aprobar': 'Reporte aprobado y publicado.', 'rechazar': 'Reporte rechazado; se notificó al autor.',
                               'sospechoso': 'Reporte marcado como sospechoso y escalado al administrador.'}[accion])
    return True


@moderator_required
def detalle_caso(request, pk):
    caso = get_object_or_404(Case.objects.select_related('familiar', 'moderado_por'), pk=pk)
    if request.method == 'POST':
        if _accion_moderacion(request, caso, 'caso'):
            return redirect('moderation:cola')
        return redirect('moderation:caso', pk=pk)
    return render(request, 'moderation/detalle_caso.html', {'caso': caso, 'puede': puede_gestionar(request.user, caso)})


@moderator_required
def detalle_avistamiento(request, pk):
    av = get_object_or_404(Sighting.objects.select_related('autor', 'caso', 'moderado_por').prefetch_related('archivos'), pk=pk)
    if request.method == 'POST':
        if _accion_moderacion(request, av, 'avistamiento'):
            return redirect('moderation:cola')
        return redirect('moderation:avistamiento', pk=pk)
    return render(request, 'moderation/detalle_avistamiento.html', {'av': av, 'puede': puede_gestionar(request.user, av)})


# ---------------------------------------------------------------- verificación de familiares
@moderator_required
def verificaciones(request):
    pendientes = User.objects.filter(rol=User.Rol.FAMILIAR, verificacion=User.Verificacion.PENDIENTE).order_by('date_joined')
    return render(request, 'moderation/verificaciones.html', {'pendientes': pendientes})


@moderator_required
def verificacion_detalle(request, pk):
    usuario = get_object_or_404(User, pk=pk, rol=User.Rol.FAMILIAR)
    if request.method == 'POST':
        if usuario.verificacion != User.Verificacion.PENDIENTE:
            messages.error(request, 'Esta solicitud ya fue gestionada.')
            return redirect('moderation:verificaciones')
        try:
            if request.POST.get('accion') == 'aprobar':
                services.aprobar_verificacion(usuario, request.user, request)
                messages.success(request, 'Identidad verificada.')
            elif request.POST.get('accion') == 'rechazar':
                services.rechazar_verificacion(usuario, request.user, request.POST.get('motivo'), request)
                messages.success(request, 'Verificación rechazada; se notificó al usuario.')
            else:
                raise ModeracionError('Acción no válida.')
        except ModeracionError as e:
            messages.error(request, str(e))
            return redirect('moderation:verificacion', pk=pk)
        return redirect('moderation:verificaciones')
    return render(request, 'moderation/verificacion_detalle.html', {'usuario': usuario})


# ---------------------------------------------------------------- reportes de contenido (HU-10)
def _reportar(request, caso=None, avistamiento=None):
    objetivo = caso or avistamiento
    form = ReportForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        r = form.save(commit=False)
        r.reportero, r.caso, r.avistamiento = request.user, caso, avistamiento
        try:
            with transaction.atomic():
                r.save()
        except IntegrityError:  # HU-10 CA3: no se duplica el reporte
            messages.info(request, 'Ya habíamos recibido su reporte sobre este contenido. Gracias por colaborar.')
        else:
            log(request.user, 'reportar', 'caso' if caso else 'avistamiento', objetivo.pk,
                caso_id=caso.pk if caso else avistamiento.caso_id, detalle=f'Motivo: {r.motivo}', request=request)
            messages.success(request, 'Gracias. Su reporte fue enviado al equipo de moderación.')
        return redirect(caso.get_absolute_url() if caso else avistamiento.caso.get_absolute_url())
    return render(request, 'moderation/reportar.html', {'form': form, 'objetivo': objetivo, 'es_caso': caso is not None})


@login_required
def reportar_caso(request, pk):
    caso = get_object_or_404(Case, pk=pk, moderacion=Case.Moderacion.PUBLICADO)
    return _reportar(request, caso=caso)


@login_required
def reportar_avistamiento(request, pk):
    av = get_object_or_404(Sighting.objects.select_related('caso'), pk=pk, moderacion=Sighting.Moderacion.PUBLICADO)
    return _reportar(request, avistamiento=av)


@moderator_required
def reportes(request):
    return render(request, 'moderation/reportes.html', {
        'grupos': services.grupos_de_reportes(), 'umbral': settings.CONTENT_REPORT_ESCALATION_THRESHOLD})


@moderator_required
def reporte_resolver(request, tipo, pk):
    if tipo == 'caso':
        objeto = get_object_or_404(Case, pk=pk)
    elif tipo == 'avistamiento':
        objeto = get_object_or_404(Sighting.objects.select_related('caso'), pk=pk)
    else:
        raise Http404
    filtro = {'caso': objeto} if tipo == 'caso' else {'avistamiento': objeto}
    pendientes = ContentReport.objects.filter(estado=ContentReport.Estado.PENDIENTE, **filtro).select_related('reportero')
    if not pendientes.exists():
        messages.info(request, 'No hay reportes pendientes sobre este contenido.')
        return redirect('moderation:reportes')
    form = ResolveReportForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        try:
            services.resolver_reportes(objeto, request.user, form.cleaned_data['accion'], form.cleaned_data['motivo'],
                                       form.cleaned_data['texto'], request)
        except ModeracionError as e:
            messages.error(request, str(e))
        else:
            messages.success(request, 'Decisión registrada.')
            return redirect('moderation:reportes')
    return render(request, 'moderation/reporte_resolver.html', {'objeto': objeto, 'tipo': tipo, 'reportes': pendientes, 'form': form})


# ---------------------------------------------------------------- solicitudes de datos (HU-14 CA6)
@admin_required
def solicitudes_datos(request):
    return render(request, 'moderation/solicitudes_datos.html', {'solicitudes': DataRequest.objects.select_related('usuario')[:100]})


@admin_required
@require_POST
def atender_solicitud(request, pk):
    s = get_object_or_404(DataRequest, pk=pk, estado=DataRequest.Estado.PENDIENTE)
    respuesta = request.POST.get('respuesta', '').strip()
    u = s.usuario
    if s.tipo == DataRequest.Tipo.ELIMINAR:
        email_original = u.email
        u.nombre, u.email, u.cedula, u.telefono, u.parentesco = 'Usuario eliminado', f'eliminado-{u.pk}@anonimo.invalid', None, '', ''
        u.is_active = False
        u.set_unusable_password()
        u.save()
        notificar(u, 'Solicitud atendida', 'Sus datos personales fueron suprimidos.', enviar_correo=False)
        from django.core.mail import send_mail  # el correo original ya no existe en la cuenta
        send_mail('Su solicitud de supresión de datos fue atendida', respuesta or 'Sus datos personales fueron suprimidos.',
                  settings.DEFAULT_FROM_EMAIL, [email_original], fail_silently=True)
    else:
        notificar(u, 'Su solicitud de corrección de datos fue atendida', respuesta or 'Un administrador atendió su solicitud.', '/cuentas/mis-datos/')
    s.estado, s.atendida_por, s.atendida_en, s.respuesta = DataRequest.Estado.ATENDIDA, request.user, timezone.now(), respuesta
    s.save()
    log(request.user, 'editar' if s.tipo == 'corregir' else 'eliminar', 'solicitud', s.pk,
        detalle=f'Solicitud {s.tipo} atendida (usuario #{u.pk})', request=request)
    messages.success(request, 'Solicitud atendida y registrada.')
    return redirect('moderation:solicitudes')
