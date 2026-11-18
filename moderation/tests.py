from datetime import timedelta

from django.core import mail
from django.urls import reverse
from django.utils import timezone

from audit.models import AuditEvent
from cases.models import Case
from core.testing import BaseTestCase
from notifications.models import Notification
from sightings.models import Sighting

from .models import ContentReport


class HU06ModeracionTests(BaseTestCase):
    def setUp(self):
        self.mod = self.make_moderador()
        self.fam = self.make_familiar()
        self.login(self.mod)

    def test_ca1_cola_ordenada_del_mas_antiguo_al_mas_reciente_con_datos(self):
        nuevo = self.make_case(self.fam, publicado=False, nombre='Caso Nuevo')
        viejo_av = self.make_sighting(self.make_case(), publicado=False)
        medio = self.make_case(publicado=False, nombre='Caso Medio')
        ahora = timezone.now()
        Sighting.objects.filter(pk=viejo_av.pk).update(creado_en=ahora - timedelta(hours=5))
        Case.objects.filter(pk=medio.pk).update(creado_en=ahora - timedelta(hours=2))
        Case.objects.filter(pk=nuevo.pk).update(creado_en=ahora - timedelta(minutes=5))
        r = self.client.get(reverse('moderation:cola'))
        self.assertEqual([i['tipo'] for i in r.context['items']], ['Avistamiento', 'Caso', 'Caso'])
        self.assertEqual([i['creado_en'] for i in r.context['items']], sorted(i['creado_en'] for i in r.context['items']))
        self.assertContains(r, 'Caso Medio')
        self.assertContains(r, self.fam.nombre)
        self.assertContains(r, 'Enviado')

    def test_ca1_la_cola_no_incluye_lo_ya_gestionado(self):
        self.make_case(publicado=True, nombre='Ya Publicado')
        self.assertNotContains(self.client.get(reverse('moderation:cola')), 'Ya Publicado')

    def test_ca1_marca_los_reportes_que_exceden_la_meta_de_24_horas(self):
        c = self.make_case(publicado=False)
        Case.objects.filter(pk=c.pk).update(creado_en=timezone.now() - timedelta(hours=30))
        self.assertContains(self.client.get(reverse('moderation:cola')), 'Excede 24 h')

    def test_ca2_detalle_con_datos_adjuntos_y_acciones(self):
        av = self.make_sighting(self.make_case(), publicado=False)
        r = self.client.get(reverse('moderation:avistamiento', args=[av.pk]))
        for texto in ('Aprobar y publicar', 'Rechazar', 'Marcar como sospechoso', av.descripcion[:30]):
            self.assertContains(r, texto)

    def test_ca3_aprobar_publica_el_caso(self):
        caso = self.make_case(self.fam, publicado=False)
        self.client.post(reverse('moderation:caso', args=[caso.pk]), {'accion': 'aprobar'})
        caso.refresh_from_db()
        self.assertEqual((caso.moderacion, caso.moderado_por), ('publicado', self.mod))
        self.assertIsNotNone(caso.moderado_en)
        self.client.logout()
        self.assertContains(self.client.get(caso.get_absolute_url()), caso.nombre)
        self.assertTrue(Notification.objects.filter(usuario=self.fam, titulo__contains=caso.codigo).exists())

    def test_ca3_aprobar_avistamiento_lo_hace_visible(self):
        caso = self.make_case()
        av = self.make_sighting(caso, publicado=False)
        self.client.post(reverse('moderation:avistamiento', args=[av.pk]), {'accion': 'aprobar'})
        av.refresh_from_db()
        self.assertEqual(av.moderacion, 'publicado')
        self.client.logout()
        self.assertContains(self.client.get(caso.get_absolute_url()), 'caminando por la plaza')

    def test_ca4_rechazar_exige_motivo_y_notifica_al_autor(self):
        caso = self.make_case(self.fam, publicado=False)
        r = self.client.post(reverse('moderation:caso', args=[caso.pk]), {'accion': 'rechazar', 'motivo': '  '}, follow=True)
        self.assertContains(r, 'Debe indicar el motivo')
        caso.refresh_from_db()
        self.assertEqual(caso.moderacion, 'pendiente')
        self.client.post(reverse('moderation:caso', args=[caso.pk]), {'accion': 'rechazar', 'motivo': 'Foto no corresponde'})
        caso.refresh_from_db()
        self.assertEqual((caso.moderacion, caso.moderacion_motivo), ('rechazado', 'Foto no corresponde'))
        self.assertTrue(any('Foto no corresponde' in m.body and m.to == [self.fam.email] for m in mail.outbox))
        self.client.logout()
        self.assertEqual(self.client.get(caso.get_absolute_url()).status_code, 404)

    def test_ca4_rechazar_avistamiento_notifica_al_autor_con_la_razon(self):
        av = self.make_sighting(self.make_case(), publicado=False)
        self.client.post(reverse('moderation:avistamiento', args=[av.pk]), {'accion': 'rechazar', 'motivo': 'Datos incoherentes'})
        n = Notification.objects.get(usuario=av.autor)
        self.assertIn('Datos incoherentes', n.mensaje)

    def test_ca5_sospechoso_queda_oculto_y_se_escala_al_administrador(self):
        av = self.make_sighting(self.make_case(), publicado=False)
        self.client.post(reverse('moderation:avistamiento', args=[av.pk]), {'accion': 'sospechoso'})
        av.refresh_from_db()
        self.assertEqual(av.moderacion, 'sospechoso')
        self.client.logout()
        self.assertNotContains(self.client.get(av.caso.get_absolute_url()), 'caminando por la plaza')
        # el moderador ya no lo ve en su cola ni puede decidir sobre él
        self.login(self.mod)
        self.assertEqual(len(self.client.get(reverse('moderation:cola')).context['items']), 0)
        self.client.post(reverse('moderation:avistamiento', args=[av.pk]), {'accion': 'aprobar'})
        av.refresh_from_db()
        self.assertEqual(av.moderacion, 'sospechoso')
        # el administrador sí lo ve y puede resolverlo
        self.client.logout()
        self.login(self.make_admin())
        self.assertEqual(len(self.client.get(reverse('moderation:cola')).context['items']), 1)
        self.client.post(reverse('moderation:avistamiento', args=[av.pk]), {'accion': 'aprobar'})
        av.refresh_from_db()
        self.assertEqual(av.moderacion, 'publicado')

    def test_ca6_cada_decision_queda_en_auditoria_con_quien_cuando_y_que(self):
        caso = self.make_case(self.fam, publicado=False)
        av = self.make_sighting(self.make_case(), publicado=False)
        self.client.post(reverse('moderation:caso', args=[caso.pk]), {'accion': 'aprobar'})
        self.client.post(reverse('moderation:avistamiento', args=[av.pk]), {'accion': 'rechazar', 'motivo': 'Spam'})
        e1 = AuditEvent.objects.get(accion='aprobar', entidad='caso')
        e2 = AuditEvent.objects.get(accion='rechazar', entidad='avistamiento')
        for e in (e1, e2):
            self.assertEqual((e.usuario, e.rol), (self.mod, 'moderador'))
            self.assertIsNotNone(e.creado_en)
            self.assertTrue(e.ip)
        self.assertIn('Spam', e2.detalle)

    def test_acciones_solo_por_post_y_con_accion_valida(self):
        caso = self.make_case(self.fam, publicado=False)
        r = self.client.post(reverse('moderation:caso', args=[caso.pk]), {'accion': 'borrar'}, follow=True)
        self.assertContains(r, 'Acción no válida')
        caso.refresh_from_db()
        self.assertEqual(caso.moderacion, 'pendiente')

    def test_ciudadano_no_puede_moderar(self):
        caso = self.make_case(self.fam, publicado=False)
        self.client.logout()
        self.login(self.make_user('c@example.com'))
        self.assertEqual(self.client.post(reverse('moderation:caso', args=[caso.pk]), {'accion': 'aprobar'}).status_code, 403)
        caso.refresh_from_db()
        self.assertEqual(caso.moderacion, 'pendiente')


class HU14MenoresTests(BaseTestCase):
    def setUp(self):
        self.mod = self.make_moderador()
        self.login(self.mod)

    def test_ca3_moderador_ve_indicador_y_no_puede_aprobar_sin_autorizacion(self):
        menor = self.make_case(publicado=False, edad=9, autorizacion_menor=False)
        r = self.client.get(reverse('moderation:caso', args=[menor.pk]))
        self.assertContains(r, 'Menor de edad')
        self.assertContains(r, 'No registrada')
        r = self.client.post(reverse('moderation:caso', args=[menor.pk]), {'accion': 'aprobar'}, follow=True)
        self.assertContains(r, 'no tiene registrada la autorización')
        menor.refresh_from_db()
        self.assertEqual(menor.moderacion, 'pendiente')

    def test_ca3_con_autorizacion_registrada_si_se_puede_aprobar(self):
        menor = self.make_case(publicado=False, edad=9, autorizacion_menor=True, calidad_declarada='Representante legal')
        self.client.post(reverse('moderation:caso', args=[menor.pk]), {'accion': 'aprobar'})
        menor.refresh_from_db()
        self.assertEqual(menor.moderacion, 'publicado')

    def test_ca3_un_mayor_de_edad_no_requiere_autorizacion(self):
        mayor = self.make_case(publicado=False, edad=18)
        self.assertFalse(mayor.es_menor)
        self.client.post(reverse('moderation:caso', args=[mayor.pk]), {'accion': 'aprobar'})
        mayor.refresh_from_db()
        self.assertEqual(mayor.moderacion, 'publicado')

    def test_ca4_caso_publico_de_menor_no_expone_datos_sensibles_del_familiar(self):
        fam = self.make_familiar('madre@example.com', cedula='1098765432', telefono='3119998877')
        menor = self.make_case(fam, edad=7, autorizacion_menor=True)
        self.client.logout()
        for url in (menor.get_absolute_url(), reverse('cases:listado'), reverse('cases:mapa', args=[menor.codigo])):
            r = self.client.get(url)
            for dato in ('1098765432', '3119998877', 'madre@example.com'):
                self.assertNotContains(r, dato)
        self.assertContains(self.client.get(menor.get_absolute_url()), 'Menor de edad')
        self.assertContains(self.client.get(menor.get_absolute_url()), 'se canaliza a través de la plataforma')

    def test_ca5_cifrado_en_transito_configurado_para_produccion(self):
        import os
        from django.conf import settings
        self.assertEqual(settings.SECURE_CONTENT_TYPE_NOSNIFF, True)
        fuente = open(os.path.join(settings.BASE_DIR, 'config', 'settings.py'), encoding='utf8').read()
        for clave in ('SECURE_SSL_REDIRECT', 'SESSION_COOKIE_SECURE', 'CSRF_COOKIE_SECURE', 'SECURE_HSTS_SECONDS'):
            self.assertIn(clave, fuente)


class HU10ReportesTests(BaseTestCase):
    def setUp(self):
        self.caso = self.make_case()
        self.av = self.make_sighting(self.caso)
        self.u1 = self.make_user('u1@example.com')

    def test_ca1_formulario_con_motivos_y_comentario_opcional(self):
        self.login(self.u1)
        r = self.client.get(reverse('moderation:reportar_avistamiento', args=[self.av.pk]))
        for motivo in ('Falso', 'Duplicado', 'Inapropiado', 'Otro'):
            self.assertContains(r, motivo)
        self.assertContains(r, 'Comentario (opcional)')

    def test_ca1_requiere_sesion(self):
        self.assertEqual(self.client.get(reverse('moderation:reportar_caso', args=[self.caso.pk])).status_code, 302)

    def test_ca2_el_reporte_se_registra_y_el_contenido_sigue_visible(self):
        self.login(self.u1)
        r = self.client.post(reverse('moderation:reportar_avistamiento', args=[self.av.pk]), {'motivo': 'falso', 'comentario': 'Es mentira'}, follow=True)
        self.assertContains(r, 'Su reporte fue enviado')
        self.assertEqual(ContentReport.objects.count(), 1)
        self.av.refresh_from_db()
        self.assertEqual(self.av.moderacion, 'publicado')
        self.assertTrue(AuditEvent.objects.filter(accion='reportar').exists())

    def test_ca3_no_se_duplica_el_reporte_del_mismo_usuario(self):
        self.login(self.u1)
        url = reverse('moderation:reportar_caso', args=[self.caso.pk])
        self.client.post(url, {'motivo': 'falso'})
        r = self.client.post(url, {'motivo': 'otro'}, follow=True)
        self.assertContains(r, 'Ya habíamos recibido su reporte')
        self.assertEqual(ContentReport.objects.count(), 1)

    def test_ca4_tres_reportes_de_usuarios_distintos_dan_prioridad_alta(self):
        self.login(self.make_moderador())
        for i in range(2):
            ContentReport.objects.create(reportero=self.make_user(f'r{i}@example.com'), avistamiento=self.av, motivo='falso')
        grupos = self.client.get(reverse('moderation:reportes')).context['grupos']
        self.assertFalse(grupos[0]['prioridad_alta'])
        ContentReport.objects.create(reportero=self.make_user('r9@example.com'), avistamiento=self.av, motivo='falso')
        otro = self.make_sighting(self.caso)
        ContentReport.objects.create(reportero=self.u1, avistamiento=otro, motivo='otro')
        grupos = self.client.get(reverse('moderation:reportes')).context['grupos']
        self.assertTrue(grupos[0]['prioridad_alta'])
        self.assertEqual(grupos[0]['objeto'].pk, self.av.pk)  # la prioridad alta va primero
        self.assertFalse(grupos[1]['prioridad_alta'])
        self.assertContains(self.client.get(reverse('moderation:cola')), 'Contenido reportado')

    def test_ca4_el_contenido_con_3_reportes_no_se_oculta_automaticamente(self):
        for i in range(3):
            ContentReport.objects.create(reportero=self.make_user(f'r{i}@example.com'), avistamiento=self.av, motivo='falso')
        self.av.refresh_from_db()
        self.assertEqual(self.av.moderacion, 'publicado')

    def test_ca5_moderador_ve_motivos_y_comentarios(self):
        ContentReport.objects.create(reportero=self.u1, avistamiento=self.av, motivo='duplicado', comentario='Ya lo reportaron ayer')
        self.login(self.make_moderador())
        r = self.client.get(reverse('moderation:reporte_resolver', args=['avistamiento', self.av.pk]))
        self.assertContains(r, 'Duplicado')
        self.assertContains(r, 'Ya lo reportaron ayer')

    def resolver(self, **datos):
        self.login(self.make_moderador())
        ContentReport.objects.create(reportero=self.u1, avistamiento=self.av, motivo='falso')
        return self.client.post(reverse('moderation:reporte_resolver', args=['avistamiento', self.av.pk]), datos)

    def test_ca5_mantener(self):
        self.resolver(accion='mantener')
        self.av.refresh_from_db()
        self.assertEqual(self.av.moderacion, 'publicado')
        self.assertEqual(ContentReport.objects.get().estado, 'mantenido')

    def test_ca5_editar(self):
        self.resolver(accion='editar', texto='Descripción corregida por el moderador')
        self.av.refresh_from_db()
        self.assertEqual(self.av.descripcion, 'Descripción corregida por el moderador')
        self.assertEqual(ContentReport.objects.get().estado, 'editado')

    def test_ca5_editar_sin_texto_no_hace_nada(self):
        r = self.resolver(accion='editar', texto='')
        self.assertContains(r, 'Escriba el nuevo texto')
        self.assertEqual(ContentReport.objects.get().estado, 'pendiente')

    def test_ca5_retirar_exige_motivo_oculta_y_notifica(self):
        r = self.resolver(accion='retirar', motivo='')
        self.assertContains(r, 'Debe indicar el motivo del retiro')
        self.client.post(reverse('moderation:reporte_resolver', args=['avistamiento', self.av.pk]), {'accion': 'retirar', 'motivo': 'Contenido falso'})
        self.av.refresh_from_db()
        self.assertEqual(self.av.moderacion, 'rechazado')
        self.assertEqual(ContentReport.objects.get().estado, 'retirado')
        self.assertTrue(Notification.objects.filter(usuario=self.av.autor, mensaje__contains='Contenido falso').exists())
        self.assertTrue(AuditEvent.objects.filter(accion='eliminar', entidad='avistamiento', entidad_id=self.av.pk).exists())

    def test_reportar_un_caso_y_resolverlo(self):
        self.login(self.u1)
        self.client.post(reverse('moderation:reportar_caso', args=[self.caso.pk]), {'motivo': 'inapropiado'})
        self.client.logout()
        self.login(self.make_moderador())
        self.client.post(reverse('moderation:reporte_resolver', args=['caso', self.caso.pk]), {'accion': 'retirar', 'motivo': 'Foto inapropiada'})
        self.caso.refresh_from_db()
        self.assertEqual(self.caso.moderacion, 'rechazado')

    def test_no_se_puede_reportar_contenido_no_publicado(self):
        pend = self.make_case(publicado=False)
        self.login(self.u1)
        self.assertEqual(self.client.get(reverse('moderation:reportar_caso', args=[pend.pk])).status_code, 404)
