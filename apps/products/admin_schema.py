"""
Schema registration for Products app.
Autodiscovered by SchemaConfig.ready() via registry.autodiscover().
"""
from apps.schema.registry import registry
from apps.schema.base import AdminSchema, SchemaField
from .models import Product, Category


@registry.register
class ProductSchema(AdminSchema):
    model = Product
    endpoint = "/api/products/"
    list_display = ["id", "name", "price", "stock", "status","category", "created_at"]
    search_fields = ["name", "description"]
    ordering = ["-created_at"]
    # Auto-introspect fields (no manual fields list needed)


@registry.register
class CategorySchema(AdminSchema):
    model = Category
    endpoint = "/api/categories/"
    list_display = ["id", "name", "slug", "created_at"]
    search_fields = ["name", "slug"]
    ordering = ["name"]