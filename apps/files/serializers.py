from rest_framework import serializers
from .models import File


class FileSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField()
    size_display = serializers.SerializerMethodField()

    class Meta:
        model = File
        fields = [
            "id",
            "original_name",
            "size",
            "size_display",
            "content_type",
            "extension",
            "url",
            "created_at",
        ]
        read_only_fields = fields

    def get_url(self, obj):
        request = self.context.get("request")
        if request:
            return request.build_absolute_uri(obj.file.url)
        return obj.file.url

    def get_size_display(self, obj):
        size = obj.size
        for unit in ("B", "KB", "MB", "GB"):
            if size < 1024:
                return f"{size:.1f} {unit}" if unit != "B" else f"{size} B"
            size /= 1024
        return f"{size:.1f} TB"