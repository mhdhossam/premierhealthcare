from .models import CustomUser
from django.contrib.auth import get_user_model
from apps.schema.registry import registry
from apps.schema.base import AdminSchema, SchemaField

User = get_user_model()


@registry.register
class UserSchema(AdminSchema):
    model = CustomUser
    endpoint = "/api/users/"
    list_display = ["id", "username", "email", "is_staff", "is_active", "date_joined"]
    search_fields = ["username", "email"]
    ordering = ["-date_joined"]
    exclude = ["password", "user_permissions", "groups"]

