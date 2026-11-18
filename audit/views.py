import csv
from datetime import datetime, time

from django.core.paginator import Paginator
from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone

from core.permissions import admin_required

from .models import AuditEvent


def _filtrar(request):
    qs = AuditEvent.objects.all()
    g = request.GET
    if g.get('usuario'):
        qs = qs.filter(usuario_email__icontains=g['usuario'].strip())
    if g.get('accion'):
        qs = qs.filter(accion=g['accion'])
    if g.get('entidad'):
        qs = qs.filter(entidad=g['entidad'])
    tz = timezone.get_current_timezone()
    try:
        if g.get('desde'):
            qs = qs.filter(creado_en__gte=datetime.combine(datetime.strptime(g['desde'], '%Y-%m-%d').date(), time.min, tz))
        if g.get('hasta'):
            qs = qs.filter(creado_en__lte=datetime.combine(datetime.strptime(g['hasta'], '%Y-%m-%d').date(), time.max, tz))
    except ValueError:
        pass
    return qs


@admin_required
def listado(request):
    qs = _filtrar(request)
    page = Paginator(qs, 50).get_page(request.GET.get('page'))
    params = request.GET.copy()
    params.pop('page', None)
    entidades = AuditEvent.objects.order_by().values_list('entidad', flat=True).distinct()
    return render(request, 'audit/listado.html', {
        'page': page, 'acciones': AuditEvent.Accion.choices, 'entidades': entidades,
        'querystring': params.urlencode(), 'filtros': request.GET})


@admin_required
def exportar_csv(request):
    """HU-12 CA5: exportar el resultado filtrado en CSV."""
    resp = HttpResponse(content_type='text/csv; charset=utf-8')
    resp['Content-Disposition'] = 'attachment; filename="auditoria.csv"'
    resp.write('﻿')
    w = csv.writer(resp)
    w.writerow(['fecha_hora', 'usuario', 'rol', 'accion', 'entidad', 'entidad_id', 'caso_id', 'ip', 'detalle'])
    for e in _filtrar(request).iterator():
        w.writerow([timezone.localtime(e.creado_en).strftime('%Y-%m-%d %H:%M:%S'), e.usuario_email, e.rol, e.accion,
                    e.entidad, e.entidad_id or '', e.caso_id or '', e.ip or '', e.detalle])
    return resp
