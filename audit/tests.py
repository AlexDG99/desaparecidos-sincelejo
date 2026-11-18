import csv
import io
from datetime import date, timedelta

from django.db import connection, transaction
from django.db.utils import DatabaseError
from django.urls import reverse

from cases.models import Case
from core.testing import BaseTestCase

from .models import AuditEvent, AuditReadOnlyError
from .services import log


class HU12AuditoriaTests(BaseTestCase):
    def setUp(self):
        self.admin = self.make_admin()
        self.caso = self.make_case()

    def test_ca1_registra_usuario_rol_fecha_accion_entidad_e_ip(self):
        e = log(self.admin, 'aprobar', 'caso', self.caso.pk, caso_id=self.caso.pk, detalle='ok', ip='10.0.0.5')
        self.assertEqual((e.usuario, e.usuario_email, e.rol, e.accion, e.entidad, e.entidad_id, str(e.ip)),
                         (self.admin, 'admin@example.com', 'administrador', 'aprobar', 'caso', self.caso.pk, '10.0.0.5'))
        self.assertIsNotNone(e.creado_en)

    def test_ca1_las_acciones_del_sistema_generan_eventos(self):
        fam = self.make_familiar('f2@example.com')
        self.login(fam)
        from core.testing import archivo_imagen
        self.client.post(reverse('cases:crear'), {
            'nombre': 'Persona Nueva', 'edad': '40', 'sexo': 'F', 'fecha_desaparicion': date.today().isoformat(), 'zona': 'Centro',
            'lugar': 'Plaza', 'senas': 'Lunar', 'acepta_politica': 'on', 'fotos': archivo_imagen()})
        nuevo = Case.objects.get(nombre='Persona Nueva')
        self.client.logout()
        self.login(self.make_moderador())
        self.client.post(reverse('moderation:caso', args=[nuevo.pk]), {'accion': 'aprobar'})
        self.client.logout()
        self.login(fam)
        self.client.post(reverse('cases:cerrar', args=[nuevo.codigo]), {'resultado': 'cerrado', 'confirmar': 'on'})
        acciones = set(AuditEvent.objects.filter(caso_id=nuevo.pk).values_list('accion', flat=True))
        self.assertEqual(acciones, {'crear', 'aprobar', 'cerrar'})
        self.assertTrue(AuditEvent.objects.filter(accion='aprobar', ip='127.0.0.1').exists())

    def test_ca2_listado_solo_para_administrador_del_mas_reciente_al_mas_antiguo(self):
        for i in range(3):
            log(self.admin, 'editar', 'caso', i, detalle=f'evento {i}')
        self.login(self.admin)
        r = self.client.get(reverse('audit:listado'))
        self.assertEqual([e.detalle for e in r.context['page']], ['evento 2', 'evento 1', 'evento 0'])
        for rol_user in (self.make_moderador(), self.make_user('c@example.com')):
            self.client.logout()
            self.login(rol_user)
            self.assertEqual(self.client.get(reverse('audit:listado')).status_code, 403)

    def test_ca2_filtros_por_usuario_accion_entidad_y_fechas(self):
        mod = self.make_moderador()
        log(self.admin, 'aprobar', 'caso', 1)
        log(mod, 'rechazar', 'avistamiento', 2)
        log(mod, 'rechazar', 'caso', 3)
        self.login(self.admin)

        def ids(**f):
            return sorted(e.entidad_id for e in self.client.get(reverse('audit:listado'), f).context['page'])
        self.assertEqual(ids(usuario='mod@'), [2, 3])
        self.assertEqual(ids(accion='aprobar'), [1])
        self.assertEqual(ids(entidad='avistamiento'), [2])
        self.assertEqual(ids(entidad='caso', usuario='mod'), [3])
        self.assertEqual(ids(desde=date.today().isoformat(), hasta=date.today().isoformat()), [1, 2, 3])
        self.assertEqual(ids(desde=(date.today() + timedelta(days=1)).isoformat()), [])
        self.assertEqual(ids(hasta=(date.today() - timedelta(days=1)).isoformat()), [])

    def test_ca3_historial_de_un_caso_con_todos_sus_eventos(self):
        av = self.make_sighting(self.caso)
        log(self.admin, 'crear', 'caso', self.caso.pk, caso_id=self.caso.pk)
        log(self.admin, 'aprobar', 'avistamiento', av.pk, caso_id=self.caso.pk)
        log(self.admin, 'crear', 'caso', 999, caso_id=999)
        self.assertEqual(AuditEvent.objects.filter(caso_id=self.caso.pk).count(), 2)
        self.login(self.admin)
        r = self.client.get(self.caso.get_absolute_url())
        self.assertContains(r, 'Historial de auditoría')
        self.assertEqual(len(r.context['historial']), 2)

    def test_ca3_el_historial_del_caso_solo_lo_ve_el_administrador(self):
        log(self.admin, 'crear', 'caso', self.caso.pk, caso_id=self.caso.pk)
        self.login(self.make_moderador())
        self.assertNotContains(self.client.get(self.caso.get_absolute_url()), 'Historial de auditoría')

    def test_ca4_la_aplicacion_impide_modificar_o_eliminar(self):
        e = log(self.admin, 'crear', 'caso', 1)
        e.detalle = 'alterado'
        with self.assertRaises(AuditReadOnlyError):
            e.save()
        with self.assertRaises(AuditReadOnlyError):
            e.delete()
        with self.assertRaises(AuditReadOnlyError):
            AuditEvent.objects.all().update(detalle='x')
        with self.assertRaises(AuditReadOnlyError):
            AuditEvent.objects.all().delete()
        self.assertEqual(AuditEvent.objects.get(pk=e.pk).detalle, '')

    def test_ca4_la_base_de_datos_tambien_rechaza_update_y_delete(self):
        if connection.vendor != 'postgresql':
            self.skipTest('El disparador de solo lectura es específico de PostgreSQL.')
        e = log(self.admin, 'crear', 'caso', 1)
        for sql in ("UPDATE audit_auditevent SET detalle = 'hack' WHERE id = %s", "DELETE FROM audit_auditevent WHERE id = %s"):
            with self.assertRaises(DatabaseError):
                with transaction.atomic(), connection.cursor() as c:
                    c.execute(sql, [e.pk])
        self.assertEqual(AuditEvent.objects.get(pk=e.pk).detalle, '')

    def test_ca4_ni_el_administrador_django_puede_editar_o_borrar(self):
        from django.contrib import admin as dj_admin
        ma = dj_admin.site._registry[AuditEvent]
        req = type('R', (), {'user': self.admin})()
        self.assertFalse(ma.has_add_permission(req))
        self.assertFalse(ma.has_change_permission(req))
        self.assertFalse(ma.has_delete_permission(req))

    def test_ca5_exportar_el_resultado_filtrado_en_csv(self):
        mod = self.make_moderador()
        log(self.admin, 'aprobar', 'caso', 1, detalle='uno', ip='10.0.0.1')
        log(mod, 'rechazar', 'caso', 2, detalle='dos, con coma')
        self.login(self.admin)
        r = self.client.get(reverse('audit:exportar'), {'accion': 'rechazar'})
        self.assertIn('text/csv', r['Content-Type'])
        filas = list(csv.reader(io.StringIO(r.content.decode('utf-8-sig'))))
        self.assertEqual(filas[0][:5], ['fecha_hora', 'usuario', 'rol', 'accion', 'entidad'])
        self.assertEqual(len(filas), 2)
        self.assertEqual((filas[1][1], filas[1][3], filas[1][8]), ('mod@example.com', 'rechazar', 'dos, con coma'))

    def test_ca5_solo_el_administrador_exporta(self):
        self.login(self.make_moderador())
        self.assertEqual(self.client.get(reverse('audit:exportar')).status_code, 403)
