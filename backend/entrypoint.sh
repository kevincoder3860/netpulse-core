#!/bin/sh
set -e

python manage.py migrate --noinput
python manage.py create_default_admin

exec "$@"
