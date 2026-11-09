from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

from .views import dashboard

urlpatterns = [
    path("", dashboard, name="dashboard"),
    path("entrar/", auth_views.LoginView.as_view(template_name="login.html"), name="login"),
    path("sair/", auth_views.LogoutView.as_view(), name="logout"),
    path("empresas/", include("empresas.urls")),
    path("funcionarios/", include("pessoal.urls")),
    path("folha/", include("folha.urls")),
    path("esocial/", include("esocial.urls")),
    path("admin/", admin.site.urls),
]
