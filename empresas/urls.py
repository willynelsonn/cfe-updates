from django.urls import path

from . import views

app_name = "empresas"
urlpatterns = [
    path("", views.EmpresaListView.as_view(), name="lista"),
    path("nova/", views.EmpresaCreateView.as_view(), name="nova"),
    path("<int:pk>/editar/", views.EmpresaUpdateView.as_view(), name="editar"),
    path("<int:pk>/selecionar/", views.selecionar, name="selecionar"),
    path("<int:pk>/certificado/", views.certificado, name="certificado"),
]
