from django.urls import path

from . import views

app_name = "pessoal"
urlpatterns = [
    path("", views.FuncionarioListView.as_view(), name="lista"),
    path("novo/", views.FuncionarioCreateView.as_view(), name="novo"),
    path("<int:pk>/", views.FuncionarioDetailView.as_view(), name="detalhe"),
    path("<int:pk>/editar/", views.FuncionarioUpdateView.as_view(), name="editar"),
    path("<int:pk>/desligar/", views.DesligamentoView.as_view(), name="desligar"),
    path("<int:pk>/dependentes/novo/", views.DependenteCreateView.as_view(), name="dependente_novo"),
    path("dependentes/<int:pk>/excluir/", views.excluir_dependente, name="dependente_excluir"),
    path("cargos/", views.CargoListView.as_view(), name="cargos"),
    path("cargos/<int:pk>/editar/", views.CargoUpdateView.as_view(), name="cargo_editar"),
]
