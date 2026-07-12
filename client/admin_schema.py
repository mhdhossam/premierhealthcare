from .models import CustomUser

from apps.schema.registry import registry
from apps.schema.base import AdminSchema, SchemaField


from .models import Doctor, Patient, DoctorAvailability, Booking

from apps.schema.registry import registry
from apps.schema.base import AdminSchema, SchemaField


@registry.register
class DoctorSchema(AdminSchema):
    model = Doctor
    endpoint = "/api/doctors/"
    # license_number omitted from list_display/search — it's a real-world
    # identifier (like an SSN analog for medical licensing), so it stays
    # editable in the detail/edit view but isn't surfaced in the table or
    # made searchable, matching the SENSITIVE_FIELD_MARKERS treatment this
    # field already gets under auto-registration (see registry.py).
    list_display = ["id", "user", "specialization"]
    search_fields = ["specialization"]
    ordering = ["-id"]


@registry.register
class PatientSchema(AdminSchema):
    model = Patient
    endpoint = "/api/patients/"
    # medical_history is PHI — deliberately excluded entirely, not just
    # hidden from the list. Unlike license_number, this shouldn't be
    # casually browsable even in a single-record edit view without a
    # more specific access control story than "is_staff".
    list_display = ["id", "user", "date_of_birth", "phone_number"]
    search_fields = ["phone_number"]
    ordering = ["-id"]
    exclude = ["medical_history"]


@registry.register
class DoctorAvailabilitySchema(AdminSchema):
    model = DoctorAvailability
    endpoint = "/api/doctor-availabilities/"
    list_display = ["id", "doctor", "weekday", "start_time", "end_time", "slot_duration_minutes"]
    search_fields = []
    ordering = ["doctor", "weekday", "start_time"]


@registry.register
class BookingSchema(AdminSchema):
    model = Booking
    endpoint = "/api/bookings/"
    list_display = ["id", "patient", "doctor", "date", "start_time", "status", "fee"]
    search_fields = ["notes"]
    ordering = ["-created_at"]

@registry.register
class UserSchema(AdminSchema):
    model = CustomUser
    endpoint = "/api/users/"
    list_display = ["id", "username", "email", "is_staff", "is_active"]
    search_fields = ["username", "email"]
    ordering = ["-id"]
    exclude = ["password", "user_permissions", "groups"]

