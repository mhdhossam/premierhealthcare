"""
Schema field definitions and base AdminSchema class.

The schema system is the source-of-truth bridge between Django models
and the React renderer. Each registered schema describes:
  - What model it wraps
  - What fields are exposed (with types, constraints, read-only flags)
  - What the API endpoint is
  - Display configuration (list columns, search fields, ordering)

Field type mapping (Django → React renderer type):
  CharField / TextField        → "string"
  IntegerField / FloatField    → "number"
  BooleanField                 → "boolean"
  DateTimeField / DateField    → "datetime" / "date"
  ForeignKey                   → "relation"
  EmailField                   → "email"
  URLField                     → "url"
  FileField / ImageField       → "file"
  ChoiceField                  → "select"
"""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Any, Optional
import django.db.models as django_fields


# ─── Field descriptors ───────────────────────────────────────────────────────

@dataclass
class SchemaField:
    name: str
    type: str                           # React renderer type
    label: str = ""                     # Human-readable label
    read_only: bool = False
    required: bool = True
    nullable: bool = False
    help_text: str = ""
    # For "string" fields
    max_length: Optional[int] = None
    # For "number" fields
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    # For "select" fields
    choices: list[dict] = field(default_factory=list)
    # For "relation" fields
    related_model: Optional[str] = None
    related_endpoint: Optional[str] = None
    # Display flags
    show_in_list: bool = True
    sortable: bool = True
    searchable: bool = False

    def __post_init__(self):
        if not self.label:
            self.label = self.name.replace("_", " ").title()

    def to_dict(self) -> dict:
        d = asdict(self)
        # Strip None values for cleaner JSON payloads
        return {k: v for k, v in d.items() if v is not None}


# ─── Django field → SchemaField converter ───────────────────────────────────

_DJANGO_TYPE_MAP: dict[type, str] = {
    django_fields.CharField: "string",
    django_fields.TextField: "text",
    django_fields.EmailField: "email",
    django_fields.URLField: "url",
    django_fields.SlugField: "string",
    django_fields.IntegerField: "number",
    django_fields.BigIntegerField: "number",
    django_fields.SmallIntegerField: "number",
    django_fields.PositiveIntegerField: "number",
    django_fields.FloatField: "number",
    django_fields.DecimalField: "number",
    django_fields.BooleanField: "boolean",
    django_fields.NullBooleanField: "boolean",
    django_fields.DateTimeField: "datetime",
    django_fields.DateField: "date",
    django_fields.TimeField: "time",
    django_fields.FileField: "file",
    django_fields.ImageField: "file",
    django_fields.ForeignKey: "relation",
    django_fields.OneToOneField: "relation",
    django_fields.AutoField: "number",
    django_fields.BigAutoField: "number",
}


def django_field_to_schema(f: django_fields.Field) -> SchemaField:
    """
    Introspect a Django model field and produce a SchemaField.
    """
    ftype = type(f)
    schema_type = "string"
    for django_type, mapped in _DJANGO_TYPE_MAP.items():
        if isinstance(f, django_type):
            schema_type = mapped
            break

    kwargs: dict[str, Any] = {
        "name": f.name,
        "type": schema_type,
        "read_only": not f.editable,
        "required": not f.blank and not f.null,
        "nullable": f.null,
        "help_text": str(f.help_text) if f.help_text else "",
    }

    if hasattr(f, "max_length") and f.max_length:
        kwargs["max_length"] = f.max_length

    # Handle choices (maps to select type)
    if f.choices:
        kwargs["type"] = "select"
        kwargs["choices"] = [{"value": v, "label": str(l)} for v, l in f.choices]

    # Handle FK / relation
    if isinstance(f, (django_fields.ForeignKey, django_fields.OneToOneField)):
        related = f.related_model
        kwargs["related_model"] = related.__name__ if related else None
        # Endpoint derived by convention: lowercase model name + "s"
        if related:
            # Use Django's built-in pluralization
            plural = related._meta.verbose_name_plural
            if not plural:
            # Fallback to simple plural (should not happen for most models)
                plural = f"{related.__name__.lower()}s"
        kwargs["related_endpoint"] = f"/api/{plural.lower()}/"
            

    # Auto fields are always read-only
    if isinstance(f, (django_fields.AutoField, django_fields.BigAutoField)):
        kwargs["read_only"] = True
        kwargs["required"] = False

    # DateTimeField with auto_now / auto_now_add are read-only
    if isinstance(f, (django_fields.DateTimeField, django_fields.DateField)):
        if getattr(f, "auto_now", False) or getattr(f, "auto_now_add", False):
            kwargs["read_only"] = True
            kwargs["required"] = False
            kwargs["show_in_list"] = True

    return SchemaField(**kwargs)


# ─── Base AdminSchema class ──────────────────────────────────────────────────

class AdminSchema:
    """
    Base class for all admin schemas.

    Subclass this per model:

        class ProductSchema(AdminSchema):
            model = Product
            endpoint = "/api/products/"
            list_display = ["id", "name", "price", "created_at"]
            search_fields = ["name"]
            ordering = ["-created_at"]

    Alternatively, use auto_schema() for zero-config generation.
    """
    model = None
    endpoint: str = ""
    list_display: list[str] = []      # Columns shown in list view
    search_fields: list[str] = []
    ordering: list[str] = ["-id"]
    # Manually defined fields override auto-introspection
    fields: list[SchemaField] = []
    # Fields excluded from auto-introspection
    exclude: list[str] = ["password"]

    @classmethod
    def get_name(cls) -> str:
        return cls.model.__name__ if cls.model else cls.__name__.replace("Schema", "")

    @classmethod
    def get_fields(cls) -> list[SchemaField]:
        """
        Returns final field list.
        If cls.fields is defined, use it directly.
        Otherwise, auto-introspect from cls.model.
        """
        if cls.fields:
            return cls.fields

        if cls.model is None:
            return []

        introspected = []
        for f in cls.model._meta.get_fields():
            # Skip reverse relations and M2M for now
            if f.is_relation and (f.one_to_many or f.many_to_many):
                continue
            if not hasattr(f, "column"):
                continue
            if f.name in cls.exclude:
                continue
            sf = django_field_to_schema(f)
            # Apply list_display config
            if cls.list_display:
                sf.show_in_list = f.name in cls.list_display
            introspected.append(sf)

        return introspected

    @classmethod
    def to_dict(cls) -> dict:
        fields = cls.get_fields()
        list_fields = [f.name for f in fields if f.show_in_list] or [f.name for f in fields]

        return {
            "name": cls.get_name(),
            "endpoint": cls.endpoint,
            "list_display": list_fields,
            "search_fields": cls.search_fields,
            "ordering": cls.ordering,
            "fields": [f.to_dict() for f in fields],
        }