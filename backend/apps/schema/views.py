"""
Schema API Views

GET /api/schema/              → list all registered schemas (sidebar nav)
GET /api/schema/<model>/      → full schema for one model
"""
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAdminUser
from rest_framework_simplejwt.authentication import JWTAuthentication

from .registry import registry


class SchemaListView(APIView):
    """
    Returns a lightweight list of all registered admin models.
    Used by React sidebar to build navigation dynamically.

    Response:
        {
          "schemas": [
            { "name": "Product", "endpoint": "/api/products/", "label": "Product", "url": "/admin/product" },
            ...
          ]
        }
    """
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAdminUser]

    def get(self, request):
        return Response({"schemas": registry.to_listing()})


class SchemaDetailView(APIView):
    """
    Returns full schema for a single model.

    Response:
        {
          "name": "Product",
          "endpoint": "/api/products/",
          "list_display": ["id", "name", "price", "created_at"],
          "search_fields": ["name"],
          "ordering": ["-created_at"],
          "fields": [
            { "name": "id", "type": "number", "read_only": true, ... },
            { "name": "name", "type": "string", "max_length": 255, ... },
            { "name": "price", "type": "number", ... },
            { "name": "created_at", "type": "datetime", "read_only": true, ... }
          ]
        }
    """
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAdminUser]

    def get(self, request, model_name: str):
        schema_class = registry.get(model_name)
        if schema_class is None:
            return Response(
                {"error": f"No schema registered for model '{model_name}'."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(schema_class.to_dict())