from django.db import models


class Notification(models.Model):
    usuario = models.ForeignKey('accounts.User', on_delete=models.CASCADE, related_name='notificaciones')
    titulo = models.CharField(max_length=160)
    mensaje = models.TextField()
    url = models.CharField(max_length=300, blank=True)
    leida = models.BooleanField(default=False)
    correo_enviado = models.BooleanField(default=False)
    intentos_correo = models.PositiveSmallIntegerField(default=0)
    creada_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-creada_en', '-id']
        indexes = [models.Index(fields=['usuario', 'leida'])]

    def __str__(self):
        return f'{self.usuario_id}: {self.titulo}'
