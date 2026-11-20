from django.db import migrations


def create_radacct_table(apps, schema_editor):
    if schema_editor.connection.alias != 'radius_db':
        return

    radacct = apps.get_model('radius', 'RadAcct')
    table_name = radacct._meta.db_table
    existing_tables = schema_editor.connection.introspection.table_names()
    if table_name not in existing_tables:
        schema_editor.create_model(radacct)


class Migration(migrations.Migration):

    dependencies = [
        ('radius', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(create_radacct_table, migrations.RunPython.noop),
    ]
