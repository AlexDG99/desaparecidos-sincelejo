"""Almacenamiento privado y cifrado en reposo (RNF-02).

Todo archivo subido (fotos de casos, evidencias de avistamientos, imágenes de cédula) se guarda cifrado
con Fernet (AES-128-CBC + HMAC-SHA256) fuera de la carpeta pública. Solo se entrega a través de vistas que
verifican permisos.
"""
import functools

from cryptography.fernet import Fernet
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage


@functools.lru_cache(maxsize=1)
def _fernet():
    return Fernet(settings.FIELD_ENCRYPTION_KEY.encode())


class EncryptedFileSystemStorage(FileSystemStorage):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault('location', str(settings.PRIVATE_MEDIA_ROOT))
        super().__init__(*args, **kwargs)

    def _save(self, name, content):
        content.seek(0)
        token = _fernet().encrypt(content.read())
        return super()._save(name, ContentFile(token))

    def _open(self, name, mode='rb'):
        with super()._open(name, 'rb') as f:
            data = _fernet().decrypt(f.read())
        return ContentFile(data, name=name)

    def url(self, name):
        raise ValueError('Los archivos privados solo se sirven mediante vistas con control de acceso.')


def get_private_storage():
    return EncryptedFileSystemStorage()
