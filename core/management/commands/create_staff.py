"""Crea moderadores y administradores (HU-13: los roles internos no se autorregistran)."""
from getpass import getpass

from django.core.management.base import BaseCommand, CommandError

from accounts.models import User


class Command(BaseCommand):
    help = 'Crea un usuario moderador o administrador.'

    def add_arguments(self, p):
        p.add_argument('email')
        p.add_argument('--rol', choices=['moderador', 'administrador'], default='moderador')
        p.add_argument('--nombre', default='')
        p.add_argument('--password', default=None)

    def handle(self, *a, **o):
        if User.objects.filter(email__iexact=o['email']).exists():
            raise CommandError('Ya existe un usuario con ese correo.')
        pwd = o['password'] or getpass('Contraseña: ')
        u = User.objects.create_user(o['email'], pwd, rol=o['rol'], nombre=o['nombre'] or o['email'],
                                     is_staff=o['rol'] == 'administrador')
        if o['rol'] == 'administrador':
            u.is_superuser = True
            u.save(update_fields=['is_superuser'])
        self.stdout.write(self.style.SUCCESS(f'Usuario {u.email} creado con rol {u.rol}.'))
