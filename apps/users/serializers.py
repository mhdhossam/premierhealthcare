"""
JWT Authentication for admin panel.

Custom TokenObtainPairSerializer that:
1. Enforces is_staff=True (admin-only login)
2. Injects user info into token claims
3. Returns user profile alongside tokens
"""
from django.contrib.auth import get_user_model
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.tokens import RefreshToken

User = get_user_model()


class AdminTokenObtainPairSerializer(TokenObtainPairSerializer):
    """
    Override to:
    - Block non-staff users from obtaining admin tokens
    - Embed user claims into access token payload
    """

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        # Custom claims embedded in JWT payload
        token["username"] = user.username
        token["email"] = user.email
        token["is_staff"] = user.is_staff
        token["is_superuser"] = user.is_superuser
        return token

    def validate(self, attrs):
        data = super().validate(attrs)

        # Admin-only gate: reject non-staff at token issuance
        if not self.user.is_staff:
            raise serializers.ValidationError(
                {"detail": "Admin access required. Your account does not have staff privileges."}
            )

        # Augment response with user profile
        data["user"] = {
            "id": self.user.id,
            "username": self.user.username,
            "email": self.user.email,
            "first_name": self.user.first_name,
            "last_name": self.user.last_name,
            "is_staff": self.user.is_staff,
            "is_superuser": self.user.is_superuser,
        }
        return data


class AdminUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "is_staff",
            "is_superuser",
            "is_active",
            "date_joined",
            "last_login",
        ]
        read_only_fields = ["id", "date_joined", "last_login"]

    def validate(self, attrs):
        # Prevent demoting your own account via API
        request = self.context.get("request")
        if request and request.user == self.instance:
            if "is_staff" in attrs and not attrs["is_staff"]:
                raise serializers.ValidationError(
                    {"is_staff": "Cannot remove your own staff privileges."}
                )
        return attrs