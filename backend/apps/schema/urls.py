from django.urls import path
from .views import SchemaListView, SchemaDetailView

urlpatterns = [
    path("",               SchemaListView.as_view(),              name="schema-list"),
    path("<str:model_name>/", SchemaDetailView.as_view(),         name="schema-detail"),
]