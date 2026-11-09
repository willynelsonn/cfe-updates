from django.urls import path

from . import views

app_name = "folha"
urlpatterns = [
    path("", views.CompetenciaListView.as_view(), name="competencias"),
    path("nova/", views.CompetenciaCreateView.as_view(), name="competencia_nova"),
    path("<int:pk>/", views.competencia, name="competencia"),
    path("<int:pk>/datas/", views.CompetenciaUpdateView.as_view(), name="competencia_editar"),
    path("<int:pk>/lancamentos/", views.novo_lancamento, name="lancamento_novo"),
    path("lancamentos/<int:pk>/excluir/", views.excluir_lancamento, name="lancamento_excluir"),
    path("<int:pk>/calcular/", views.calcular, name="calcular"),
    path("<int:pk>/fechar/", views.fechar, name="fechar"),
    path("<int:pk>/apurar/", views.apurar, name="apurar"),
    path("<int:pk>/holerites/", views.holerites_impressao, name="holerites_impressao"),
    path("<int:pk>/guias/", views.guias, name="guias"),
    path("<int:pk>/guias/gerar/", views.gerar_guias, name="gerar_guias"),
    path("guias/<int:pk>/pdf/", views.guia_pdf, name="guia_pdf"),
    path("guias/<int:pk>/paga/", views.guia_paga, name="guia_paga"),
    path("holerite/<int:pk>/", views.holerite, name="holerite"),
    path("13-salario/", views.decimo_terceiro, name="decimo_terceiro"),
    path("ferias/", views.FeriasListView.as_view(), name="ferias"),
    path("ferias/nova/", views.ferias_nova, name="ferias_nova"),
    path("ferias/<int:pk>/", views.ferias_detalhe, name="ferias_detalhe"),
    path("ferias/<int:pk>/cancelar/", views.ferias_cancelar, name="ferias_cancelar"),
    path("ferias/<int:pk>/<str:doc>/", views.ferias_documento, name="ferias_documento"),
    path("rubricas/", views.RubricaListView.as_view(), name="rubricas"),
    path("rubricas/nova/", views.RubricaCreateView.as_view(), name="rubrica_nova"),
    path("rubricas/<int:pk>/editar/", views.RubricaUpdateView.as_view(), name="rubrica_editar"),
]
