import io
from datetime import date, timedelta
from unittest import mock

from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from audit.models import AuditEvent
from core.testing import BaseTestCase, archivo_imagen, archivo_mp4, imagen_bytes
from notifications.models import Notification

from .models import Sighting, SightingMedia


def datos_avistamiento(**extra):
    d = {'fecha': (date.today() - timedelta(days=1)).isoformat(), 'hora': '09:15', 'direccion': 'Cerca de la plaza',
         'latitud': '9.304700', 'longitud': '-75.397800',
         'descripcion': 'Vi a la persona caminando hacia el norte por la carrera 20, llevaba una mochila.'}
    d.update(extra)
    return d


class HU04AvistamientoTests(BaseTestCase):
    def setUp(self):
        self.caso = self.make_case()
        self.user = self.make_user('c@example.com')
        self.url = reverse('sightings:crear', args=[self.caso.codigo])

    def test_ca1_requiere_sesion_y_asocia_el_formulario_al_caso(self):
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 302)
        self.login(self.user)
        r = self.client.get(self.url)
        self.assertContains(r, self.caso.codigo)
        self.assertContains(r, 'name="direccion"')

    def test_el_centro_del_mapa_usa_punto_decimal_para_que_leaflet_lo_lea(self):
        import json
        import re
        self.login(self.user)
        html = self.client.get(self.url).content.decode()
        crudo = re.search(r'<script id="centro-mapa" type="application/json">(.*?)</script>', html, re.S).group(1)
        centro = json.loads(crudo)
        self.assertEqual(len(centro), 2)  # con coma decimal (es-CO) salían 4 números y el mapa no se dibujaba
        self.assertAlmostEqual(centro[0], 9.3047)

    def test_ca1_solo_casos_activos_y_publicados(self):
        self.login(self.user)
        cerrado = self.make_case(estado='cerrado')
        pendiente = self.make_case(publicado=False)
        for c in (cerrado, pendiente):
            self.assertEqual(self.client.get(reverse('sightings:crear', args=[c.codigo])).status_code, 404)

    def test_ca2_ubicacion_por_mapa_gps_o_direccion(self):
        self.login(self.user)
        for extra in ({'direccion': '', 'latitud': '9.3', 'longitud': '-75.39'}, {'direccion': 'Barrio Boston', 'latitud': '', 'longitud': ''}):
            self.client.post(self.url, datos_avistamiento(**extra))
        self.assertEqual(Sighting.objects.count(), 2)
        r = self.client.post(self.url, datos_avistamiento(direccion='', latitud='', longitud=''))
        self.assertContains(r, 'Indique la ubicación')
        self.assertEqual(Sighting.objects.count(), 2)

    def test_ca3_fecha_posterior_al_momento_actual_o_anterior_a_la_desaparicion(self):
        self.login(self.user)
        r = self.client.post(self.url, datos_avistamiento(fecha=(date.today() + timedelta(days=1)).isoformat()))
        self.assertContains(r, 'no pueden ser posteriores al momento actual')
        r = self.client.post(self.url, datos_avistamiento(fecha=(self.caso.fecha_desaparicion - timedelta(days=1)).isoformat()))
        self.assertContains(r, 'anterior a la fecha de desaparición')
        self.assertEqual(Sighting.objects.count(), 0)

    def test_ca3_hora_futura_hoy_se_rechaza(self):
        self.login(self.user)
        futura = (timezone.localtime() + timedelta(hours=2))
        if futura.date() == timezone.localdate():
            self.client.post(self.url, datos_avistamiento(fecha=date.today().isoformat(), hora=futura.strftime('%H:%M')))
            self.assertEqual(Sighting.objects.count(), 0)

    def test_ca4_descripcion_entre_20_y_1000_caracteres(self):
        self.login(self.user)
        r = self.client.post(self.url, datos_avistamiento(descripcion='muy corta'))
        self.assertContains(r, 'al menos 20 caracteres')
        r = self.client.post(self.url, datos_avistamiento(descripcion='x' * 1001))
        self.assertEqual(Sighting.objects.count(), 0)
        self.client.post(self.url, datos_avistamiento(descripcion='x' * 20))
        self.client.post(self.url, datos_avistamiento(descripcion='y' * 1000))
        self.assertEqual(Sighting.objects.count(), 2)

    def test_ca5_queda_pendiente_con_confirmacion_y_no_se_publica(self):
        self.login(self.user)
        r = self.client.post(self.url, datos_avistamiento())
        self.assertContains(r, 'Pendiente de moderación')
        av = Sighting.objects.get()
        self.assertEqual((av.moderacion, av.autor, av.caso), ('pendiente', self.user, self.caso))
        self.client.logout()
        self.assertNotContains(self.client.get(self.caso.get_absolute_url()), 'carrera 20')
        self.assertTrue(AuditEvent.objects.filter(accion='crear', entidad='avistamiento', entidad_id=av.pk).exists())
        self.assertEqual(Notification.objects.filter(usuario=self.caso.familiar).count(), 0)  # aún no se notifica

    def test_ca6_limite_de_5_avistamientos_por_hora(self):
        self.login(self.user)
        for _ in range(5):
            self.assertEqual(self.client.post(self.url, datos_avistamiento()).status_code, 200)
        r = self.client.post(self.url, datos_avistamiento())
        self.assertEqual(r.status_code, 429)
        self.assertContains(r, 'Demasiados avistamientos', status_code=429)
        self.assertEqual(Sighting.objects.count(), 5)

    def test_ca6_el_limite_vence_pasada_una_hora(self):
        self.login(self.user)
        for _ in range(5):
            self.client.post(self.url, datos_avistamiento())
        Sighting.objects.update(creado_en=timezone.now() - timedelta(hours=1, minutes=1))
        self.assertEqual(self.client.post(self.url, datos_avistamiento()).status_code, 200)
        self.assertEqual(Sighting.objects.count(), 6)

    @override_settings(SIGHTING_IP_RATE_LIMIT_PER_HOUR=3)
    def test_rnf10_limite_por_direccion_ip_aunque_cambien_de_cuenta(self):
        for i in range(3):
            self.client.logout()
            self.login(self.make_user(f'u{i}@example.com'))
            self.client.post(self.url, datos_avistamiento())
        self.client.logout()
        self.login(self.make_user('nuevo@example.com'))
        self.assertEqual(self.client.post(self.url, datos_avistamiento()).status_code, 429)

    def test_el_formulario_muestra_aviso_de_emergencias_123(self):
        self.login(self.user)
        self.assertContains(self.client.get(self.url), '123')


class HU05EvidenciaTests(BaseTestCase):
    def setUp(self):
        self.caso = self.make_case()
        self.user = self.make_user('c@example.com')
        self.login(self.user)
        self.url = reverse('sightings:crear', args=[self.caso.codigo])

    def enviar(self, archivos):
        return self.client.post(self.url, dict(datos_avistamiento(), evidencias=archivos))

    def test_ca1_hasta_3_archivos_imagenes_y_un_video(self):
        self.enviar([archivo_imagen('a.jpg'), archivo_imagen('b.png', 'PNG'), archivo_mp4()])
        av = Sighting.objects.get()
        self.assertEqual(av.archivos.count(), 3)
        self.assertEqual(av.archivos.filter(tipo='video').count(), 1)

    def test_ca1_rechaza_mas_de_3_archivos_y_mas_de_un_video(self):
        r = self.enviar([archivo_imagen(f'{i}.jpg') for i in range(4)])
        self.assertContains(r, 'máximo 3 archivos')
        r = self.enviar([archivo_mp4('a.mp4'), archivo_mp4('b.mp4')])
        self.assertContains(r, 'Solo puede adjuntar un video')
        self.assertEqual(Sighting.objects.count(), 0)

    def test_ca2_formato_o_tamano_no_permitido_conserva_el_formulario(self):
        r = self.enviar([SimpleUploadedFile('doc.pdf', b'%PDF-1.4')])
        self.assertContains(r, 'no es una imagen válida')
        self.assertContains(r, 'Vi a la persona caminando')  # el resto del formulario se conserva
        grande = SimpleUploadedFile('g.jpg', imagen_bytes() + b'\0' * (5 * 1024 * 1024 + 1))
        self.assertContains(self.enviar([grande]), 'supera el tamaño máximo de 5 MB')
        video = SimpleUploadedFile('v.mp4', b'\x00\x00\x00\x18ftypmp42' + b'\0' * (30 * 1024 * 1024))
        self.assertContains(self.enviar([video]), 'supera el tamaño máximo de 30 MB')
        falso = SimpleUploadedFile('v.mp4', b'esto no es un video')
        self.assertContains(self.enviar([falso]), 'no es un video MP4 válido')
        self.assertEqual(Sighting.objects.count(), 0)

    def test_ca3_el_formulario_incluye_progreso_con_cancelacion(self):
        r = self.client.get(self.url)
        self.assertContains(r, 'id="btn-cancelar"')
        self.assertContains(r, 'role="progressbar"')

    def test_ca4_se_eliminan_los_metadatos_exif(self):
        self.enviar([archivo_imagen('a.jpg', exif=True)])
        m = SightingMedia.objects.get()
        with m.archivo.open('rb') as f:
            data = f.read()
        from PIL import Image
        self.assertEqual(len(Image.open(io.BytesIO(data)).getexif()), 0)
        self.assertNotIn(b'CamaraSecreta', data)
        with open(m.archivo.path, 'rb') as f:
            self.assertTrue(f.read().startswith(b'gAAAA'))  # además, cifrado en reposo

    def test_ca5_moderador_ve_la_evidencia_y_el_publico_solo_tras_aprobar(self):
        self.enviar([archivo_imagen('a.jpg')])
        av = Sighting.objects.get()
        m = av.archivos.get()
        url = reverse('sightings:media', args=[m.pk])
        self.client.logout()
        self.assertEqual(self.client.get(url).status_code, 404)             # público, pendiente
        self.login(self.make_user('otro@example.com'))
        self.assertEqual(self.client.get(url).status_code, 404)             # otro ciudadano
        self.client.logout()
        self.login(self.make_moderador())
        self.assertEqual(self.client.get(url).status_code, 200)             # moderador
        self.client.logout()
        self.login(self.user)
        self.assertEqual(self.client.get(url).status_code, 200)             # el autor
        av.moderacion = 'publicado'
        av.save()
        self.client.logout()
        r = self.client.get(url)
        self.assertEqual(r.status_code, 200)                                # público tras aprobar
        self.assertTrue(b''.join(r.streaming_content).startswith(b'\xff\xd8'))

    def test_el_video_publico_se_sirve_como_mp4(self):
        self.enviar([archivo_mp4()])
        av = Sighting.objects.get()
        av.moderacion = 'publicado'
        av.save()
        self.client.logout()
        r = self.client.get(reverse('sightings:media', args=[av.archivos.get().pk]))
        self.assertEqual(r['Content-Type'], 'video/mp4')


class HU07NotificacionTests(BaseTestCase):
    def setUp(self):
        self.caso = self.make_case()
        self.fam = self.caso.familiar
        self.av = self.make_sighting(self.caso, publicado=False)
        self.mod = self.make_moderador()
        self.login(self.mod)

    def aprobar(self):
        return self.client.post(reverse('moderation:avistamiento', args=[self.av.pk]), {'accion': 'aprobar'})

    def test_ca1_al_aprobar_el_familiar_recibe_notificacion_y_correo(self):
        self.aprobar()
        n = Notification.objects.get(usuario=self.fam)
        self.assertIn(self.caso.codigo, n.titulo)
        self.assertTrue(n.correo_enviado)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.fam.email])

    def test_ca2_resumen_con_fecha_hora_lugar_y_enlace(self):
        self.aprobar()
        n = Notification.objects.get(usuario=self.fam)
        self.assertIn(self.av.fecha.strftime('%d/%m/%Y'), n.mensaje)
        self.assertIn('10:30', n.mensaje)
        self.assertIn('Plaza principal', n.mensaje)
        self.assertIn(f'/casos/{self.caso.codigo}/', n.url)
        self.assertIn(n.url, mail.outbox[0].body)

    def test_ca3_listado_con_no_leidas_destacadas_y_marcar_como_leidas(self):
        self.aprobar()
        self.client.logout()
        self.login(self.fam)
        r = self.client.get(reverse('notifications:listado'))
        self.assertContains(r, 'notif-unread')
        self.assertContains(r, 'Nueva')
        self.assertEqual(r.context['notificaciones_sin_leer'], 1)
        n = Notification.objects.get(usuario=self.fam)
        self.client.post(reverse('notifications:leida', args=[n.pk]))
        n.refresh_from_db()
        self.assertTrue(n.leida)
        Notification.objects.create(usuario=self.fam, titulo='x', mensaje='y')
        self.client.post(reverse('notifications:todas'))
        self.assertEqual(self.fam.notificaciones.filter(leida=False).count(), 0)

    def test_ca3_abrir_marca_leida_y_redirige_al_detalle(self):
        self.aprobar()
        self.client.logout()
        self.login(self.fam)
        n = Notification.objects.get(usuario=self.fam)
        r = self.client.get(reverse('notifications:abrir', args=[n.pk]))
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r['Location'], n.url)
        n.refresh_from_db()
        self.assertTrue(n.leida)

    def test_un_usuario_no_puede_leer_notificaciones_ajenas(self):
        self.aprobar()
        n = Notification.objects.get(usuario=self.fam)
        self.client.logout()
        self.login(self.make_user('otro@example.com'))
        self.assertEqual(self.client.get(reverse('notifications:abrir', args=[n.pk])).status_code, 404)

    def test_ca4_avistamiento_rechazado_no_notifica_al_familiar(self):
        self.client.post(reverse('moderation:avistamiento', args=[self.av.pk]), {'accion': 'rechazar', 'motivo': 'Información falsa'})
        self.assertEqual(Notification.objects.filter(usuario=self.fam).count(), 0)
        self.assertEqual(Notification.objects.filter(usuario=self.av.autor).count(), 1)  # solo se informa al autor

    def test_ca5_si_el_correo_falla_reintenta_3_veces_y_conserva_la_notificacion(self):
        with mock.patch('notifications.services.send_mail', side_effect=OSError('SMTP caído')) as m:
            self.aprobar()
        self.assertEqual(m.call_count, 3)
        n = Notification.objects.get(usuario=self.fam)
        self.assertEqual((n.intentos_correo, n.correo_enviado), (3, False))
        self.client.logout()
        self.login(self.fam)
        self.assertContains(self.client.get(reverse('notifications:listado')), self.caso.codigo)  # sigue disponible en la plataforma

    def test_ca5_si_el_segundo_intento_funciona_no_se_reintenta_mas(self):
        real = mail.send_mail
        llamadas = {'n': 0}

        def a_veces(*a, **k):
            llamadas['n'] += 1
            if llamadas['n'] == 1:
                raise OSError('fallo transitorio')
            return real(*a, **k)

        with mock.patch('notifications.services.send_mail', side_effect=a_veces):
            self.aprobar()
        n = Notification.objects.get(usuario=self.fam)
        self.assertEqual((n.intentos_correo, n.correo_enviado), (2, True))

    def test_ca1_la_notificacion_es_inmediata(self):
        antes = timezone.now()
        self.aprobar()
        n = Notification.objects.get(usuario=self.fam)
        self.assertLess((n.creada_en - antes).total_seconds(), 300)


class HU15MisAvistamientosTests(BaseTestCase):
    """HU-15: el usuario consulta el estado de los avistamientos que ha enviado."""

    def setUp(self):
        self.caso = self.make_case()
        self.user = self.make_user('c@example.com')
        self.url = reverse('sightings:mis_avistamientos')

    def test_ca1_requiere_sesion(self):
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 302)
        self.assertIn(reverse('accounts:login'), r['Location'])

    def test_ca2_lista_solo_mis_avistamientos_con_el_codigo_del_caso_y_su_estado(self):
        mio = self.make_sighting(self.caso, autor=self.user, publicado=False)
        ajeno = self.make_sighting(self.caso, autor=self.make_user('otro@example.com'), descripcion='Texto del otro usuario')
        self.login(self.user)
        r = self.client.get(self.url)
        self.assertEqual(list(r.context['avistamientos']), [mio])
        self.assertContains(r, self.caso.codigo)
        self.assertContains(r, 'Pendiente de moderación')
        self.assertNotContains(r, ajeno.descripcion)

    def test_ca3_un_avistamiento_rechazado_muestra_el_motivo(self):
        self.make_sighting(self.caso, autor=self.user, publicado=False, moderacion='rechazado', moderacion_motivo='Datos incoherentes')
        self.login(self.user)
        self.assertContains(self.client.get(self.url), 'Datos incoherentes')

    def test_ca4_sin_avistamientos_muestra_un_mensaje(self):
        self.login(self.user)
        self.assertContains(self.client.get(self.url), 'Aún no ha enviado avistamientos')

    def test_ca5_el_menu_tiene_el_enlace_para_usuarios_con_sesion(self):
        self.login(self.user)
        self.assertContains(self.client.get(reverse('cases:home')), 'Mis avistamientos')
