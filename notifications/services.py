import logging

from django.conf import settings
from django.core.mail import send_mail

from .models import Notification

logger = logging.getLogger(__name__)


def notificar(usuario, titulo, mensaje, url='', enviar_correo=True):
    """Crea la notificación en la plataforma y envía el correo con hasta 3 reintentos (HU-07 CA1, CA5).

    Si el correo falla, la notificación permanece disponible en la plataforma.
    """
    n = Notification.objects.create(usuario=usuario, titulo=titulo, mensaje=mensaje, url=url)
    if not enviar_correo:
        return n
    enlace = f'\n\nVer detalle: {settings.SITE_URL.rstrip("/")}{url}' if url else ''
    for _ in range(settings.EMAIL_SEND_ATTEMPTS):
        n.intentos_correo += 1
        try:
            send_mail(titulo, mensaje + enlace, settings.DEFAULT_FROM_EMAIL, [usuario.email])
            n.correo_enviado = True
            break
        except Exception as exc:  # noqa: BLE001 - cualquier fallo del servicio de correo se reintenta
            logger.warning('Fallo al enviar correo a %s (intento %s): %s', usuario.email, n.intentos_correo, exc)
    n.save(update_fields=['intentos_correo', 'correo_enviado'])
    return n
