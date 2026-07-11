"""
Registers the Files model with apps.schema so it appears
in the Nexus Admin sidebar automatically.
"""
# apps/files/apps.py

from django.apps import AppConfig


class FilesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.files"
    label = "files"