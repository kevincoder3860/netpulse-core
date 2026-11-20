from django.db import migrations, models


def create_missing_freeradius_tables(apps, schema_editor):
    if (
        schema_editor.connection.alias != 'radius_db'
        or schema_editor.connection.vendor != 'sqlite'
    ):
        return

    existing_tables = set(schema_editor.connection.introspection.table_names())
    model_names = ('RadCheck', 'RadReply', 'RadUserGroup', 'RadAcct', 'Nas')
    for model_name in model_names:
        model = apps.get_model('radius', model_name)
        if model._meta.db_table not in existing_tables:
            schema_editor.create_model(model)
            existing_tables.add(model._meta.db_table)


class Migration(migrations.Migration):

    dependencies = [
        ('radius', '0002_create_radacct_table'),
    ]

    operations = [
        migrations.CreateModel(
            name='RadUserGroup',
            fields=[
                ('id', models.AutoField(primary_key=True, serialize=False)),
                ('username', models.CharField(default='', max_length=64)),
                ('groupname', models.CharField(default='', max_length=64)),
                ('priority', models.IntegerField(default=1)),
            ],
            options={
                'db_table': 'radusergroup',
                'managed': False,
            },
        ),
        migrations.RunPython(
            create_missing_freeradius_tables,
            migrations.RunPython.noop,
        ),
    ]
