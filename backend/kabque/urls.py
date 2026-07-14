from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path


def health(_request):
    return JsonResponse({"status": "ok", "service": "KabQue API"})


urlpatterns = [
    path("", health, name="health"),
    path("admin/", admin.site.urls),
    path("api/", include("queueapp.urls")),
]
