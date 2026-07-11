from django.shortcuts import render
from django.views.decorators.cache import never_cache

@never_cache
def admin_index(request):
    return render(request, 'nexus_admin/index.html')