"""Exportación de la ficha de un caso (HU-11): PDF legible y CSV estructurado.

Solo incluye avistamientos aprobados (HU-11 CA4). Los campos se alinearán con los que solicita el SIRDEC
una vez se validen con el enlace institucional.
"""
import csv
import io

from django.http import HttpResponse
from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

CASO_COLUMNAS = ['codigo', 'nombre', 'edad', 'sexo', 'fecha_desaparicion', 'hora_aproximada', 'zona', 'lugar',
                 'senas', 'vestimenta', 'numero_denuncia', 'estado', 'menor_de_edad']
AVISTAMIENTO_COLUMNAS = ['avistamiento_id', 'avistamiento_fecha', 'avistamiento_hora', 'avistamiento_latitud',
                         'avistamiento_longitud', 'avistamiento_direccion', 'avistamiento_descripcion']


def _avistamientos(caso):
    return caso.avistamientos.filter(moderacion='publicado').order_by('fecha', 'hora')


def _fila_caso(caso):
    return [caso.codigo, caso.nombre, caso.edad, caso.get_sexo_display(), caso.fecha_desaparicion.isoformat(),
            caso.hora_aproximada.strftime('%H:%M') if caso.hora_aproximada else '', caso.zona, caso.lugar,
            caso.senas, caso.vestimenta, caso.numero_denuncia, caso.get_estado_display(), 'sí' if caso.es_menor else 'no']


def caso_a_csv(caso):
    resp = HttpResponse(content_type='text/csv; charset=utf-8')
    resp['Content-Disposition'] = f'attachment; filename="{caso.codigo}.csv"'
    resp.write('﻿')
    w = csv.writer(resp)
    w.writerow(CASO_COLUMNAS + AVISTAMIENTO_COLUMNAS + ['generado_en'])
    generado = timezone.localtime().strftime('%Y-%m-%d %H:%M:%S')
    base = _fila_caso(caso)
    avs = list(_avistamientos(caso))
    if not avs:
        w.writerow(base + [''] * len(AVISTAMIENTO_COLUMNAS) + [generado])
    for a in avs:
        w.writerow(base + [a.pk, a.fecha.isoformat(), a.hora.strftime('%H:%M'), a.latitud or '', a.longitud or '',
                           a.direccion, a.descripcion, generado])
    return resp


def caso_a_pdf(caso):
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter, leftMargin=2 * cm, rightMargin=2 * cm, topMargin=2 * cm, bottomMargin=2 * cm,
                            title=f'Ficha del caso {caso.codigo}')
    st = getSampleStyleSheet()
    celda = st['BodyText']
    story = [Paragraph(f'Ficha del caso {caso.codigo}', st['Title']),
             Paragraph('Sistema de Reporte de Personas Desaparecidas y Avistamientos — Sincelejo', st['Normal']),
             Paragraph(f'Generada el {timezone.localtime():%d/%m/%Y %H:%M}', st['Normal']), Spacer(1, 12)]
    filas = [['Nombre', caso.nombre], ['Edad', str(caso.edad)], ['Sexo', caso.get_sexo_display()],
             ['Fecha de desaparición', caso.fecha_desaparicion.strftime('%d/%m/%Y')],
             ['Hora aproximada', caso.hora_aproximada.strftime('%H:%M') if caso.hora_aproximada else '—'],
             ['Zona', caso.zona], ['Lugar', caso.lugar], ['Señas particulares', caso.senas],
             ['Vestimenta', caso.vestimenta or '—'], ['N.º de denuncia', caso.numero_denuncia or '—'],
             ['Estado', caso.get_estado_display()], ['Menor de edad', 'Sí' if caso.es_menor else 'No']]
    t = Table([[Paragraph(f'<b>{k}</b>', celda), Paragraph(v, celda)] for k, v in filas], colWidths=[5 * cm, 12 * cm])
    t.setStyle(TableStyle([('GRID', (0, 0), (-1, -1), 0.5, colors.grey), ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                           ('BACKGROUND', (0, 0), (0, -1), colors.whitesmoke)]))
    story += [t, Spacer(1, 12)]
    for f in caso.fotos.all():
        try:
            with f.imagen.open('rb') as fh:
                data = fh.read()
            iw, ih = ImageReader(io.BytesIO(data)).getSize()
            ancho = min(8 * cm, iw)
            story += [Image(io.BytesIO(data), width=ancho, height=ancho * ih / iw), Spacer(1, 8)]
        except Exception:  # noqa: BLE001 - una foto ilegible no debe impedir la exportación
            continue
    story.append(Paragraph('Avistamientos aprobados', st['Heading2']))
    avs = list(_avistamientos(caso))
    if not avs:
        story.append(Paragraph('El caso no tiene avistamientos aprobados.', st['Normal']))
    else:
        datos = [[Paragraph('<b>Fecha y hora</b>', celda), Paragraph('<b>Ubicación</b>', celda), Paragraph('<b>Descripción</b>', celda)]]
        for a in avs:
            ubic = a.direccion or ''
            if a.latitud is not None and a.longitud is not None:
                ubic = f'{ubic} ({float(a.latitud):.5f}, {float(a.longitud):.5f})'.strip()
            datos.append([Paragraph(f'{a.fecha:%d/%m/%Y} {a.hora:%H:%M}', celda), Paragraph(ubic or '—', celda),
                          Paragraph(a.descripcion, celda)])
        t2 = Table(datos, colWidths=[3.5 * cm, 5 * cm, 8.5 * cm], repeatRows=1)
        t2.setStyle(TableStyle([('GRID', (0, 0), (-1, -1), 0.5, colors.grey), ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                                ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey)]))
        story.append(t2)
    doc.build(story)
    resp = HttpResponse(buf.getvalue(), content_type='application/pdf')
    resp['Content-Disposition'] = f'attachment; filename="{caso.codigo}.pdf"'
    return resp
