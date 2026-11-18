from django.core.files.base import ContentFile
from django.urls import reverse

from core.storage import EncryptedFileSystemStorage
from core.testing import BaseTestCase
from core.utils import normalizar


class CoreTests(BaseTestCase):
    def test_salud_responde_ok_rnf01(self):
        r = self.client.get(reverse('health'))
        self.assertEqual((r.status_code, r.json()), (200, {'estado': 'ok'}))

    def test_normalizar(self):
        self.assertEqual(normalizar('  JOSÉ   Ángel '), 'jose angel')

    def test_almacenamiento_cifrado_ida_y_vuelta(self):
        s = EncryptedFileSystemStorage()
        nombre = s.save('prueba/secreto.txt', ContentFile(b'dato muy sensible'))
        with open(s.path(nombre), 'rb') as f:
            self.assertNotIn(b'sensible', f.read())
        with s.open(nombre) as f:
            self.assertEqual(f.read(), b'dato muy sensible')
        with self.assertRaises(ValueError):
            s.url(nombre)
        s.delete(nombre)

    def test_pagina_404_y_403_personalizadas(self):
        self.assertContains(self.client.get('/no-existe/'), 'Página no encontrada', status_code=404)

    def test_inicio_publico(self):
        self.make_case(nombre='Caso Visible')
        r = self.client.get('/')
        self.assertContains(r, 'Caso Visible')
        self.assertContains(r, 'no sustituye la denuncia')

    def test_cabeceras_de_seguridad(self):
        r = self.client.get('/')
        self.assertEqual(r['X-Content-Type-Options'], 'nosniff')
        self.assertEqual(r['X-Frame-Options'], 'DENY')


class MapaTests(BaseTestCase):
    def test_politica_de_referer_permite_cargar_teselas_del_mapa(self):
        r = self.client.get('/')
        self.assertEqual(r['Referrer-Policy'], 'strict-origin-when-cross-origin')


class HU16EstadisticasTests(BaseTestCase):
    """HU-16: el administrador consulta un panel con estadísticas generales."""

    def setUp(self):
        self.admin = self.make_admin()
        self.url = reverse('estadisticas')

    def test_ca1_requiere_sesion(self):
        self.assertEqual(self.client.get(self.url).status_code, 302)

    def test_ca2_solo_el_administrador_puede_verlo(self):
        for usuario in (self.make_user('c@example.com'), self.make_moderador()):
            self.client.logout()
            self.login(usuario)
            self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_ca3_muestra_el_conteo_de_casos_y_avistamientos(self):
        self.make_case()
        activo = self.make_case()
        self.make_case(publicado=False)
        self.make_case(estado='cerrado')
        self.make_sighting(activo)
        self.make_sighting(activo)
        self.make_sighting(activo, publicado=False)
        self.login(self.admin)
        resumen = self.client.get(self.url).context['resumen']
        self.assertEqual(resumen['casos_activos'], 2)
        self.assertEqual(resumen['casos_pendientes'], 1)
        self.assertEqual(resumen['casos_cerrados'], 1)
        self.assertEqual(resumen['avistamientos_publicados'], 2)
        self.assertEqual(resumen['avistamientos_pendientes'], 1)

    def test_ca4_muestra_los_usuarios_por_rol(self):
        self.make_user('a@example.com')
        self.make_user('b@example.com')
        self.make_moderador()
        self.login(self.admin)
        usuarios = self.client.get(self.url).context['resumen']['usuarios']
        self.assertEqual(usuarios, {'ciudadano': 2, 'familiar': 0, 'moderador': 1, 'administrador': 1})

    def test_ca5_el_menu_muestra_el_enlace_solo_al_administrador(self):
        self.login(self.admin)
        self.assertContains(self.client.get(reverse('cases:home')), 'Estadísticas')
        self.client.logout()
        self.login(self.make_user('c@example.com'))
        self.assertNotContains(self.client.get(reverse('cases:home')), 'Estadísticas')

    def test_calcular_resumen_devuelve_ceros_cuando_no_hay_datos(self):
        from core.estadisticas import calcular_resumen
        resumen = calcular_resumen()
        self.assertEqual(resumen['casos_activos'], 0)
        self.assertEqual(resumen['usuarios'], {'ciudadano': 0, 'familiar': 0, 'moderador': 0, 'administrador': 1})
