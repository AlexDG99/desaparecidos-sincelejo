# Sistema de Reporte de Personas Desaparecidas y Avistamientos – Sincelejo

Django 5.2 + PostgreSQL. Implementa las 14 historias de usuario (4 sprints) del documento del primer avance.

## Puesta en marcha local
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # en desarrollo use DEBUG=True y la base local
python manage.py migrate
python manage.py seed_demo    # datos de ejemplo (clave Demo-Clave-2026)
python manage.py runserver
```
Con Docker: `docker compose up --build` (crea PostgreSQL y la app en el puerto 8000).

## Roles
Ciudadano y familiar se registran en `/cuentas/`. Moderadores y administradores se crean con
`python manage.py create_staff correo@dominio --rol moderador|administrador --nombre "Nombre"`.
El familiar queda «pendiente» hasta que un moderador revisa sus datos (nombre, número de cédula y teléfono). No se almacenan fotografías de documentos.

## Pruebas
`python manage.py test` (144 pruebas; requieren PostgreSQL para el disparador de auditoría).

## Trazabilidad HU → módulo
HU-01 accounts · HU-02 cases (crear) · HU-03 cases (listado) · HU-04/05/07 sightings · HU-06/10 moderation ·
HU-08 cases (mapa) · HU-09 cases (cierre) · HU-11 cases (exportar) · HU-12 audit · HU-13 accounts · HU-14 accounts/cases/moderation.

## Copias de seguridad
`scripts/backup_db.sh` (diaria, retención 30 días). Arquitectura en `docs/arquitectura.md`.

## Pendientes antes de producción
Revisión jurídica de los textos (Ley 1581/1098); contraseñas con PBKDF2 (Django) en lugar de bcrypt; no se
eliminan metadatos ni se valida duración de videos; configurar SMTP real y HTTPS.

## Correo (notificaciones y recuperación de contraseña)
El registro NO exige confirmar el correo: la cuenta se crea y se inicia sesión de inmediato. El correo solo se usa para notificaciones y recuperar la contraseña.
Configure en `.env`: `EMAIL_BACKEND`, `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_USE_TLS`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD` y
`DEFAULT_FROM_EMAIL` (ver `.env.example`, con ejemplo para Gmail). Sin SMTP, use el backend de consola y lea los
correos con `docker compose logs -f web`. Los fallos de envío quedan registrados en el log.
