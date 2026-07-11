from django.apps import AppConfig


class SchemaConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.schema"

    def ready(self):
        # Trigger autodiscovery of all admin_schema.py modules
        # across all installed apps. This mirrors Django admin's
        # autodiscover() behavior — decorators self-register.
        from .registry import registry
        registry.autodiscover()