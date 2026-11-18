import uuid

from django.conf import settings
from django.db import IntegrityError, models, transaction
from django.urls import reverse
from django.utils import timezone

from core.storage import get_private_storage
from core.utils import normalizar


def _foto_path(instance, filename):
    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else 'jpg'
    return f'casos/{uuid.uuid4().hex}.{ext}'


class Case(models.Model):
    class Sexo(models.TextChoices):
        MASCULINO = 'M', 'Masculino'
        FEMENINO = 'F', 'Femenino'
        OTRO = 'O', 'Otro / no especificado'

    class Moderacion(models.TextChoices):
        PENDIENTE = 'pendiente', 'Pendiente de moderación'
        PUBLICADO = 'publicado', 'Publicado'
        RECHAZADO = 'rechazado', 'Rechazado'
        SOSPECHOSO = 'sospechoso', 'Sospechoso (escalado)'

    class Estado(models.TextChoices):
        ACTIVO = 'activo', 'Activo'
        VIVO = 'encontrado_vivo', 'Encontrado con vida'
        MUERTO = 'encontrado_muerto', 'Encontrado sin vida'
        CERRADO = 'cerrado', 'Cerrado'

    codigo = models.CharField(max_length=20, unique=True, editable=False)
    familiar = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='casos')
    nombre = models.CharField('nombre completo', max_length=150)
    nombre_norm = models.CharField(max_length=150, editable=False, db_index=True)
    edad = models.PositiveSmallIntegerField()
    sexo = models.CharField(max_length=1, choices=Sexo.choices)
    fecha_desaparicion = models.DateField('fecha de desaparición')
    hora_aproximada = models.TimeField('hora aproximada', null=True, blank=True)
    zona = models.CharField('barrio o comuna', max_length=100)
    zona_norm = models.CharField(max_length=100, editable=False, db_index=True)
    lugar = models.CharField('lugar o dirección de la desaparición', max_length=200)
    senas = models.TextField('señas particulares')
    vestimenta = models.TextField('vestimenta', blank=True)
    numero_denuncia = models.CharField('número de denuncia', max_length=60, blank=True)

    es_menor = models.BooleanField(default=False, editable=False)
    calidad_declarada = models.CharField('calidad con la que actúa', max_length=60, blank=True)
    autorizacion_menor = models.BooleanField('autorización de difusión del menor', default=False)

    moderacion = models.CharField(max_length=12, choices=Moderacion.choices, default=Moderacion.PENDIENTE, db_index=True)
    moderacion_motivo = models.TextField(blank=True)
    moderado_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    moderado_en = models.DateTimeField(null=True, blank=True)

    estado = models.CharField(max_length=20, choices=Estado.choices, default=Estado.ACTIVO, db_index=True)
    cerrado_en = models.DateTimeField(null=True, blank=True)

    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-fecha_desaparicion', '-creado_en']
        indexes = [models.Index(fields=['moderacion', 'estado', '-fecha_desaparicion'])]

    def __str__(self):
        return f'{self.codigo} · {self.nombre}'

    def get_absolute_url(self):
        return reverse('cases:detalle', args=[self.codigo])

    @staticmethod
    def _siguiente_codigo():
        prefijo = f'SIN-{timezone.localdate().year}-'
        ultimo = Case.objects.filter(codigo__startswith=prefijo).order_by('-codigo').values_list('codigo', flat=True).first()
        n = int(ultimo.rsplit('-', 1)[-1]) + 1 if ultimo else 1
        return f'{prefijo}{n:04d}'

    def save(self, *args, **kwargs):
        self.nombre_norm = normalizar(self.nombre)
        self.zona_norm = normalizar(self.zona)
        self.es_menor = self.edad is not None and self.edad < 18
        if self.codigo:
            return super().save(*args, **kwargs)
        for _ in range(5):  # el código es único: se reintenta ante una colisión concurrente
            self.codigo = self._siguiente_codigo()
            try:
                with transaction.atomic():
                    return super().save(*args, **kwargs)
            except IntegrityError:
                self.codigo = ''
        raise IntegrityError('No fue posible generar un código único para el caso.')

    @property
    def es_publico(self):
        return self.moderacion == self.Moderacion.PUBLICADO

    @property
    def esta_activo(self):
        return self.estado == self.Estado.ACTIVO

    @property
    def muestra_ficha_completa(self):
        """Un caso cerrado solo conserva nombre y estado en la vista pública (HU-09 CA4)."""
        return self.esta_activo


class CasePhoto(models.Model):
    caso = models.ForeignKey(Case, on_delete=models.CASCADE, related_name='fotos')
    imagen = models.ImageField(upload_to=_foto_path, storage=get_private_storage)
    orden = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ['orden', 'id']
