from django.contrib import admin

from .models import Competencia, Holerite, ItemHolerite, Lancamento, Rubrica


@admin.register(Rubrica)
class RubricaAdmin(admin.ModelAdmin):
    list_display = ["codigo", "descricao", "empresa", "tipo", "natureza", "inc_cp", "inc_irrf", "inc_fgts", "papel"]
    list_filter = ["empresa", "tipo"]


class ItemInline(admin.TabularInline):
    model = ItemHolerite
    extra = 0


@admin.register(Holerite)
class HoleriteAdmin(admin.ModelAdmin):
    list_display = ["competencia", "funcionario", "total_proventos", "total_descontos", "liquido"]
    inlines = [ItemInline]


admin.site.register(Competencia)
admin.site.register(Lancamento)
