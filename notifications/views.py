from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .models import Notification


@login_required
def listado(request):
    return render(request, 'notifications/listado.html', {'notificaciones': request.user.notificaciones.all()[:100]})


@login_required
def abrir(request, pk):
    n = get_object_or_404(Notification, pk=pk, usuario=request.user)
    if not n.leida:
        n.leida = True
        n.save(update_fields=['leida'])
    return redirect(n.url or 'notifications:listado')


@login_required
@require_POST
def marcar_leida(request, pk):
    Notification.objects.filter(pk=pk, usuario=request.user).update(leida=True)
    return redirect('notifications:listado')


@login_required
@require_POST
def marcar_todas(request):
    request.user.notificaciones.filter(leida=False).update(leida=True)
    return redirect('notifications:listado')
