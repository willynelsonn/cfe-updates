from django.contrib import admin

from .models import Empresa


@admin.register(Empresa)
class EmpresaAdmin(admin.ModelAdmin):
    list_display = ["razao_social", "nr_insc", "class_trib", "ambiente_esocial", "ativa"]
    search_fields = ["razao_social", "nome_fantasia", "nr_insc"]
    exclude = ["certificado_senha_cifrada"]
