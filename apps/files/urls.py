from django.urls import path
from .views import FileListUploadView, FileDetailView
 
urlpatterns = [
    path("files/", FileListUploadView.as_view(), name="file-list-upload"),
    path("files/<int:file_id>/", FileDetailView.as_view(), name="file-detail"),
]