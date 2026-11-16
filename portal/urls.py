from django.urls import path

from . import views

app_name = "portal"

urlpatterns = [
    path("cliente/", views.inicio, name="inicio"),
]
