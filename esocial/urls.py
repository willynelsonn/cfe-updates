from django.urls import path

from . import views

app_name = "esocial"
urlpatterns = [
    path("", views.EventoListView.as_view(), name="eventos"),
    path("guia/", views.guia, name="guia"),
    path("lotes/", views.LoteListView.as_view(), name="lotes"),
    path("evento/<int:pk>/", views.EventoDetailView.as_view(), name="evento"),
    path("evento/<int:pk>/xml/", views.baixar_xml, name="xml"),
    path("evento/<int:pk>/reenviar/", views.reenviar_evento, name="reenviar"),
    path("evento/<int:pk>/regerar/", views.regerar_evento, name="regerar"),
    path("gerar-iniciais/", views.gerar_iniciais, name="gerar_iniciais"),
    path("funcionario/<int:pk>/admissao/", views.admissao, name="admissao"),
    path("funcionario/<int:pk>/desligamento/", views.desligamento, name="desligamento"),
    path("transmitir/", views.transmitir, name="transmitir"),
    path("consultar/", views.consultar, name="consultar"),
    path("processar.json", views.processar_json, name="processar_json"),
    path("situacao.json", views.situacao_json, name="situacao_json"),
]
