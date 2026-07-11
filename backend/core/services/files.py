"""
core/services/files.py

All file business logic lives here.
Both the API views call into this — no logic in views.
"""
from django.core.exceptions import PermissionDenied, ObjectDoesNotExist

from apps.files.models import File


def upload_file(user, uploaded_file):
    """
    Save an uploaded file and return the File instance.
    `uploaded_file` is a Django InMemoryUploadedFile / TemporaryUploadedFile.
    """
    content_type = getattr(uploaded_file, "content_type", "") or ""
    return File.objects.create(
        user=user,
        file=uploaded_file,
        original_name=uploaded_file.name,
        size=uploaded_file.size,
        content_type=content_type,
    )


def get_user_files(user):
    """Return all files belonging to a user, newest first."""
    return File.objects.filter(user=user)


def delete_file(user, file_id):
    """
    Delete a file by ID. Raises PermissionDenied if the file
    doesn't belong to this user, ObjectDoesNotExist if not found.
    """
    try:
        f = File.objects.get(id=file_id)
    except File.DoesNotExist:
        raise ObjectDoesNotExist(f"File {file_id} not found.")

    if f.user_id != user.id:
        raise PermissionDenied("You do not own this file.")

    # Delete the actual file from storage before removing DB row
    f.file.delete(save=False)
    f.delete()