from core.utils import get_client_ip

from .models import AuditEvent


def log(usuario, accion, entidad, entidad_id=None, caso_id=None, detalle='', request=None, ip=None):
    """Registra un evento de auditoría (HU-12 CA1): usuario, rol, fecha/hora, acción, entidad e IP."""
    if ip is None and request is not None:
        ip = get_client_ip(request)
    authenticated = bool(usuario and getattr(usuario, 'pk', None))
    return AuditEvent.objects.create(
        usuario=usuario if authenticated else None,
        usuario_email=usuario.email if authenticated else '',
        rol=usuario.rol if authenticated else '',
        accion=accion, entidad=entidad, entidad_id=entidad_id, caso_id=caso_id,
        detalle=detalle[:2000], ip=ip)
