from .models import CustomUser

from apps.schema.registry import registry
from apps.schema.base import AdminSchema, SchemaField




@registry.register
class UserSchema(AdminSchema):
    model = CustomUser
    endpoint = "/api/users/"
    list_display = ["id", "username", "email", "is_staff", "is_active"]
    search_fields = ["username", "email"]
    ordering = ["-id"]
    exclude = ["password", "user_permissions", "groups"]

