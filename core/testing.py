"""Utilidades para las pruebas automatizadas."""
import io
from datetime import date, time, timedelta

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from PIL import Image

from accounts.models import User
from cases.models import Case, CasePhoto
from sightings.models import Sighting

PASSWORD = 'Clave-Segura-2026'


def imagen_bytes(formato='JPEG', size=(40, 30), exif=False):
    img = Image.new('RGB', size, (200, 30, 30))
    buf = io.BytesIO()
    kwargs = {}
    if exif and formato == 'JPEG':
        e = Image.Exif()
        e[0x010F] = 'CamaraSecreta'
        e[0x0112] = 1
        kwargs['exif'] = e
    img.save(buf, formato, **kwargs)
    return buf.getvalue()


def archivo_imagen(nombre='foto.jpg', formato='JPEG', exif=False):
    return SimpleUploadedFile(nombre, imagen_bytes(formato, exif=exif), content_type='image/jpeg' if formato == 'JPEG' else 'image/png')


def archivo_mp4(nombre='video.mp4', size=2048):
    return SimpleUploadedFile(nombre, b'\x00\x00\x00\x18ftypmp42' + b'\x00' * size, content_type='video/mp4')


class BaseTestCase(TestCase):
    def make_user(self, email='ciudadano@example.com', rol=User.Rol.CIUDADANO, **extra):
        extra.setdefault('nombre', 'Persona de Prueba')
        if rol == User.Rol.ADMINISTRADOR:
            extra.setdefault('is_staff', True)
        return User.objects.create_user(email, PASSWORD, rol=rol, **extra)

    def make_familiar(self, email='familiar@example.com', verificada=True, **extra):
        n = User.objects.count() + 1
        extra.setdefault('cedula', f'1{n:09d}')
        extra.setdefault('telefono', '3001234567')
        extra.setdefault('parentesco', 'Madre/Padre')
        extra.setdefault('verificacion', User.Verificacion.VERIFICADA if verificada else User.Verificacion.PENDIENTE)
        return self.make_user(email, User.Rol.FAMILIAR, **extra)

    def make_moderador(self, email='mod@example.com'):
        return self.make_user(email, User.Rol.MODERADOR, nombre='Moderadora')

    def make_admin(self, email='admin@example.com'):
        return self.make_user(email, User.Rol.ADMINISTRADOR, nombre='Administrador')

    def make_case(self, familiar=None, publicado=True, **extra):
        familiar = familiar or self.make_familiar(email=f'fam{Case.objects.count()}@example.com')
        datos = dict(nombre='José Ángel Pérez', edad=30, sexo='M', fecha_desaparicion=date.today() - timedelta(days=3),
                     zona='Barrio Majagual', lugar='Calle 20 # 15-10', senas='Cicatriz en la ceja izquierda', familiar=familiar)
        datos.update(extra)
        if publicado:
            datos.setdefault('moderacion', Case.Moderacion.PUBLICADO)
        caso = Case.objects.create(**datos)
        foto = CasePhoto(caso=caso)
        foto.imagen.save('f.jpg', __import__('django.core.files.base', fromlist=['ContentFile']).ContentFile(imagen_bytes()), save=False)
        foto.save()
        return caso

    def make_sighting(self, caso, autor=None, publicado=True, **extra):
        autor = autor or self.make_user(f'ciud{Sighting.objects.count()}@example.com')
        datos = dict(caso=caso, autor=autor, fecha=date.today() - timedelta(days=1), hora=time(10, 30),
                     latitud='9.304700', longitud='-75.397800', direccion='Plaza principal',
                     descripcion='Vi a la persona caminando por la plaza con una mochila azul.')
        datos.update(extra)
        if publicado:
            datos.setdefault('moderacion', Sighting.Moderacion.PUBLICADO)
        return Sighting.objects.create(**datos)

    def login(self, user):
        self.client.force_login(user)
