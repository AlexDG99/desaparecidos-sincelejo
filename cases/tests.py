import csv
import io
from datetime import date, timedelta

from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone

from accounts.models import ConsentRecord
from audit.models import AuditEvent
from core.testing import BaseTestCase, archivo_imagen, imagen_bytes

from .models import Case, CasePhoto


def datos_caso(**extra):
    d = {'nombre': 'Luis Alberto Mendoza', 'edad': '35', 'sexo': 'M',
         'fecha_desaparicion': (date.today() - timedelta(days=2)).isoformat(), 'hora_aproximada': '18:30',
         'zona': 'Barrio La Pajuela', 'lugar': 'Cerca del parque', 'senas': 'Tatuaje en el brazo derecho',
         'vestimenta': 'Camisa azul', 'numero_denuncia': '', 'acepta_politica': 'on',
         'fotos': archivo_imagen('a.jpg')}
    d.update(extra)
    return d


class HU02CrearCasoTests(BaseTestCase):
    def setUp(self):
        self.fam = self.make_familiar()
        self.login(self.fam)

    def test_ca1_formulario_con_los_campos_requeridos(self):
        r = self.client.get(reverse('cases:crear'))
        for c in ('nombre', 'edad', 'sexo', 'fecha_desaparicion', 'hora_aproximada', 'zona', 'lugar', 'senas', 'vestimenta', 'fotos'):
            self.assertContains(r, f'name="{c}"')

    def test_ca2_campos_vacios_o_fecha_futura_no_registran_el_caso(self):
        r = self.client.post(reverse('cases:crear'), datos_caso(nombre='', senas=''))
        self.assertEqual(Case.objects.count(), 0)
        self.assertEqual(r.status_code, 200)
        r = self.client.post(reverse('cases:crear'), datos_caso(fecha_desaparicion=(date.today() + timedelta(days=1)).isoformat()))
        self.assertContains(r, 'no puede ser futura')
        self.assertEqual(Case.objects.count(), 0)

    def test_ca2_exige_al_menos_una_fotografia(self):
        d = datos_caso()
        d.pop('fotos')
        r = self.client.post(reverse('cases:crear'), d)
        self.assertContains(r, 'al menos una fotografía')
        self.assertEqual(Case.objects.count(), 0)

    def test_ca3_rechaza_formato_peso_y_cantidad_de_fotos(self):
        r = self.client.post(reverse('cases:crear'), datos_caso(fotos=SimpleUploadedFile('a.gif', b'GIF89a', content_type='image/gif')))
        self.assertContains(r, 'no es una imagen válida')
        grande = SimpleUploadedFile('g.jpg', imagen_bytes() + b'\0' * (5 * 1024 * 1024 + 1))
        r = self.client.post(reverse('cases:crear'), datos_caso(fotos=grande))
        self.assertContains(r, 'supera el tamaño máximo de 5 MB')
        cuatro = [archivo_imagen(f'f{i}.jpg') for i in range(4)]
        r = self.client.post(reverse('cases:crear'), datos_caso(fotos=cuatro))
        self.assertContains(r, 'máximo 3 fotografías')
        self.assertEqual(Case.objects.count(), 0)

    def test_ca3_rechaza_png_disfrazado_y_acepta_png_real(self):
        self.client.post(reverse('cases:crear'), datos_caso(fotos=SimpleUploadedFile('a.png', b'texto', content_type='image/png')))
        self.assertEqual(Case.objects.count(), 0)
        self.client.post(reverse('cases:crear'), datos_caso(fotos=archivo_imagen('a.png', 'PNG')))
        self.assertEqual(Case.objects.count(), 1)

    def test_ca4_caso_valido_queda_pendiente_con_codigo_unico(self):
        r = self.client.post(reverse('cases:crear'), datos_caso())
        self.assertEqual(r.status_code, 200)
        caso = Case.objects.get()
        self.assertEqual(caso.codigo, f'SIN-{timezone.localdate().year}-0001')
        self.assertEqual(caso.moderacion, Case.Moderacion.PENDIENTE)
        self.assertContains(r, caso.codigo)
        self.assertEqual(caso.fotos.count(), 1)
        self.client.post(reverse('cases:crear'), datos_caso(fotos=archivo_imagen('b.jpg')))
        self.assertEqual(Case.objects.order_by('id').last().codigo, f'SIN-{timezone.localdate().year}-0002')
        self.assertTrue(AuditEvent.objects.filter(accion='crear', entidad='caso', entidad_id=caso.pk).exists())

    def test_ca4_caso_pendiente_no_es_visible_al_publico(self):
        self.client.post(reverse('cases:crear'), datos_caso())
        caso = Case.objects.get()
        self.client.logout()
        self.assertEqual(self.client.get(caso.get_absolute_url()).status_code, 404)
        self.assertNotContains(self.client.get(reverse('cases:listado')), caso.nombre)

    def test_ca5_menor_de_edad_exige_calidad_y_autorizacion(self):
        r = self.client.post(reverse('cases:crear'), datos_caso(edad='10'))
        self.assertContains(r, 'Declare su calidad')
        self.assertContains(r, 'confirmar la autorización')
        self.assertEqual(Case.objects.count(), 0)
        r = self.client.post(reverse('cases:crear'), datos_caso(edad='10', calidad_declarada='Representante legal', autorizacion_menor='on'))
        caso = Case.objects.get()
        self.assertTrue(caso.es_menor and caso.autorizacion_menor)
        self.assertEqual(ConsentRecord.objects.filter(caso_id=caso.pk).count(), 2)  # tratamiento + difusión del menor

    def test_ca6_aviso_de_denuncia_y_campo_opcional(self):
        r = self.client.get(reverse('cases:crear'))
        self.assertContains(r, 'no sustituye la denuncia')
        self.assertContains(r, 'name="numero_denuncia"')

    def test_exige_aceptar_la_politica_de_datos(self):
        d = datos_caso()
        d.pop('acepta_politica')
        r = self.client.post(reverse('cases:crear'), d)
        self.assertContains(r, 'política de tratamiento')
        self.assertEqual(Case.objects.count(), 0)

    def test_fotos_sin_metadatos_exif_y_cifradas_en_disco(self):
        self.client.post(reverse('cases:crear'), datos_caso(fotos=archivo_imagen('a.jpg', exif=True)))
        foto = CasePhoto.objects.get()
        with foto.imagen.open('rb') as f:
            data = f.read()
        from PIL import Image
        img = Image.open(io.BytesIO(data))
        self.assertEqual(len(img.getexif()), 0)
        self.assertNotIn(b'CamaraSecreta', data)
        with open(foto.imagen.path, 'rb') as f:
            self.assertTrue(f.read().startswith(b'gAAAA'))

    def test_solo_familiares_pueden_crear(self):
        self.client.logout()
        self.login(self.make_user('c@example.com'))
        self.assertEqual(self.client.get(reverse('cases:crear')).status_code, 403)


class HU03ListadoTests(BaseTestCase):
    def setUp(self):
        self.a = self.make_case(nombre='José Ángel Pérez', zona='Barrio Majagual')
        self.b = self.make_case(nombre='María Camila Díaz', zona='Comuna 3', fecha_desaparicion=date.today() - timedelta(days=30), edad=15)
        self.pend = self.make_case(nombre='Pendiente Oculto', publicado=False)
        self.cerrado = self.make_case(nombre='Caso Cerrado Uno', estado=Case.Estado.VIVO)

    def test_ca1_listado_publico_solo_publicados_y_activos(self):
        r = self.client.get(reverse('cases:listado'))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'José Ángel Pérez')
        self.assertContains(r, 'María Camila Díaz')
        self.assertNotContains(r, 'Pendiente Oculto')
        self.assertNotContains(r, 'Caso Cerrado Uno')

    def test_ca1_orden_del_mas_reciente_al_mas_antiguo(self):
        r = self.client.get(reverse('cases:listado'))
        nombres = [c.nombre for c in r.context['page']]
        self.assertEqual(nombres, ['José Ángel Pérez', 'María Camila Díaz'])

    def test_ca1_paginado_de_a_12(self):
        for i in range(14):
            self.make_case(nombre=f'Persona {i:02d}', fecha_desaparicion=date.today() - timedelta(days=100 + i))
        r = self.client.get(reverse('cases:listado'))
        self.assertEqual(len(r.context['page']), 12)
        self.assertEqual(r.context['page'].paginator.num_pages, 2)
        self.assertEqual(len(self.client.get(reverse('cases:listado') + '?page=2').context['page']), 4)

    def test_ca2_busqueda_sin_distinguir_mayusculas_ni_tildes(self):
        for q in ('jose angel', 'JOSÉ ÁNGEL', 'jose', 'perez'):
            r = self.client.get(reverse('cases:listado'), {'q': q})
            self.assertContains(r, 'José Ángel Pérez')
            self.assertNotContains(r, 'María Camila')

    def test_ca3_filtros_combinados(self):
        r = self.client.get(reverse('cases:listado'), {'zona': 'majagual'})
        self.assertEqual([c.nombre for c in r.context['page']], ['José Ángel Pérez'])
        r = self.client.get(reverse('cases:listado'), {'desde': (date.today() - timedelta(days=10)).isoformat()})
        self.assertEqual([c.nombre for c in r.context['page']], ['José Ángel Pérez'])
        r = self.client.get(reverse('cases:listado'), {'hasta': (date.today() - timedelta(days=10)).isoformat()})
        self.assertEqual([c.nombre for c in r.context['page']], ['María Camila Díaz'])
        r = self.client.get(reverse('cases:listado'), {'zona': 'majagual', 'q': 'maria'})
        self.assertEqual(len(r.context['page']), 0)
        r = self.client.get(reverse('cases:listado'), {'estado': 'encontrado_vivo'})
        self.assertEqual([c.nombre for c in r.context['page']], ['Caso Cerrado Uno'])

    def test_ca4_sin_resultados_muestra_mensaje_y_limpiar_filtros(self):
        r = self.client.get(reverse('cases:listado'), {'q': 'zzzz'})
        self.assertContains(r, 'No se encontraron casos')
        self.assertContains(r, 'Limpiar filtros')

    def test_ca5_consulta_eficiente(self):
        with self.assertNumQueries(3):  # conteo, página y fotografías (prefetch): sin consultas N+1
            self.client.get(reverse('cases:listado'))

    def test_ca6_diseno_responsivo(self):
        r = self.client.get(reverse('cases:listado'))
        self.assertContains(r, 'name="viewport"')
        self.assertContains(r, 'row-cols-1')

    def test_el_listado_publico_no_expone_datos_sensibles(self):
        r = self.client.get(reverse('cases:listado'))
        self.assertNotContains(r, self.a.familiar.cedula)
        self.assertNotContains(r, self.a.familiar.telefono)
        self.assertNotContains(r, self.a.lugar)
        r = self.client.get(self.a.get_absolute_url())
        self.assertNotContains(r, self.a.familiar.cedula)
        self.assertNotContains(r, self.a.familiar.telefono)
        self.assertNotContains(r, self.a.familiar.email)

    def test_las_fotos_publicas_se_sirven_descifradas(self):
        foto = self.a.fotos.first()
        r = self.client.get(reverse('cases:foto', args=[self.a.codigo, foto.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r['Content-Type'], 'image/jpeg')
        self.assertTrue(b''.join(r.streaming_content).startswith(b'\xff\xd8'))

    def test_fotos_de_casos_no_publicados_son_privadas(self):
        foto = self.pend.fotos.first()
        self.assertEqual(self.client.get(reverse('cases:foto', args=[self.pend.codigo, foto.pk])).status_code, 404)
        self.login(self.pend.familiar)
        self.assertEqual(self.client.get(reverse('cases:foto', args=[self.pend.codigo, foto.pk])).status_code, 200)


class HU09CerrarCasoTests(BaseTestCase):
    def setUp(self):
        self.caso = self.make_case()
        self.av = self.make_sighting(self.caso)

    def test_ca1_ca2_titular_cierra_con_resultado_y_deja_de_ser_activo(self):
        self.login(self.caso.familiar)
        r = self.client.get(reverse('cases:cerrar', args=[self.caso.codigo]))
        self.assertContains(r, 'Encontrado con vida')
        self.assertContains(r, 'Encontrado sin vida')
        self.assertContains(r, 'Cerrado por otro motivo')
        r = self.client.post(reverse('cases:cerrar', args=[self.caso.codigo]), {'resultado': 'encontrado_vivo'})
        self.assertContains(r, 'Debe confirmar', status_code=200) if r.status_code == 200 else None
        self.caso.refresh_from_db()
        self.assertEqual(self.caso.estado, Case.Estado.ACTIVO)  # sin confirmar no se cierra
        self.client.post(reverse('cases:cerrar', args=[self.caso.codigo]), {'resultado': 'encontrado_vivo', 'confirmar': 'on'})
        self.caso.refresh_from_db()
        self.assertEqual(self.caso.estado, Case.Estado.VIVO)
        self.assertIsNotNone(self.caso.cerrado_en)
        self.assertNotContains(self.client.get(reverse('cases:listado')), self.caso.nombre)
        self.assertTrue(AuditEvent.objects.filter(accion='cerrar', entidad_id=self.caso.pk).exists())

    def test_ca3_historial_archivado_solo_para_titular_moderadores_y_admin(self):
        self.caso.estado = Case.Estado.VIVO
        self.caso.save()
        self.assertEqual(self.caso.avistamientos.count(), 1)  # se conserva
        self.assertNotContains(self.client.get(self.caso.get_absolute_url()), 'caminando por la plaza')
        self.login(self.caso.familiar)
        self.assertContains(self.client.get(self.caso.get_absolute_url()), 'caminando por la plaza')
        self.client.logout()
        self.login(self.make_moderador())
        self.assertContains(self.client.get(self.caso.get_absolute_url()), 'caminando por la plaza')

    def test_ca4_caso_cerrado_solo_muestra_nombre_y_estado(self):
        self.caso.estado = Case.Estado.VIVO
        self.caso.save()
        r = self.client.get(self.caso.get_absolute_url())
        self.assertContains(r, self.caso.nombre)
        self.assertContains(r, 'Encontrado con vida')
        self.assertNotContains(r, self.caso.senas)
        self.assertNotContains(r, self.caso.lugar)
        foto = self.caso.fotos.first()
        self.assertEqual(self.client.get(reverse('cases:foto', args=[self.caso.codigo, foto.pk])).status_code, 404)
        r = self.client.get(reverse('cases:listado'), {'estado': 'encontrado_vivo'})
        self.assertContains(r, self.caso.nombre)
        self.assertNotContains(r, '<img')

    def test_ca5_usuario_distinto_del_titular_no_puede_cerrar(self):
        self.login(self.make_user('otro@example.com'))
        self.assertEqual(self.client.post(reverse('cases:cerrar', args=[self.caso.codigo]), {'resultado': 'cerrado', 'confirmar': 'on'}).status_code, 403)
        self.caso.refresh_from_db()
        self.assertEqual(self.caso.estado, Case.Estado.ACTIVO)

    def test_ca6_solo_el_administrador_reabre(self):
        self.caso.estado = Case.Estado.CERRADO
        self.caso.save()
        self.login(self.caso.familiar)
        self.assertEqual(self.client.post(reverse('cases:reabrir', args=[self.caso.codigo])).status_code, 403)
        self.client.logout()
        self.login(self.make_admin())
        self.client.post(reverse('cases:reabrir', args=[self.caso.codigo]))
        self.caso.refresh_from_db()
        self.assertEqual(self.caso.estado, Case.Estado.ACTIVO)
        self.assertTrue(AuditEvent.objects.filter(accion='reabrir', entidad_id=self.caso.pk).exists())

    def test_administrador_tambien_puede_cerrar(self):
        self.login(self.make_admin())
        self.client.post(reverse('cases:cerrar', args=[self.caso.codigo]), {'resultado': 'cerrado', 'confirmar': 'on'})
        self.caso.refresh_from_db()
        self.assertEqual(self.caso.estado, Case.Estado.CERRADO)


class HU08MapaTests(BaseTestCase):
    def setUp(self):
        self.caso = self.make_case()

    def test_ca1_ca2_solo_avistamientos_aprobados_con_sus_datos(self):
        a = self.make_sighting(self.caso, latitud='9.30471', longitud='-75.39781', direccion='Parque Santander')
        self.make_sighting(self.caso, publicado=False)  # pendiente
        self.make_sighting(self.caso, moderacion='rechazado')
        self.make_sighting(self.caso, moderacion='sospechoso')
        d = self.client.get(reverse('cases:mapa_datos', args=[self.caso.codigo])).json()
        self.assertEqual(len(d['puntos']), 1)
        p = d['puntos'][0]
        self.assertEqual((p['fecha'], p['hora']), (a.fecha.strftime('%d/%m/%Y'), '10:30'))
        self.assertIn('plaza', p['descripcion'])
        self.assertEqual(p['ubicacion'], 'Parque Santander')

    def test_ca3_cronologia_en_orden_de_fecha_y_hora(self):
        self.make_sighting(self.caso, fecha=date.today() - timedelta(days=1), descripcion='Segundo avistamiento de prueba largo')
        self.make_sighting(self.caso, fecha=date.today() - timedelta(days=2), descripcion='Primer avistamiento de prueba largo!')
        pts = self.client.get(reverse('cases:mapa_datos', args=[self.caso.codigo])).json()['puntos']
        self.assertEqual([p['n'] for p in pts], [1, 2])
        self.assertIn('Primer', pts[0]['descripcion'])

    def test_ca4_sin_avistamientos_devuelve_lista_vacia_y_pagina_con_mensaje(self):
        self.assertEqual(self.client.get(reverse('cases:mapa_datos', args=[self.caso.codigo])).json()['puntos'], [])
        self.assertContains(self.client.get(reverse('cases:mapa', args=[self.caso.codigo])), 'todavía no tiene avistamientos aprobados')

    def test_ca6_la_ubicacion_publica_se_redondea_a_unos_100_metros(self):
        self.make_sighting(self.caso, latitud='9.304789', longitud='-75.397856')
        d = self.client.get(reverse('cases:mapa_datos', args=[self.caso.codigo])).json()
        p = d['puntos'][0]
        self.assertEqual((p['lat'], p['lng']), (9.305, -75.398))
        self.assertEqual(d['radio'], 100)

    def test_ca7_pagina_del_mapa_es_responsiva_y_accesible(self):
        r = self.client.get(reverse('cases:mapa', args=[self.caso.codigo]))
        self.assertContains(r, 'name="viewport"')
        self.assertContains(r, 'aria-label="Mapa interactivo de avistamientos"')

    def test_el_mapa_de_casos_no_publicados_no_es_publico(self):
        pend = self.make_case(publicado=False)
        self.assertEqual(self.client.get(reverse('cases:mapa_datos', args=[pend.codigo])).status_code, 404)


class HU11ExportarTests(BaseTestCase):
    def setUp(self):
        self.caso = self.make_case()
        self.ok = self.make_sighting(self.caso, descripcion='Avistamiento aprobado visible en la ficha exportada')
        self.pend = self.make_sighting(self.caso, publicado=False, descripcion='Avistamiento pendiente que no debe salir')
        self.rech = self.make_sighting(self.caso, moderacion='rechazado', descripcion='Avistamiento rechazado que no debe salir')

    def test_ca1_solo_el_administrador_ve_la_opcion(self):
        self.login(self.make_admin())
        self.assertContains(self.client.get(self.caso.get_absolute_url()), 'Exportar PDF')
        self.client.logout()
        self.login(self.caso.familiar)
        self.assertNotContains(self.client.get(self.caso.get_absolute_url()), 'Exportar PDF')

    def test_ca2_descarga_en_pdf_y_csv(self):
        self.login(self.make_admin())
        pdf = self.client.get(reverse('cases:exportar', args=[self.caso.codigo, 'pdf']))
        self.assertEqual(pdf['Content-Type'], 'application/pdf')
        self.assertTrue(pdf.content.startswith(b'%PDF'))
        csv_r = self.client.get(reverse('cases:exportar', args=[self.caso.codigo, 'csv']))
        self.assertIn('text/csv', csv_r['Content-Type'])
        self.assertEqual(self.client.get(reverse('cases:exportar', args=[self.caso.codigo, 'xml'])).status_code, 404)

    def test_ca3_ca4_csv_incluye_caso_y_solo_avistamientos_aprobados(self):
        self.login(self.make_admin())
        r = self.client.get(reverse('cases:exportar', args=[self.caso.codigo, 'csv']))
        filas = list(csv.DictReader(io.StringIO(r.content.decode('utf-8-sig'))))
        self.assertEqual(len(filas), 1)
        f = filas[0]
        self.assertEqual((f['codigo'], f['nombre'], f['edad']), (self.caso.codigo, self.caso.nombre, '30'))
        self.assertIn('aprobado visible', f['avistamiento_descripcion'])
        self.assertTrue(f['avistamiento_fecha'] and f['avistamiento_hora'] and f['avistamiento_latitud'] and f['generado_en'])
        self.assertNotIn('pendiente', r.content.decode())
        self.assertNotIn('rechazado que', r.content.decode())

    def test_ca3_pdf_incluye_fotografia_y_datos(self):
        self.login(self.make_admin())
        pdf = self.client.get(reverse('cases:exportar', args=[self.caso.codigo, 'pdf'])).content
        self.assertGreater(len(pdf), 2000)
        self.assertIn(b'/Image', pdf)

    def test_ca5_registra_la_exportacion_en_auditoria(self):
        admin = self.make_admin()
        self.login(admin)
        self.client.get(reverse('cases:exportar', args=[self.caso.codigo, 'pdf']))
        e = AuditEvent.objects.get(accion='exportar')
        self.assertEqual((e.usuario, e.caso_id, e.entidad), (admin, self.caso.pk, 'caso'))
        self.assertIn('PDF', e.detalle)

    def test_ca6_usuarios_sin_rol_de_administrador_no_pueden_exportar(self):
        for u in (self.make_moderador(), self.caso.familiar, self.make_user('c@example.com')):
            self.client.logout()
            self.login(u)
            self.assertEqual(self.client.get(reverse('cases:exportar', args=[self.caso.codigo, 'csv'])).status_code, 403)
        self.assertFalse(AuditEvent.objects.filter(accion='exportar').exists())

    def test_csv_sin_avistamientos_genera_una_fila(self):
        caso = self.make_case()
        self.login(self.make_admin())
        r = self.client.get(reverse('cases:exportar', args=[caso.codigo, 'csv']))
        self.assertEqual(len(list(csv.DictReader(io.StringIO(r.content.decode('utf-8-sig'))))), 1)
