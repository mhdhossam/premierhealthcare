import os
from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()


def user_upload_path(instance, filename):
    """Store files under uploads/<user_id>/<filename>"""
    return f"uploads/{instance.user_id}/{filename}"


class File(models.Model):
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="files",
    )
    file = models.FileField(upload_to=user_upload_path)
    original_name = models.CharField(max_length=255)
    size = models.PositiveBigIntegerField(help_text="File size in bytes")
    content_type = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.original_name

    @property
    def extension(self):
        _, ext = os.path.splitext(self.original_name)
        return ext.lower().lstrip(".")