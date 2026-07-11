from django.http import request, response

from core.viewsets import AdminModelViewSet
from .models import Product, Category
from .serializers import ProductSerializer, ProductListSerializer, CategorySerializer


class ProductViewSet(AdminModelViewSet):
    queryset = Product.objects.select_related("category").all()
    serializer_class = ProductSerializer
    search_fields = ["name", "description", "status"]
    ordering_fields = ["id", "name", "price", "stock", "created_at"]
    filterset_fields = ["status", "category"]

    def get_serializer_class(self):
        if self.action == "list":
            return ProductListSerializer
        return ProductSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        status_filter = self.request.query_params.get("status")
        if status_filter:
            qs = qs.filter(status=status_filter)
        return qs
    
    def update(self, request, *args, **kwargs):
        print("Request data:", request.data)
        response = super().update(request, *args, **kwargs)
        if response.status_code == 400:
            print("Validation errors:", response.data)   # ← this one specifically
        return response


class CategoryViewSet(AdminModelViewSet):
    queryset = Category.objects.prefetch_related("products").all()
    serializer_class = CategorySerializer
    search_fields = ["name", "slug"]
    ordering_fields = ["id", "name", "created_at"]