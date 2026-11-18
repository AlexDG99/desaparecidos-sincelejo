def unread_notifications(request):
    user = getattr(request, 'user', None)
    if user is not None and user.is_authenticated:
        return {'notificaciones_sin_leer': user.notificaciones.filter(leida=False).count()}
    return {'notificaciones_sin_leer': 0}
