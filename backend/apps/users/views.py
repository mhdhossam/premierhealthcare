"""
Auth views for the headless admin panel.

Endpoints:
  POST /api/auth/login/    → obtain access + refresh tokens
  POST /api/auth/refresh/  → rotate access token (handled by simplejwt default)
  POST /api/auth/verify/   → verify token validity
  POST /api/auth/logout/   → blacklist refresh token
  GET/PUT /api/users/<id>/ → manage admin users (CRUD)
"""
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenVerifyView,
)
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError

from core.viewsets import AdminModelViewSet
from .serializers import AdminTokenObtainPairSerializer, AdminUserSerializer

User = get_user_model()


class AdminTokenObtainPairView(TokenObtainPairView):
    """Login endpoint — returns access + refresh + user profile."""
    serializer_class = AdminTokenObtainPairSerializer


class AdminTokenVerifyView(TokenVerifyView):
    """Verify token validity. Returns 200 if valid, 401 if not."""
    pass


class AdminLogoutView(APIView):
    """
    Blacklists the refresh token on logout.
    Requires: { "refresh": "<token>" } in body.
    """
    def post(self, request):
        refresh_token = request.data.get("refresh")
        if not refresh_token:
            return Response(
                {"error": "Refresh token is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            token = RefreshToken(refresh_token)
            token.blacklist()
            return Response({"detail": "Successfully logged out."}, status=status.HTTP_200_OK)
        except TokenError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class AdminUserViewSet(AdminModelViewSet):
    """
    CRUD for admin user management.
    Only superusers can manage other users.
    """
    queryset = User.objects.filter(is_staff=True).order_by("-date_joined")
    serializer_class = AdminUserSerializer
    search_fields = ["username", "email", "first_name", "last_name"]
    ordering_fields = ["id", "username", "date_joined", "last_login"]

    def get_permissions(self):
        # Creating/deleting users requires superuser
        from rest_framework.permissions import IsAdminUser
        from core.permissions import IsSuperUser
        if self.action in ("create", "destroy"):
            return [IsSuperUser()]
        return [IsAdminUser()]