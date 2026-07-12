# serializers.py
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework import serializers
from datetime import datetime, timedelta
from .models import Booking, DoctorAvailability,Notification,CustomUser


class RoleTokenObtainPairSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token['role'] = user.role
        token['is_verified'] = user.is_verified
        return token

# wizard_serializers.py
from rest_framework import serializers
from .models import Department, Service, Branch, Doctor, DoctorAvailability, BranchService, DoctorService


class DepartmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Department
        fields = ["id", "name", "slug", "description", "icon"]


class ServiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Service
        fields = ["id", "name", "slug", "description", "duration_minutes", "default_fee"]


class BranchSerializer(serializers.ModelSerializer):
    # Effective fee for THIS service at THIS branch — resolved in the view
    # via query param, not a static model field, so it's passed through
    # context rather than computed here.
    effective_fee = serializers.SerializerMethodField()

    class Meta:
        model = Branch
        fields = ["id", "name", "address", "city", "phone", "latitude", "longitude", "effective_fee"]

    def get_effective_fee(self, obj):
        service_id = self.context.get("service_id")
        if not service_id:
            return None
        bs = BranchService.objects.filter(branch=obj, service_id=service_id).first()
        return bs.effective_fee if bs else None


class DoctorPublicSerializer(serializers.ModelSerializer):
    name = serializers.CharField(source="user.get_full_name", read_only=True)
    effective_fee = serializers.SerializerMethodField()

    class Meta:
        model = Doctor
        fields = ["id", "name", "specialization", "bio", "effective_fee"]

    def get_effective_fee(self, obj):
        service_id = self.context.get("service_id")
        if not service_id:
            return None
        ds = DoctorService.objects.filter(doctor=obj, service_id=service_id).first()
        if ds and ds.fee_override is not None:
            return ds.fee_override
        branch_id = self.context.get("branch_id")
        if branch_id:
            bs = BranchService.objects.filter(branch_id=branch_id, service_id=service_id).first()
            if bs:
                return bs.effective_fee
        return None


class AvailableSlotSerializer(serializers.Serializer):
    """Not a ModelSerializer — slots are computed, not stored rows."""
    date = serializers.DateField()
    start_time = serializers.TimeField()
    end_time = serializers.TimeField()
# serializers.py — replace BookingCreateSerializer with this version

class BookingCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Booking
        fields = ['doctor', 'service', 'branch', 'date', 'start_time']

    def validate(self, attrs):
        doctor = attrs['doctor']
        service = attrs['service']
        branch = attrs['branch']
        date = attrs['date']
        start_time = attrs['start_time']
        weekday = date.weekday()

        # Doctor must actually offer this service at this branch —
        # otherwise a crafted request could book a doctor/service/branch
        # combination that was never validated through the wizard steps.
        if not doctor.branches.filter(id=branch.id).exists():
            raise serializers.ValidationError("Doctor does not work at this branch.")
        if not doctor.services.filter(id=service.id).exists():
            raise serializers.ValidationError("Doctor does not offer this service.")

        avail = DoctorAvailability.objects.filter(
            doctor=doctor, branch=branch, weekday=weekday,
            start_time__lte=start_time,
        ).first()
        if not avail:
            raise serializers.ValidationError("Doctor not available at this branch on this day.")

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
            "role",
            "last_name",
            "is_staff",
            "is_superuser",
            "is_active",
           
            
        ]
        read_only_fields = ["id", "is_superuser"]

    def validate(self, attrs):
        # Prevent demoting your own account via API
        request = self.context.get("request")
        if request and request.user == self.instance:
            if "is_staff" in attrs and not attrs["is_staff"]:
                raise serializers.ValidationError(
                    {"is_staff": "Cannot remove your own staff privileges."}
                )
        return attrs
