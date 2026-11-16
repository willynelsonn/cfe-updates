from django.urls import path

from . import escritorio, pedidos, views

app_name = "portal"

urlpatterns = [
    path("cliente/", views.inicio, name="inicio"),
    path("cliente/pedidos/", pedidos.lista, name="pedidos"),
    path("cliente/pedidos/novo/", pedidos.novo, name="pedido_novo"),
    path("cliente/pedidos/novo/<slug:tipo>/", pedidos.criar, name="pedido_criar"),
    path("cliente/pedidos/<int:pk>/", pedidos.pedido, name="pedido"),
    path("cliente/pedidos/<int:pk>/corrigir/", pedidos.corrigir, name="pedido_corrigir"),
    path("cliente/pedidos/<int:pk>/cancelar/", pedidos.cancelar, name="pedido_cancelar"),
    path("cliente/pedidos/<int:pk>/anexos/<int:anexo>/", pedidos.anexo, name="pedido_anexo"),
    path("pedidos/", escritorio.lista, name="escritorio_pedidos"),
    path("pedidos/<int:pk>/", escritorio.pedido, name="escritorio_pedido"),
    path("pedidos/<int:pk>/aprovar/", escritorio.aprovar, name="escritorio_aprovar"),
    path("pedidos/<int:pk>/anexos/<int:anexo>/", escritorio.anexo, name="escritorio_anexo"),
    path("cadastro/", views.cadastro, name="cadastro"),
    path("termos/", views.termos, name="termos"),
    path("privacidade/", views.privacidade, name="privacidade"),
    path("convite/<str:codigo>/", views.convite, name="convite"),
]
