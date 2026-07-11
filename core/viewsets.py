"""
Base ViewSet that all admin resource ViewSets inherit from.

Provides:
- JWT authentication enforcement
- IsAdminUser permission
- Standardized error responses
- Audit logging hooks (pre/post save)
"""
from rest_framework import viewsets, status
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework_simplejwt.authentication import JWTAuthentication
import logging

logger = logging.getLogger(__name__)


class AdminModelViewSet(viewsets.ModelViewSet):
    """
    Drop-in replacement for ModelViewSet with admin-level auth enforced.
    All resource viewsets inherit from this.
    """
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAdminUser]

    # Subclasses set this to enable per-model search fields
    search_fields: list[str] = []
    ordering_fields: list[str] = ["id"]
    ordering = ["-id"]
class AdminModelViewSet(viewsets.ModelViewSet):
    # ... existing code ...

    def update(self, request, *args, **kwargs):
        logger.info(f"PATCH data: {request.data}")  # you already have this

        response = super().update(request, *args, **kwargs)
        if response.status_code == status.HTTP_400_BAD_REQUEST:
            logger.error(f"Validation errors: {response.data}")  # <-- add this
        return response
    
    def perform_create(self, serializer):
        instance = serializer.save()
        logger.info(
            "ADMIN_CREATE | model=%s | id=%s | user=%s",
            instance.__class__.__name__,
            instance.pk,
            self.request.user.username,
        )

    def perform_update(self, serializer):
        instance = serializer.save()
        logger.info(
            "ADMIN_UPDATE | model=%s | id=%s | user=%s",
            instance.__class__.__name__,
            instance.pk,
            self.request.user.username,
        )

    def perform_destroy(self, instance):
        logger.info(
            "ADMIN_DELETE | model=%s | id=%s | user=%s",
            instance.__class__.__name__,
            instance.pk,
            self.request.user.username,
        )
        instance.delete()

    def handle_exception(self, exc):
        response = super().handle_exception(exc)
        # Normalize all error bodies to {"error": "...", "detail": ...}
        if response is not None and not isinstance(response.data, dict):
            response.data = {"error": str(response.data)}
        return response