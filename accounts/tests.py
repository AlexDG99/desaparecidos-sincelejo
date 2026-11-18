import re
from datetime import timedelta

from django.conf import settings
from django.core import mail
from django.urls import reverse
from django.utils import timezone

from audit.models import AuditEvent
from core.testing import PASSWORD, BaseTestCase

from .models import ConsentRecord, DataRequest, User


class HU13LoginTests(BaseTestCase):
    """HU-13: inicio de sesión y control de acceso por rol."""

    def datos_ciudadano(self, **extra):
        d = {'nombre': 'Ana Gómez', 'email': 'ana@example.com', 'password1': PASSWORD, 'password2': PASSWORD, 'acepta_politica': 'on'}
        d.update(extra)
        return d

    def test_ca1_registro_ciudadano_crea_la_cuenta_e_inicia_sesion_sin_confirmar_correo(self):
        r = self.client.post(reverse('accounts:registro'), self.datos_ciudadano())
        self.assertRedirects(r, reverse('cases:home'), fetch_redirect_response=False)
        u = User.objects.get(email='ana@example.com')
        self.assertEqual(u.rol, User.Rol.CIUDADANO)
        self.assertEqual(len(mail.outbox), 0)  # ya no se envía correo de confirmación
        self.assertEqual(int(self.client.session['_auth_user_id']), u.pk)
        self.assertTrue(ConsentRecord.objects.filter(usuario=u, tipo='tratamiento_datos').exists())

    def test_ca1_registro_exige_autorizacion_de_datos(self):
        d = self.datos_ciudadano()
        d.pop('acepta_politica')
        r = self.client.post(reverse('accounts:registro'), d)
        self.assertContains(r, 'Debe aceptar la política de tratamiento de datos personales')
        self.assertFalse(User.objects.filter(email='ana@example.com').exists())

    def test_registro_rechaza_correo_duplicado_y_contrasena_debil(self):
        self.make_user('ana@example.com')
        r = self.client.post(reverse('accounts:registro'), self.datos_ciudadano())
        self.assertContains(r, 'Ya existe una cuenta con este correo')
        r = self.client.post(reverse('accounts:registro'), self.datos_ciudadano(email='otra@example.com', password1='12345678', password2='12345678'))
        self.assertFalse(User.objects.filter(email='otra@example.com').exists())

    def test_el_usuario_recien_registrado_puede_ingresar_de_inmediato(self):
        self.client.post(reverse('accounts:registro'), self.datos_ciudadano())
        self.client.logout()
        r = self.client.post(reverse('accounts:login'), {'username': 'ana@example.com', 'password': PASSWORD})
        self.assertRedirects(r, reverse('cases:home'), fetch_redirect_response=False)

    def test_ca2_login_correcto_muestra_solo_opciones_del_rol(self):
        self.make_user('c@example.com')
        self.client.post(reverse('accounts:login'), {'username': 'C@Example.com', 'password': PASSWORD})
        r = self.client.get(reverse('cases:home'))
        self.assertNotContains(r, 'Moderación</a>')
        self.assertNotContains(r, 'Reportar desaparición</a>')
        self.client.logout()
        self.login(self.make_moderador())
        self.assertContains(self.client.get(reverse('cases:home')), 'Moderación</a>')

    def test_ca3_bloqueo_tras_cinco_intentos_fallidos(self):
        u = self.make_user('c@example.com')
        for i in range(4):
            r = self.client.post(reverse('accounts:login'), {'username': u.email, 'password': 'incorrecta'})
            self.assertContains(r, 'introduzca')  # mensaje de credenciales inválidas de Django
        r = self.client.post(reverse('accounts:login'), {'username': u.email, 'password': 'incorrecta'})
        self.assertContains(r, 'bloqueada temporalmente')
        # un sexto intento, aun con la contraseña correcta, sigue bloqueado
        r = self.client.post(reverse('accounts:login'), {'username': u.email, 'password': PASSWORD})
        self.assertContains(r, 'bloqueada temporalmente')
        self.assertContains(r, '15 minutos')
        u.refresh_from_db()
        self.assertAlmostEqual((u.bloqueado_hasta - timezone.now()).total_seconds(), 15 * 60, delta=30)

    def test_ca3_el_bloqueo_vence_a_los_15_minutos(self):
        u = self.make_user('c@example.com')
        u.bloqueado_hasta = timezone.now() - timedelta(seconds=1)
        u.intentos_fallidos = 0
        u.save()
        r = self.client.post(reverse('accounts:login'), {'username': u.email, 'password': PASSWORD})
        self.assertRedirects(r, reverse('cases:home'), fetch_redirect_response=False)

    def test_ca4_recuperacion_enlace_un_solo_uso(self):
        u = self.make_user('c@example.com')
        self.client.post(reverse('accounts:password_reset'), {'email': u.email})
        self.assertEqual(len(mail.outbox), 1)
        enlace = re.search(r'https?://\S+/cuentas/recuperar/\S+/\S+/', mail.outbox[0].body).group(0)
        path = enlace.split('testserver', 1)[-1] if 'testserver' in enlace else '/' + enlace.split('/', 3)[3]
        r = self.client.get(path, follow=True)
        self.assertEqual(r.status_code, 200)
        r = self.client.post(r.request['PATH_INFO'], {'new_password1': 'Otra-Clave-2026!', 'new_password2': 'Otra-Clave-2026!'})
        self.assertEqual(r.status_code, 302)
        u.refresh_from_db()
        self.assertTrue(u.check_password('Otra-Clave-2026!'))
        # el mismo enlace ya no sirve
        r = self.client.get(path, follow=True)
        self.assertContains(r, 'Enlace inválido o vencido')

    def test_ca4_vigencia_del_enlace_es_60_minutos(self):
        self.assertEqual(settings.PASSWORD_RESET_TIMEOUT, 3600)

    def test_ca5_sesion_expira_a_los_30_minutos_de_inactividad(self):
        self.assertEqual(settings.SESSION_COOKIE_AGE, 30 * 60)
        self.assertTrue(settings.SESSION_SAVE_EVERY_REQUEST)  # el plazo se renueva con cada acción

    def test_ca6_usuario_sin_rol_de_moderador_recibe_403(self):
        self.login(self.make_user('c@example.com'))
        for nombre in ('moderation:cola', 'moderation:verificaciones', 'moderation:reportes'):
            self.assertEqual(self.client.get(reverse(nombre)).status_code, 403, nombre)

    def test_visitante_anonimo_es_redirigido_al_login(self):
        r = self.client.get(reverse('moderation:cola'))
        self.assertEqual(r.status_code, 302)
        self.assertIn('/cuentas/ingresar/', r['Location'])

    def test_contrasenas_se_almacenan_con_hash(self):
        u = self.make_user('c@example.com')
        self.assertTrue(u.password.startswith('pbkdf2_'))
        self.assertNotIn(PASSWORD, u.password)

    def test_moderadores_no_se_autoregistran(self):
        self.client.post(reverse('accounts:registro'), self.datos_ciudadano(rol='administrador'))
        self.assertEqual(User.objects.get(email='ana@example.com').rol, User.Rol.CIUDADANO)


class HU01FamiliarTests(BaseTestCase):
    """HU-01: registro y verificación de identidad del familiar."""

    def datos(self, **extra):
        d = {'nombre': 'María Pérez', 'cedula': '1100223344', 'email': 'maria@example.com', 'telefono': '3001112233',
             'parentesco': 'Madre/Padre', 'password1': PASSWORD, 'password2': PASSWORD, 'acepta_politica': 'on'}
        d.update(extra)
        return d

    def test_ca1_formulario_solicita_los_datos_requeridos(self):
        r = self.client.get(reverse('accounts:registro_familiar'))
        for campo in ('nombre', 'cedula', 'email', 'telefono', 'parentesco', 'password1'):
            self.assertContains(r, f'name="{campo}"')
        self.assertNotContains(r, 'cedula_imagen')
        self.assertNotContains(r, 'type="file"')

    def test_ca2_registro_completo_queda_pendiente_de_verificacion(self):
        r = self.client.post(reverse('accounts:registro_familiar'), self.datos())
        self.assertEqual(r.status_code, 302)
        u = User.objects.get(email='maria@example.com')
        self.assertEqual((u.rol, u.verificacion), (User.Rol.FAMILIAR, User.Verificacion.PENDIENTE))
        self.assertEqual(u.cedula, '1100223344')
        self.assertTrue(ConsentRecord.objects.filter(usuario=u).exists())

    def test_ca2_exige_campos_y_autorizacion(self):
        for faltante in ('nombre', 'cedula', 'telefono', 'parentesco', 'acepta_politica'):
            d = self.datos()
            d.pop(faltante)
            r = self.client.post(reverse('accounts:registro_familiar'), d)
            self.assertEqual(r.status_code, 200, faltante)
            self.assertFalse(User.objects.filter(email='maria@example.com').exists(), faltante)

    def test_ca6_impide_duplicados_por_cedula_o_correo(self):
        self.make_familiar('x@example.com', cedula='1100223344')
        r = self.client.post(reverse('accounts:registro_familiar'), self.datos())
        self.assertContains(r, 'Ya existe una cuenta con este número de cédula')
        r = self.client.post(reverse('accounts:registro_familiar'), self.datos(cedula='999888777', email='x@example.com'))
        self.assertContains(r, 'Ya existe una cuenta con este correo')

    def test_cedula_con_formato_invalido_se_rechaza(self):
        r = self.client.post(reverse('accounts:registro_familiar'), self.datos(cedula='12ab'))
        self.assertContains(r, 'número de cédula válido')
        self.assertEqual(User.objects.filter(email='maria@example.com').count(), 0)

    def test_no_se_almacenan_imagenes_de_cedula(self):
        self.assertFalse(any(f.name == 'cedula_imagen' for f in User._meta.get_fields()))

    def test_ca3_familiar_pendiente_no_puede_crear_casos(self):
        self.login(self.make_familiar('f@example.com', verificada=False))
        r = self.client.get(reverse('cases:crear'))
        self.assertEqual(r.status_code, 403)
        self.assertContains(r, 'Aún no puede publicar casos', status_code=403)

    def test_ca4_moderador_aprueba_y_familiar_queda_verificado(self):
        fam = self.make_familiar('f@example.com', verificada=False)
        mod = self.make_moderador()
        self.login(mod)
        r = self.client.post(reverse('moderation:verificacion', args=[fam.pk]), {'accion': 'aprobar'})
        self.assertEqual(r.status_code, 302)
        fam.refresh_from_db()
        self.assertTrue(fam.es_familiar_verificado)
        self.assertTrue(AuditEvent.objects.filter(accion='verificar', entidad_id=fam.pk).exists())
        self.assertTrue(fam.notificaciones.exists())
        self.client.logout()
        self.login(fam)
        self.assertEqual(self.client.get(reverse('cases:crear')).status_code, 200)

    def test_ca5_rechazo_exige_motivo_notifica_y_permite_reenviar(self):
        fam = self.make_familiar('f@example.com', verificada=False)
        self.login(self.make_moderador())
        r = self.client.post(reverse('moderation:verificacion', args=[fam.pk]), {'accion': 'rechazar', 'motivo': ''}, follow=True)
        self.assertContains(r, 'Debe indicar el motivo')
        fam.refresh_from_db()
        self.assertEqual(fam.verificacion, User.Verificacion.PENDIENTE)
        self.client.post(reverse('moderation:verificacion', args=[fam.pk]), {'accion': 'rechazar', 'motivo': 'Foto borrosa'})
        fam.refresh_from_db()
        self.assertEqual((fam.verificacion, fam.verificacion_motivo), (User.Verificacion.RECHAZADA, 'Foto borrosa'))
        self.assertTrue(any('Foto borrosa' in m.body for m in mail.outbox))
        self.client.logout()
        self.login(fam)
        r = self.client.post(reverse('accounts:reenviar_verificacion'), {'nombre': 'María Pérez Corregida', 'cedula': '1100998877', 'telefono': '3012223344'})
        self.assertEqual(r.status_code, 302)
        fam.refresh_from_db()
        self.assertEqual((fam.verificacion, fam.nombre, fam.cedula), (User.Verificacion.PENDIENTE, 'María Pérez Corregida', '1100998877'))

    def test_moderador_ve_los_datos_de_verificacion_sin_imagen(self):
        fam = self.make_familiar('f@example.com', verificada=False, cedula='1100445566')
        self.login(self.make_moderador())
        r = self.client.get(reverse('moderation:verificacion', args=[fam.pk]))
        self.assertContains(r, '1100445566')
        self.assertNotContains(r, '<img')
        self.client.logout()
        self.login(self.make_user('c@example.com'))
        self.assertEqual(self.client.get(reverse('moderation:verificacion', args=[fam.pk])).status_code, 403)


class HU14DataRightsTests(BaseTestCase):
    def test_ca6_solicitud_de_correccion_y_atencion_por_administrador(self):
        u = self.make_user('c@example.com')
        self.login(u)
        self.client.post(reverse('accounts:mis_datos'), {'tipo': 'corregir', 'mensaje': 'Mi nombre está mal escrito'})
        s = DataRequest.objects.get(usuario=u)
        self.client.logout()
        self.login(self.make_admin())
        r = self.client.post(reverse('moderation:atender_solicitud', args=[s.pk]), {'respuesta': 'Listo'})
        self.assertEqual(r.status_code, 302)
        s.refresh_from_db()
        self.assertEqual(s.estado, DataRequest.Estado.ATENDIDA)
        self.assertTrue(AuditEvent.objects.filter(entidad='solicitud', entidad_id=s.pk).exists())

    def test_ca6_supresion_anonimiza_la_cuenta(self):
        u = self.make_familiar('f@example.com')
        s = DataRequest.objects.create(usuario=u, tipo='eliminar', mensaje='Borren mis datos')
        self.login(self.make_admin())
        self.client.post(reverse('moderation:atender_solicitud', args=[s.pk]), {'respuesta': 'Hecho'})
        u.refresh_from_db()
        self.assertEqual((u.nombre, u.is_active, u.cedula), ('Usuario eliminado', False, None))
        self.assertTrue(u.email.endswith('@anonimo.invalid'))
        self.assertFalse(u.has_usable_password())

    def test_solo_el_administrador_atiende_solicitudes(self):
        u = self.make_user('c@example.com')
        s = DataRequest.objects.create(usuario=u, tipo='corregir', mensaje='x')
        self.login(self.make_moderador())
        self.assertEqual(self.client.post(reverse('moderation:atender_solicitud', args=[s.pk])).status_code, 403)
