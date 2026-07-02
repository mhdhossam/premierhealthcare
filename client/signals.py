from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import CustomUser, Doctor, Patient, Role


@receiver(post_save, sender=CustomUser)
def create_role_profile(sender, instance, created, **kwargs):
    if not created:
        return
    if instance.role == Role.DOCTOR:
        Doctor.objects.get_or_create(user=instance)
    elif instance.role == Role.PATIENT:
        Patient.objects.get_or_create(user=instance)