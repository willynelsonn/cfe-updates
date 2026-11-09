from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect


class EmpresaRequiredMixin(LoginRequiredMixin):
    """Exige login e uma empresa selecionada; filtra querysets pela empresa ativa."""

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if request.empresa is None:
            messages.info(request, "Cadastre uma empresa para começar.")
            return redirect("empresas:nova")
        self.empresa = request.empresa
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        return super().get_queryset().filter(empresa=self.empresa)
