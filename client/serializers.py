# serializers.py
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework import serializers
from datetime import datetime, timedelta
from .models import Booking, DoctorAvailability,Notification
from.models import CustomUser

class RoleTokenObtainPairSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token['role'] = user.role
        token['is_verified'] = user.is_verified
        return token


class BookingCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Booking
        fields = ['doctor', 'date', 'start_time']

    def validate(self, attrs):
        doctor = attrs['doctor']
        date = attrs['date']
        start_time = attrs['start_time']
        weekday = date.weekday()

        avail = DoctorAvailability.objects.filter(
            doctor=doctor, weekday=weekday,
            start_time__lte=start_time,
        ).first()
        if not avail:
            raise serializers.ValidationError("Doctor not available on this day.")

        end_dt = (datetime.combine(date, start_time) +
                  timedelta(minutes=avail.slot_duration_minutes))
        if end_dt.time() > avail.end_time:
            raise serializers.ValidationError("Slot exceeds doctor's availability window.")

        attrs['end_time'] = end_dt.time()

        exists = Booking.objects.filter(
            doctor=doctor, date=date, start_time=start_time,
            status__in=['pending_payment', 'confirmed']
        ).exists()
        if exists:
            raise serializers.ValidationError("Slot already booked.")

        return attrs


class BookingSerializer(serializers.ModelSerializer):
    class Meta:
        model = Booking
        fields = ['id', 'patient', 'doctor', 'date', 'start_time', 'end_time',
                  'status', 'fee', 'notes', 'created_at']
        read_only_fields = fields

# serializers.py


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ["id", "notification_type", "title", "message", "booking", "is_read", "created_at"]
        read_only_fields = fields



"""
JWT Authentication for admin panel.

Custom TokenObtainPairSerializer that:
1. Enforces is_staff=True (admin-only login)
2. Injects user info into token claims
3. Returns user profile alongside tokens
"""





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
        model = CustomUser
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
