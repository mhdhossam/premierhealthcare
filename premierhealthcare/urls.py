
from premierhealthcare import settings
from django.contrib import admin
from django.urls import path, include, re_path
from django.conf.urls.static import static
from rest_framework_simplejwt.views import TokenRefreshView
from apps.users.views import AdminTokenObtainPairView, AdminTokenVerifyView, AdminLogoutView
from core.views import admin_index
urlpatterns = [
    path('django-admin/', admin.site.urls),
    path('api/', include('client.urls')),


    path("django-admin/", admin.site.urls),

    # Auth
    path("api/auth/login/",   AdminTokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("api/auth/refresh/", TokenRefreshView.as_view(),          name="token_refresh"),
    path("api/auth/verify/",  AdminTokenVerifyView.as_view(),      name="token_verify"),
    path("api/auth/logout/",  AdminLogoutView.as_view(),           name="token_logout"),
    re_path(r'^admin/.*$', admin_index, name='admin_index'),
    # Resource APIs
    path("api/", include("apps.products.urls")),
    path("api/", include("apps.users.urls")),
    path("api/", include("apps.files.urls")),   # ← new

    # Schema (sidebar auto-population)
    path("api/schema/", include("apps.schema.urls")),  # Include the client app's URLs
]
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)




