from django.urls import path

from . import views

app_name = "portal"

urlpatterns = [
    path("cliente/", views.inicio, name="inicio"),
    path("cadastro/", views.cadastro, name="cadastro"),
    path("termos/", views.termos, name="termos"),
    path("privacidade/", views.privacidade, name="privacidade"),
    path("convite/<str:codigo>/", views.convite, name="convite"),
]
