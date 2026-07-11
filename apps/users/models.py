from django.db import models

from django.utils.translation import gettext_lazy as _
from django.contrib.auth.models import User

# class jointeam(models.Model):
#     user=models.OneToOneField(User,related_name='jointeam', on_delete=models.CASCADE)
#     name=models.CharField(max_length=40,null=True,blank=True)
#     email=models.EmailField(max_length=40,unique=True,blank=True)
#     linkedin_profile=models.CharField(max_length=40,null=True,blank=True)
#     phonenumber=models.CharField(max_length=40,null=True,blank=True)
#     portfolio=models.CharField(max_length=200,null=True,blank=True)
#     resume=models.FileField(upload_to='resumes/')
#     created_at=models.DateTimeField(auto_now_add=True)
#     update_at=models.DateTimeField(auto_now=True)
#     class Meta:
#         ordering=['-created_at'] 

#     def __str__(self):
#         return self.user.username