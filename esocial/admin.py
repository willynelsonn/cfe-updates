from django.contrib import admin

from .models import Evento, Lote


@admin.register(Evento)
class EventoAdmin(admin.ModelAdmin):
    list_display = ["tipo", "descricao", "empresa", "status", "recibo", "criado_em"]
    list_filter = ["empresa", "tipo", "status"]


@admin.register(Lote)
class LoteAdmin(admin.ModelAdmin):
    list_display = ["pk", "empresa", "grupo", "protocolo", "status", "criado_em"]
