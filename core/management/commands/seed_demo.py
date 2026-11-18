"""Carga datos de demostración (solo para desarrollo)."""
from datetime import date, time, timedelta

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand

from accounts.models import User
from cases.models import Case, CasePhoto
from core.testing import imagen_bytes
from sightings.models import Sighting

PASSWORD = 'Demo-Clave-2026'


class Command(BaseCommand):
    help = 'Crea usuarios, casos y avistamientos de demostración.'

    def handle(self, *a, **o):
        def user(email, rol, nombre, **extra):
            u, creado = User.objects.get_or_create(email=email, defaults=dict(rol=rol, nombre=nombre, **extra))
            if creado:
                u.set_password(PASSWORD)
                if rol == 'administrador':
                    u.is_staff = u.is_superuser = True
                u.save()
            return u
        user('admin@demo.local', 'administrador', 'Administrador Demo')
        user('moderador@demo.local', 'moderador', 'Moderadora Demo')
        ciud = user('ciudadano@demo.local', 'ciudadano', 'Ciudadano Demo')
        fam = user('familiar@demo.local', 'familiar', 'Familiar Demo', cedula='1100000001', telefono='3001112233',
                   parentesco='Madre/Padre', verificacion=User.Verificacion.VERIFICADA)
        if Case.objects.exists():
            self.stdout.write('Ya hay casos; no se cargan más.')
            return
        datos = [('Luis Fernando Támara', 34, 'M', 'Barrio Majagual', 'publicado'),
                 ('María José Ortega', 15, 'F', 'Comuna 3', 'publicado'),
                 ('Carlos Julio Mendoza', 61, 'M', 'Barrio La Selva', 'pendiente')]
        for i, (n, edad, sx, zona, mod) in enumerate(datos):
            c = Case.objects.create(familiar=fam, nombre=n, edad=edad, sexo=sx, zona=zona, lugar='Cerca del parque',
                                    fecha_desaparicion=date.today() - timedelta(days=2 + i), senas='Lunar en la mejilla',
                                    moderacion=mod, autorizacion_menor=edad < 18, calidad_declarada='Familiar' if edad < 18 else '')
            f = CasePhoto(caso=c)
            f.imagen.save('f.jpg', ContentFile(imagen_bytes()), save=False)
            f.save()
            if mod == 'publicado':
                Sighting.objects.create(caso=c, autor=ciud, fecha=date.today() - timedelta(days=1), hora=time(15, 20),
                                        latitud='9.3047', longitud='-75.3978', direccion='Plaza Majagual',
                                        descripcion='Lo vi caminando hacia el mercado.', moderacion='publicado')
        self.stdout.write(self.style.SUCCESS(f'Datos de demostración listos. Clave de todos los usuarios: {PASSWORD}'))
