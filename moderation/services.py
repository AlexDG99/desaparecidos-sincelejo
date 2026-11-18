"""Reglas de negocio de la moderación (HU-06, HU-10, HU-14) con auditoría y notificaciones."""
from django.conf import settings
from django.utils import timezone

from accounts.models import User
from audit.services import log
from cases.models import Case
from notifications.services import notificar
from sightings.models import Sighting

from .models import ContentReport


class ModeracionError(Exception):
    pass


def _marcar(obj, moderador, estado, motivo=''):
    obj.moderacion = estado
    obj.moderacion_motivo = motivo
    obj.moderado_por = moderador
    obj.moderado_en = timezone.now()
    obj.save(update_fields=['moderacion', 'moderacion_motivo', 'moderado_por', 'moderado_en'])


def puede_gestionar(user, obj):
    """Los moderadores gestionan lo pendiente; lo marcado como sospechoso se escala al administrador (HU-06 CA5)."""
    if obj.moderacion == 'sospechoso':
        return user.es_administrador
    return user.es_moderador and obj.moderacion in ('pendiente', 'publicado')


# ---------------------------------------------------------------- casos
def aprobar_caso(caso, moderador, request=None):
    if caso.es_menor and not caso.autorizacion_menor:  # HU-14 CA3
        raise ModeracionError('El caso es de un menor de edad y no tiene registrada la autorización de difusión.')
    _marcar(caso, moderador, Case.Moderacion.PUBLICADO)
    log(moderador, 'aprobar', 'caso', caso.pk, caso_id=caso.pk, detalle=f'Caso {caso.codigo} aprobado', request=request)
    notificar(caso.familiar, f'Su caso {caso.codigo} fue publicado',
              'Un moderador aprobó su caso. Ya es visible para la ciudadanía.', caso.get_absolute_url())


def rechazar_caso(caso, moderador, motivo, request=None):
    motivo = (motivo or '').strip()
    if not motivo:
        raise ModeracionError('Debe indicar el motivo del rechazo.')
    _marcar(caso, moderador, Case.Moderacion.RECHAZADO, motivo)
    log(moderador, 'rechazar', 'caso', caso.pk, caso_id=caso.pk, detalle=f'Rechazado: {motivo}', request=request)
    notificar(caso.familiar, f'Su caso {caso.codigo} no fue publicado', f'Motivo del rechazo: {motivo}', '/mis-casos/')


def sospechoso_caso(caso, moderador, request=None):
    _marcar(caso, moderador, Case.Moderacion.SOSPECHOSO)
    log(moderador, 'sospechoso', 'caso', caso.pk, caso_id=caso.pk, detalle='Escalado al administrador', request=request)


# ---------------------------------------------------------------- avistamientos
def aprobar_avistamiento(av, moderador, request=None):
    _marcar(av, moderador, Sighting.Moderacion.PUBLICADO)
    log(moderador, 'aprobar', 'avistamiento', av.pk, caso_id=av.caso_id, detalle=f'Avistamiento #{av.pk} aprobado', request=request)
    # HU-07: el familiar es notificado cuando el avistamiento ya fue verificado y publicado
    notificar(av.caso.familiar, f'Nuevo avistamiento en el caso {av.caso.codigo}',
              f'Se publicó un avistamiento el {av.fecha:%d/%m/%Y} a las {av.hora:%H:%M}. '
              f'Lugar aproximado: {av.ubicacion_resumen}.', av.get_absolute_url())


def rechazar_avistamiento(av, moderador, motivo, request=None):
    motivo = (motivo or '').strip()
    if not motivo:
        raise ModeracionError('Debe indicar el motivo del rechazo.')
    _marcar(av, moderador, Sighting.Moderacion.RECHAZADO, motivo)
    log(moderador, 'rechazar', 'avistamiento', av.pk, caso_id=av.caso_id, detalle=f'Rechazado: {motivo}', request=request)
    # solo se notifica al autor; el familiar no recibe alertas por reportes rechazados (HU-07 CA4)
    notificar(av.autor, 'Su avistamiento no fue publicado', f'Motivo del rechazo: {motivo}', av.caso.get_absolute_url())


def sospechoso_avistamiento(av, moderador, request=None):
    _marcar(av, moderador, Sighting.Moderacion.SOSPECHOSO)
    log(moderador, 'sospechoso', 'avistamiento', av.pk, caso_id=av.caso_id, detalle='Escalado al administrador', request=request)


# ---------------------------------------------------------------- verificación de identidad (HU-01)
def aprobar_verificacion(usuario, moderador, request=None):
    usuario.verificacion = User.Verificacion.VERIFICADA
    usuario.verificacion_motivo = ''
    usuario.save()
    log(moderador, 'verificar', 'usuario', usuario.pk, detalle='Identidad verificada', request=request)
    notificar(usuario, 'Su identidad fue verificada', 'Ya puede publicar casos de desaparición.', '/casos/nuevo/')


def rechazar_verificacion(usuario, moderador, motivo, request=None):
    motivo = (motivo or '').strip()
    if not motivo:
        raise ModeracionError('Debe indicar el motivo del rechazo.')
    usuario.verificacion = User.Verificacion.RECHAZADA
    usuario.verificacion_motivo = motivo
    usuario.save()
    log(moderador, 'rechazar', 'usuario', usuario.pk, detalle=f'Verificación rechazada: {motivo}', request=request)
    notificar(usuario, 'No pudimos verificar su identidad',
              f'Motivo: {motivo}. Puede corregir sus datos y volver a enviarlos desde la plataforma.', '/cuentas/verificacion/reenviar/')


# ---------------------------------------------------------------- reportes de contenido (HU-10)
def grupos_de_reportes():
    """Agrupa los reportes pendientes por contenido; prioridad alta al alcanzar el umbral de reportantes distintos."""
    grupos = {}
    qs = ContentReport.objects.filter(estado=ContentReport.Estado.PENDIENTE).select_related('reportero', 'caso', 'avistamiento__caso')
    for r in qs:
        clave = ('caso', r.caso_id) if r.caso_id else ('avistamiento', r.avistamiento_id)
        g = grupos.setdefault(clave, {'tipo': clave[0], 'objeto': r.objetivo, 'reportes': [], 'reporteros': set()})
        g['reportes'].append(r)
        g['reporteros'].add(r.reportero_id)
    resultado = []
    for g in grupos.values():
        g['prioridad_alta'] = len(g['reporteros']) >= settings.CONTENT_REPORT_ESCALATION_THRESHOLD
        g['primero'] = min(r.creado_en for r in g['reportes'])
        resultado.append(g)
    resultado.sort(key=lambda g: (not g['prioridad_alta'], g['primero']))
    return resultado


def resolver_reportes(objeto, moderador, accion, motivo='', texto='', request=None):
    tipo = 'caso' if isinstance(objeto, Case) else 'avistamiento'
    filtro = {'caso': objeto} if tipo == 'caso' else {'avistamiento': objeto}
    reportes = ContentReport.objects.filter(estado=ContentReport.Estado.PENDIENTE, **filtro)
    caso_id = objeto.pk if tipo == 'caso' else objeto.caso_id
    if accion == 'mantener':
        nuevo = ContentReport.Estado.MANTENIDO
        detalle = 'Contenido mantenido tras revisar reportes'
    elif accion == 'editar':
        texto = (texto or '').strip()
        if not texto:
            raise ModeracionError('Escriba el nuevo texto para editar el contenido.')
        if tipo == 'caso':
            objeto.senas = texto
            objeto.save(update_fields=['senas', 'actualizado_en'])
        else:
            objeto.descripcion = texto[:1000]
            objeto.save(update_fields=['descripcion'])
        nuevo = ContentReport.Estado.EDITADO
        detalle = 'Contenido editado tras revisar reportes'
    elif accion == 'retirar':
        motivo = (motivo or '').strip()
        if not motivo:
            raise ModeracionError('Debe indicar el motivo del retiro.')
        _marcar(objeto, moderador, 'rechazado', f'Retirado por reportes: {motivo}')
        nuevo = ContentReport.Estado.RETIRADO
        detalle = f'Contenido retirado: {motivo}'
        destinatario = objeto.familiar if tipo == 'caso' else objeto.autor
        notificar(destinatario, 'Se retiró un contenido que usted publicó', f'Motivo: {motivo}', '/')
    else:
        raise ModeracionError('Acción no válida.')
    reportes.update(estado=nuevo, resuelto_por=moderador, resuelto_en=timezone.now())
    log(moderador, 'editar' if accion == 'editar' else ('eliminar' if accion == 'retirar' else 'aprobar'), tipo, objeto.pk,
        caso_id=caso_id, detalle=detalle, request=request)
