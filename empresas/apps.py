from django.apps import AppConfig
from django.db.models.signals import post_migrate


def proteger_tabelas_postgres(using="default", **kwargs):
    """No Supabase, fecha a API pública (PostgREST) para as tabelas do sistema.

    O Supabase expõe o schema "public" pela Data API aos papéis anon/authenticated. Ligamos o
    RLS (sem políticas, ninguém de fora lê nada) e retiramos os privilégios desses papéis.
    O FolhaWeb conecta como dono das tabelas, que não é afetado pelo RLS.
    """
    from django.db import connections

    conn = connections[using]
    if conn.vendor != "postgresql":
        return
    with conn.cursor() as cur:
        cur.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
        for (tabela,) in cur.fetchall():
            cur.execute(f'ALTER TABLE public."{tabela}" ENABLE ROW LEVEL SECURITY')
        cur.execute("SELECT rolname FROM pg_roles WHERE rolname IN ('anon', 'authenticated')")
        papeis = [r[0] for r in cur.fetchall()]
        if papeis:
            lista = ", ".join(papeis)
            cur.execute(f"REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {lista}")
            cur.execute(f"REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM {lista}")


class EmpresasConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "empresas"

    def ready(self):
        post_migrate.connect(proteger_tabelas_postgres, sender=self, dispatch_uid="folha-proteger-postgres")
