from django.db import migrations

CREATE = """
CREATE OR REPLACE FUNCTION audit_block_mutation() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'El registro de auditoría es de solo lectura';
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER audit_no_update_delete BEFORE UPDATE OR DELETE ON audit_auditevent
    FOR EACH ROW EXECUTE FUNCTION audit_block_mutation();
"""
DROP = """
DROP TRIGGER IF EXISTS audit_no_update_delete ON audit_auditevent;
DROP FUNCTION IF EXISTS audit_block_mutation();
"""


def crear(apps, schema_editor):
    """HU-12 CA4: además de la protección en la aplicación, la base de datos rechaza UPDATE y DELETE."""
    if schema_editor.connection.vendor == 'postgresql':
        schema_editor.execute(CREATE)


def borrar(apps, schema_editor):
    if schema_editor.connection.vendor == 'postgresql':
        schema_editor.execute(DROP)


class Migration(migrations.Migration):
    dependencies = [('audit', '0001_initial')]
    operations = [migrations.RunPython(crear, borrar)]
