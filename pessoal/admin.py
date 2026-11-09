from django.contrib import admin

from .models import Cargo, Dependente, Funcionario


class DependenteInline(admin.TabularInline):
    model = Dependente
    extra = 0


@admin.register(Funcionario)
class FuncionarioAdmin(admin.ModelAdmin):
    list_display = ["matricula", "nome", "cpf", "empresa", "data_admissao", "data_desligamento"]
    list_filter = ["empresa"]
    search_fields = ["nome", "cpf", "matricula"]
    inlines = [DependenteInline]


admin.site.register(Cargo)
