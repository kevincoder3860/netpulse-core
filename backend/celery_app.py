import os
from celery import Celery

# Set default Django settings module for Celery
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.core.settings')

app = Celery('backend')
# Load configuration from Django settings, using the CELERY_ prefix
app.config_from_object('django.conf:settings', namespace='CELERY')
# Autodiscover tasks in all installed Django apps
app.autodiscover_tasks()

@app.task(bind=True)
def debug_task(self):
    """Simple debug task to verify worker is running.
    Usage: `python manage.py shell -c "from backend.celery_app import debug_task; debug_task.delay()"`
    """
    print(f'Request: {self.request!r}')
