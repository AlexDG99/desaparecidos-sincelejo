from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.db import models
from django.utils import timezone


class UserManager(BaseUserManager):
    use_in_migrations = True

    def create_user(self, email, password=None, **extra):
        if not email:
            raise ValueError('El correo electrónico es obligatorio.')
        email = self.normalize_email(email).lower()
        user = self.model(email=email, **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_staff(self, email, password, rol, nombre):
        """Crea moderadores y administradores (no existe auto-registro para esos roles, HU-13)."""
        extra = dict(rol=rol, nombre=nombre,
                     is_staff=(rol == User.Rol.ADMINISTRADOR))
        return self.create_user(email, password, **extra)

    def create_superuser(self, email, password=None, **extra):
        extra.setdefault('rol', User.Rol.ADMINISTRADOR)
        extra.setdefault('nombre', 'Administrador')
        extra.update(is_staff=True, is_superuser=True)
        return self.create_user(email, password, **extra)


class User(AbstractBaseUser, PermissionsMixin):
    class Rol(models.TextChoices):
        CIUDADANO = 'ciudadano', 'Ciudadano'
        FAMILIAR = 'familiar', 'Familiar'
        MODERADOR = 'moderador', 'Moderador'
        ADMINISTRADOR = 'administrador', 'Administrador'

    class Verificacion(models.TextChoices):
        NO_APLICA = 'no_aplica', 'No aplica'
        PENDIENTE = 'pendiente', 'Pendiente de verificación'
        VERIFICADA = 'verificada', 'Verificada'
        RECHAZADA = 'rechazada', 'Rechazada'

    email = models.EmailField('correo electrónico', unique=True)
    nombre = models.CharField('nombres completos', max_length=150)
    rol = models.CharField(max_length=20, choices=Rol.choices, default=Rol.CIUDADANO)
    cedula = models.CharField('número de cédula', max_length=15, unique=True, null=True, blank=True)
    telefono = models.CharField('teléfono celular', max_length=20, blank=True)
    parentesco = models.CharField('parentesco con la persona desaparecida', max_length=60, blank=True)
    verificacion = models.CharField(max_length=12, choices=Verificacion.choices, default=Verificacion.NO_APLICA)
    verificacion_motivo = models.TextField(blank=True)
    intentos_fallidos = models.PositiveSmallIntegerField(default=0)
    bloqueado_hasta = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(default=timezone.now)

    objects = UserManager()
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['nombre']

    class Meta:
        verbose_name = 'usuario'
        verbose_name_plural = 'usuarios'

    def save(self, *args, **kwargs):
        self.email = (self.email or '').lower()
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.nombre} <{self.email}>'

    def get_short_name(self):
        return self.nombre.split(' ')[0] if self.nombre else self.email

    @property
    def es_moderador(self):
        return self.rol in (self.Rol.MODERADOR, self.Rol.ADMINISTRADOR)

    @property
    def es_administrador(self):
        return self.rol == self.Rol.ADMINISTRADOR

    @property
    def es_familiar_verificado(self):
        return self.rol == self.Rol.FAMILIAR and self.verificacion == self.Verificacion.VERIFICADA

    @property
    def esta_bloqueado(self):
        return bool(self.bloqueado_hasta and self.bloqueado_hasta > timezone.now())


class ConsentRecord(models.Model):
    """Constancia de aceptación de la política de tratamiento de datos (Ley 1581 de 2012, HU-14 CA1/CA2)."""

    class Tipo(models.TextChoices):
        TRATAMIENTO = 'tratamiento_datos', 'Tratamiento de datos personales'
        MENOR = 'difusion_menor', 'Autorización de difusión de datos de un menor'

    usuario = models.ForeignKey(User, on_delete=models.CASCADE, related_name='consentimientos')
    tipo = models.CharField(max_length=20, choices=Tipo.choices)
    version_politica = models.CharField(max_length=10, default='1.0')
    caso_id = models.PositiveBigIntegerField(null=True, blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    aceptado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-aceptado_en']


class DataRequest(models.Model):
    """Solicitud de corrección o supresión de datos (derechos del titular, HU-14 CA6)."""

    class Tipo(models.TextChoices):
        CORREGIR = 'corregir', 'Corregir mis datos'
        ELIMINAR = 'eliminar', 'Eliminar mis datos'

    class Estado(models.TextChoices):
        PENDIENTE = 'pendiente', 'Pendiente'
        ATENDIDA = 'atendida', 'Atendida'

    usuario = models.ForeignKey(User, on_delete=models.CASCADE, related_name='solicitudes_datos')
    tipo = models.CharField(max_length=10, choices=Tipo.choices)
    mensaje = models.TextField()
    estado = models.CharField(max_length=10, choices=Estado.choices, default=Estado.PENDIENTE)
    atendida_por = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    atendida_en = models.DateTimeField(null=True, blank=True)
    respuesta = models.TextField(blank=True)
    creada_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['estado', 'creada_en']
