"""
Schema Registry

A singleton-style registry that holds all registered AdminSchema subclasses.
Schemas are registered either explicitly via @register or automatically
via autodiscover() which walks all installed apps for admin_schema.py modules.

Usage:
    # In apps/products/admin_schema.py
    from apps.schema.registry import registry
    from apps.schema.base import AdminSchema
    from .models import Product

    @registry.register
    class ProductSchema(AdminSchema):
        model = Product
        endpoint = "/api/products/"
        list_display = ["id", "name", "price", "created_at"]
        search_fields = ["name"]


    # In views / APIs:
    schema = registry.get("Product")           # → ProductSchema class (bare name, unambiguous only)
    schema = registry.get("billing.Product")    # → ProductSchema class (qualified, always works)
    all_schemas = registry.all()                # → {qualified_name: SchemaClass, ...}
    listing = registry.to_listing()             # → [{name, endpoint, label}, ...]
"""
from __future__ import annotations
import importlib
import logging
from typing import TYPE_CHECKING
from django.db import models

if TYPE_CHECKING:
    from apps.schema.base import AdminSchema

logger = logging.getLogger(__name__)


# Django's own apps + known third-party auth/infra apps that should never
# get an auto-generated admin schema. Keyed by app_label (e.g. 'auth'),
# NOT by dotted module path — app_label is never dotted, so a
# startswith('django.') check silently never matches anything.
DJANGO_INTERNAL_APPS = {
    "admin",
    "auth",
    "contenttypes",
    "sessions",
    "sites",
    "messages",
    "staticfiles",
    "rest_framework_simplejwt",
    "token_blacklist",
}

# Substring markers for fields that should never be auto-exposed in a
# dynamically generated list_display. This is a denylist-by-substring,
# which is a stopgap — not a real security boundary. Prefer giving
# models/schemas an explicit `admin_hidden_fields` attribute long-term
# (see _is_sensitive docstring below).
SENSITIVE_FIELD_MARKERS = (
    "password",
    "token",
    "secret",
    "hmac",
    "webhook_payload",
    "medical_history",
    "license_number",
    "ssn",
    "ccn",
    "card",
)


def _is_sensitive(field_name: str) -> bool:
    """
    Heuristic check for fields that shouldn't appear in an auto-generated
    admin list_display. Substring-based, so it's a stopgap: it will not
    catch every sensitive field, and could over-match on a benign field
    that happens to contain one of these substrings (e.g. a field named
    'card_game_id'). Explicit schemas (registered via @register) always
    take precedence over auto-registration, so the real fix for any
    sensitive model is to write an explicit AdminSchema for it rather
    than rely on this filter.
    """
    lowered = field_name.lower()
    return any(marker in lowered for marker in SENSITIVE_FIELD_MARKERS)


class SchemaRegistry:
    def __init__(self):
        # Primary store: qualified key "app_label.ModelName" -> schema class.
        # This is collision-proof by construction (Django guarantees
        # app_label + model name uniqueness within a project).
        self._registry: dict[str, type[AdminSchema]] = {}

        # Convenience index: bare model name -> qualified key, ONLY when
        # unambiguous. If two apps register the same bare model name,
        # this is set to None to force callers to use the qualified form.
        self._bare_index: dict[str, str | None] = {}

    def auto_register_all_models(self):
        """
        Automatically register all models from all apps with a default schema.
        This is called AFTER autodiscover() so explicit schemas take precedence.
        """
        from django.apps import apps as django_apps
        from .base import AdminSchema

        for app_config in django_apps.get_app_configs():
            if app_config.label in DJANGO_INTERNAL_APPS:
                continue

            for model in app_config.get_models():
                qualified_name = self._qualified_name(model)

                # Skip models already registered (explicit schemas win —
                # this includes ones registered under the qualified name
                # by an earlier autodiscover() pass).
                if qualified_name in self._registry:
                    continue

                # Build a sensible default list_display: skip the PK field
                # itself (it's re-added as "id" below) and any sensitive field.
                fields = model._meta.fields
                list_display = ["id"]
                for f in fields:
                    if f.name == "id" or _is_sensitive(f.name):
                        continue
                    if len(list_display) < 5:
                        list_display.append(f.name)

                # Search fields: only CharField and TextField, also filtered
                # for sensitive content (e.g. don't make medical_history
                # searchable-and-displayable by accident).
                search_fields = []
                for f in fields:
                    if _is_sensitive(f.name):
                        continue
                    if isinstance(f, (models.CharField, models.TextField)) and len(search_fields) < 2:
                        search_fields.append(f.name)

                # Endpoint: pluralized model name (fallback)
                endpoint = f"/api/{model._meta.model_name}s/"

                # Dynamically create the schema class
                schema_name = f"{model.__name__}Schema"
                schema_class = type(
                    schema_name,
                    (AdminSchema,),
                    {
                        "model": model,
                        "endpoint": endpoint,
                        "list_display": list_display,
                        "search_fields": search_fields,
                        "ordering": ["-id"],
                    },
                )
                self.register(schema_class)
                logger.info("Auto-registered schema for %s", qualified_name)

    @staticmethod
    def _qualified_name(model) -> str:
        return f"{model._meta.app_label}.{model.__name__}"

    def register(self, schema_class: type[AdminSchema]) -> type[AdminSchema]:
        """
        Decorator / direct call to register a schema.

            @registry.register
            class ProductSchema(AdminSchema): ...

        or

            registry.register(ProductSchema)

        Internally keyed by "app_label.ModelName" so two models sharing a
        bare name (e.g. two different `Payment` models in different apps)
        can never silently overwrite one another. A bare-name convenience
        index is maintained for the common single-model case, and is
        explicitly disabled (forcing qualified lookups) the moment a
        collision is detected.
        """
        model = schema_class.model
        qualified_name = self._qualified_name(model)
        bare_name = model.__name__

        if qualified_name in self._registry:
            logger.warning("Schema '%s' is being overwritten in registry.", qualified_name)
        self._registry[qualified_name] = schema_class

        existing_bare = self._bare_index.get(bare_name, "__unset__")
        if existing_bare == "__unset__":
            self._bare_index[bare_name] = qualified_name
        elif existing_bare is None:
            # already marked ambiguous by an earlier collision; nothing to do
            pass
        elif existing_bare != qualified_name:
            logger.error(
                "Model name collision: '%s' is registered under both '%s' and '%s'. "
                "Bare-name lookups for '%s' are now disabled — use the qualified "
                "form 'app_label.%s' instead.",
                bare_name, existing_bare, qualified_name, bare_name, bare_name,
            )
            self._bare_index[bare_name] = None
        # else: re-registering the same model under the same qualified name — no-op

        logger.debug("Registered schema: %s → %s", qualified_name, schema_class)
        return schema_class

    def get(self, name: str) -> type[AdminSchema] | None:
        """
        Retrieve a schema by name. Accepts either:
          - a qualified name "app_label.ModelName" (always unambiguous), or
          - a bare model name "ModelName" (only works if unambiguous —
            returns None and logs an error if two apps registered the
            same bare model name, rather than silently returning the
            wrong one).

        Case-insensitive on the ModelName portion.
        """
        # Exact qualified match first
        if name in self._registry:
            return self._registry[name]

        # Qualified, case-insensitive match
        if "." in name:
            name_lower = name.lower()
            for key, val in self._registry.items():
                if key.lower() == name_lower:
                    return val
            return None

        # Bare-name lookup via convenience index
        if name in self._bare_index:
            qualified = self._bare_index[name]
            if qualified is None:
                logger.error(
                    "Ambiguous lookup: '%s' matches multiple registered models. "
                    "Use the qualified form 'app_label.%s'.",
                    name, name,
                )
                return None
            return self._registry.get(qualified)

        # Bare-name, case-insensitive fallback
        name_lower = name.lower()
        matches = {
            qname: cls for qname, cls in self._registry.items()
            if qname.rsplit(".", 1)[-1].lower() == name_lower
        }
        if len(matches) == 1:
            return next(iter(matches.values()))
        if len(matches) > 1:
            logger.error(
                "Ambiguous case-insensitive lookup: '%s' matches multiple "
                "registered models (%s). Use the qualified form.",
                name, ", ".join(matches.keys()),
            )
        return None

    def all(self) -> dict[str, type[AdminSchema]]:
        return dict(self._registry)

    def to_listing(self) -> list[dict]:
        """
        Returns a lightweight list of all registered models for the sidebar nav.
        `name` here is the qualified key; bare model name is exposed
        separately as `label` for display purposes.
        """
        return [
            {
                "name": qualified_name,
                "endpoint": cls.endpoint,
                "label": cls.model.__name__,
                "url": f"/admin/{cls.model.__name__.lower()}",
            }
            for qualified_name, cls in sorted(self._registry.items())
        ]

    def autodiscover(self):
        """
        Walk all INSTALLED_APPS and import admin_schema.py from each.
        This triggers @registry.register decorators automatically,
        mirroring how Django's admin.autodiscover() works.
        """
        from django.apps import apps as django_apps

        for app_config in django_apps.get_app_configs():
            module_path = f"{app_config.name}.admin_schema"
            try:
                importlib.import_module(module_path)
                logger.debug("Autodiscovered schema module: %s", module_path)
            except ModuleNotFoundError:
                pass
            except Exception as e:
                logger.error("Error loading schema module %s: %s", module_path, e)


# Global singleton — import this everywhere
registry = SchemaRegistry()