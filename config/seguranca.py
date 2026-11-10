"""Login com bloqueio após tentativas erradas (proteção contra adivinhação de senha)."""

from django.conf import settings
from django.contrib.auth import views as auth_views
from django.contrib.auth.forms import AuthenticationForm
from django.core.cache import cache
from django.core.exceptions import ValidationError


def ip_do_cliente(request) -> str:
    # Atrás do Cloudflare Tunnel o servidor só escuta em 127.0.0.1; o IP real vem da Cloudflare.
    return (request.META.get("HTTP_CF_CONNECTING_IP") or request.META.get("REMOTE_ADDR") or "?").strip()


def _chaves(request, usuario: str) -> list[str]:
    return [f"login-falhas:ip:{ip_do_cliente(request)}", f"login-falhas:usuario:{(usuario or '').lower()}"]


class LoginComBloqueioForm(AuthenticationForm):
    def clean(self):
        usuario = self.data.get("username", "")
        chaves = _chaves(self.request, usuario)
        limite = settings.LOGIN_TENTATIVAS_MAX
        if any(cache.get(c, 0) >= limite for c in chaves):
            raise ValidationError(
                f"Muitas tentativas erradas. Aguarde {settings.LOGIN_BLOQUEIO_MINUTOS} minutos e tente de novo.",
                code="bloqueado",
            )
        try:
            return super().clean()
        except ValidationError:
            segundos = settings.LOGIN_BLOQUEIO_MINUTOS * 60
            for c in chaves:
                cache.set(c, cache.get(c, 0) + 1, segundos)
            raise


class LoginView(auth_views.LoginView):
    template_name = "login.html"
    authentication_form = LoginComBloqueioForm
    redirect_authenticated_user = True

    def form_valid(self, form):
        cache.delete_many(_chaves(self.request, form.cleaned_data.get("username", "")))
        return super().form_valid(form)
