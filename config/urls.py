from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path
from django.views.generic import RedirectView

from .seguranca import LoginView
from .views import dashboard

urlpatterns = [
    path("", dashboard, name="dashboard"),
    path("entrar/", LoginView.as_view(), name="login"),
    path("sair/", auth_views.LogoutView.as_view(), name="logout"),
    path("empresas/", include("empresas.urls")),
    path("funcionarios/", include("pessoal.urls")),
    path("folha/", include("folha.urls")),
    path("esocial/", include("esocial.urls")),
    # O login do admin passa pela mesma tela com bloqueio de tentativas.
    path("admin/login/", RedirectView.as_view(url="/entrar/?next=/admin/", query_string=False)),
    path("admin/", admin.site.urls),
]
