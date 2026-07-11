from django.core.exceptions import PermissionDenied, ObjectDoesNotExist

from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework import status

from core.services.files import upload_file, get_user_files, delete_file
from .serializers import FileSerializer


class FileListUploadView(APIView):
    """
    GET  /api/files/        — list all files for the current admin user
    POST /api/files/        — upload a new file (multipart/form-data, field: "file")
    """
    permission_classes = [IsAdminUser]
    parser_classes = [MultiPartParser, FormParser]

    def get(self, request):
        files = get_user_files(request.user)
        serializer = FileSerializer(files, many=True, context={"request": request})
        return Response(serializer.data)

    def post(self, request):
        uploaded = request.FILES.get("file")
        if not uploaded:
            return Response(
                {"detail": "No file provided. Send a multipart/form-data request with field 'file'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        instance = upload_file(request.user, uploaded)
        serializer = FileSerializer(instance, context={"request": request})
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class FileDetailView(APIView):
    """
    DELETE /api/files/<id>/  — delete a file (owner only)
    """
    permission_classes = [IsAdminUser]

    def delete(self, request, file_id):
        try:
            delete_file(request.user, file_id)
            return Response(status=status.HTTP_204_NO_CONTENT)
        except ObjectDoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        except PermissionDenied:
            return Response({"detail": "You do not own this file."}, status=status.HTTP_403_FORBIDDEN)