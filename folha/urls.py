from django.urls import path

from . import views

app_name = "folha"
urlpatterns = [
    path("", views.CompetenciaListView.as_view(), name="competencias"),
    path("nova/", views.CompetenciaCreateView.as_view(), name="competencia_nova"),
    path("<int:pk>/", views.CompetenciaDetailView.as_view(), name="competencia"),
    path("<int:pk>/lancamentos/", views.novo_lancamento, name="lancamento_novo"),
    path("lancamentos/<int:pk>/excluir/", views.excluir_lancamento, name="lancamento_excluir"),
    path("<int:pk>/calcular/", views.calcular, name="calcular"),
    path("<int:pk>/fechar/", views.fechar, name="fechar"),
    path("<int:pk>/holerites/", views.holerites_impressao, name="holerites_impressao"),
    path("holerite/<int:pk>/", views.holerite, name="holerite"),
    path("rubricas/", views.RubricaListView.as_view(), name="rubricas"),
    path("rubricas/nova/", views.RubricaCreateView.as_view(), name="rubrica_nova"),
    path("rubricas/<int:pk>/editar/", views.RubricaUpdateView.as_view(), name="rubrica_editar"),
]
