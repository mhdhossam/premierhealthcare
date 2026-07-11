# serializers.py
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework import serializers
from datetime import datetime, timedelta
from .models import Booking, DoctorAvailability, Doctor,Notification


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