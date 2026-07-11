from django.db import models
from django.utils.translation import gettext_lazy as _
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
import uuid
from django.core.validators import MinValueValidator
from django.conf import settings


class NotificationType(models.TextChoices):
    BOOKING_CREATED = "booking_created", "Booking Created"
    BOOKING_CONFIRMED = "booking_confirmed", "Booking Confirmed"
    BOOKING_CANCELLED = "booking_cancelled", "Booking Cancelled"
    PAYMENT_FAILED = "payment_failed", "Payment Failed"


class Notification(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
        db_index=True,
    )
    notification_type = models.CharField(
        max_length=32, choices=NotificationType.choices, db_index=True
    )
    title = models.CharField(max_length=150)
    message = models.CharField(max_length=500)
    booking = models.ForeignKey(
        "Booking",
        on_delete=models.CASCADE,
        related_name="notifications",
        null=True,
        blank=True,
    )
    is_read = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        # covers the hot query: "give me this user's unread, newest first"
        indexes = [
            models.Index(fields=["recipient", "is_read", "-created_at"]),
        ]

    def __str__(self):
        return f"{self.notification_type} -> recipient={self.recipient_id}"


class Role(models.TextChoices):
    ADMIN = 'admin', _('Admin')
    DOCTOR = 'doctor', _('Doctor')
    PATIENT = 'patient', _('Patient')


class CustomUserManager(BaseUserManager):
    def create_user(self, email, username, password=None, **extra_fields):
        if not email:
            raise ValueError("The Email field must be set")
        if not username:
            raise ValueError("The Username field must be set")
        email = self.normalize_email(email)
        user = self.model(email=email, username=username, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, username, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("role", Role.ADMIN)
        extra_fields.setdefault("is_verified", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True")

        return self.create_user(email, username, password, **extra_fields)


class CustomUser(AbstractBaseUser, PermissionsMixin):
    email = models.EmailField(unique=True)
    username = models.CharField(max_length=150, unique=True)
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.PATIENT)
    first_name = models.CharField(max_length=100, blank=True)
    last_name = models.CharField(max_length=100, blank=True)
    is_verified = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)

    objects = CustomUserManager()

    USERNAME_FIELD = 'username'
    REQUIRED_FIELDS = ['email']

    def __str__(self):
        return self.username
    
    def get_full_name(self):
        full = f"{self.first_name} {self.last_name}".strip()
        return full or self.username

    @property
    def is_admin(self):
        return self.role == Role.ADMIN

    @property
    def is_doctor(self):
        return self.role == Role.DOCTOR

    @property
    def is_patient(self):
        return self.role == Role.PATIENT


class Doctor(models.Model):
    user = models.OneToOneField(CustomUser, on_delete=models.CASCADE, related_name='doctor_profile')
    specialization = models.CharField(max_length=100)
    license_number = models.CharField(max_length=50, unique=True)
    bio = models.TextField(blank=True)

    def __str__(self):
        return f"Dr. {self.user.username}"


class Patient(models.Model):
    user = models.OneToOneField(CustomUser, on_delete=models.CASCADE, related_name='patient_profile')
    date_of_birth = models.DateField(null=True, blank=True)
    phone_number = models.CharField(max_length=20, blank=True)
    medical_history = models.TextField(blank=True)

    def __str__(self):
        return self.user.username



class DoctorAvailability(models.Model):
    doctor = models.ForeignKey(Doctor, on_delete=models.CASCADE, related_name='availabilities')
    weekday = models.IntegerField(choices=[(i, d) for i, d in enumerate(
        ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'])])
    start_time = models.TimeField()
    end_time = models.TimeField()
    slot_duration_minutes = models.PositiveIntegerField(default=30)

    class Meta:
        unique_together = ('doctor', 'weekday', 'start_time')


class BookingStatus(models.TextChoices):
    PENDING_PAYMENT = 'pending_payment', 'Pending Payment'
    CONFIRMED = 'confirmed', 'Confirmed'
    CANCELLED = 'cancelled', 'Cancelled'
    COMPLETED = 'completed', 'Completed'
    EXPIRED = 'expired', 'Expired'


class Booking(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='bookings')
    doctor = models.ForeignKey(Doctor, on_delete=models.CASCADE, related_name='bookings')
    date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    status = models.CharField(max_length=20, choices=BookingStatus.choices,
                               default=BookingStatus.PENDING_PAYMENT)
    fee = models.DecimalField(max_digits=8, decimal_places=2, validators=[MinValueValidator(0)])
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['doctor', 'date', 'start_time'],
                condition=models.Q(status__in=['pending_payment', 'confirmed']),
                name='unique_active_slot'
            )
        ]
        indexes = [models.Index(fields=['doctor', 'date'])]

    def __str__(self):
        return f"{self.patient} -> {self.doctor} on {self.date} {self.start_time}"


class PaymentStatus(models.TextChoices):
    PENDING = 'pending', 'Pending'
    PAID = 'paid', 'Paid'
    FAILED = 'failed', 'Failed'
    REFUNDED = 'refunded', 'Refunded'


class Payment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    booking = models.OneToOneField(Booking, on_delete=models.CASCADE, related_name='payment')
    amount = models.DecimalField(max_digits=8, decimal_places=2)
    currency = models.CharField(max_length=3, default='EGP')
    status = models.CharField(max_length=20, choices=PaymentStatus.choices,
                               default=PaymentStatus.PENDING)
    paymob_order_id = models.CharField(max_length=100, blank=True, null=True, db_index=True)
    paymob_transaction_id = models.CharField(max_length=100, blank=True, null=True)
    payment_token = models.TextField(blank=True, null=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    raw_webhook_payload = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.booking_id} - {self.status}"