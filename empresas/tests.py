"""Testes da publicação no servidor: bloqueio de login, backup e .env de produção."""

import os
import tempfile
import zipfile
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase, override_settings


@override_settings(LOGIN_TENTATIVAS_MAX=3, LOGIN_BLOQUEIO_MINUTOS=15)
class BloqueioLoginTests(TestCase):
    def setUp(self):
        cache.clear()
        User.objects.create_user("ana", password="senha-forte-123")
        User.objects.create_user("bruno", password="outra-senha-456")

    def entrar(self, usuario, senha, ip="203.0.113.10"):
        return self.client.post("/entrar/", {"username": usuario, "password": senha}, HTTP_CF_CONNECTING_IP=ip)

    def test_bloqueia_apos_tentativas_erradas_mesmo_com_senha_certa(self):
        for _ in range(3):
            r = self.entrar("ana", "errada")
            self.assertContains(r, "Usuário ou senha incorretos")
        r = self.entrar("ana", "senha-forte-123")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Muitas tentativas erradas")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_bloqueio_por_ip_atinge_outros_usuarios_do_mesmo_ip(self):
        for _ in range(3):
            self.entrar("ana", "errada")
        r = self.entrar("bruno", "outra-senha-456")
        self.assertContains(r, "Muitas tentativas erradas")

    def test_outro_ip_e_outro_usuario_nao_ficam_bloqueados(self):
        for _ in range(3):
            self.entrar("ana", "errada")
        r = self.entrar("bruno", "outra-senha-456", ip="198.51.100.7")
        self.assertEqual(r.status_code, 302)

    def test_login_certo_zera_as_tentativas(self):
        for _ in range(2):
            self.entrar("ana", "errada")
        self.assertEqual(self.entrar("ana", "senha-forte-123").status_code, 302)
        self.client.logout()
        for _ in range(2):
            self.entrar("ana", "errada")
        self.assertEqual(self.entrar("ana", "senha-forte-123").status_code, 302)

    def test_login_do_admin_passa_pela_tela_com_bloqueio(self):
        r = self.client.get("/admin/login/")
        self.assertRedirects(r, "/entrar/?next=/admin/", fetch_redirect_response=False)


class ComandosServidorTests(TestCase):
    def test_garantir_superusuario_cria_e_depois_troca_a_senha(self):
        with patch.dict(os.environ, {"DJANGO_SUPERUSER_USERNAME": "dono", "DJANGO_SUPERUSER_PASSWORD": "primeira-123"}):
            call_command("garantir_superusuario", stdout=StringIO())
        with patch.dict(os.environ, {"DJANGO_SUPERUSER_USERNAME": "dono", "DJANGO_SUPERUSER_PASSWORD": "segunda-456"}):
            call_command("garantir_superusuario", stdout=StringIO())
        dono = User.objects.get(username="dono")
        self.assertTrue(dono.is_superuser)
        self.assertTrue(dono.check_password("segunda-456"))
        self.assertEqual(User.objects.count(), 1)

    def test_preparar_servidor_cria_env_uma_vez_so(self):
        with tempfile.TemporaryDirectory() as tmp, override_settings(BASE_DIR=Path(tmp)):
            call_command("preparar_servidor", stdout=StringIO())
            env = Path(tmp) / ".env"
            conteudo = env.read_text(encoding="utf-8")
            self.assertIn("FOLHA_DEBUG=false", conteudo)
            chave = next(l for l in conteudo.splitlines() if l.startswith("FOLHA_SECRET_KEY="))
            self.assertGreater(len(chave.split("=", 1)[1]), 50)
            env.write_text("FOLHA_SECRET_KEY=minha\n", encoding="utf-8")
            call_command("preparar_servidor", stdout=StringIO())
            self.assertEqual(env.read_text(encoding="utf-8"), "FOLHA_SECRET_KEY=minha\n")

    def test_backup_gera_zip_com_banco_certificados_e_env_e_guarda_os_recentes(self):
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            banco = raiz / "db.sqlite3"
            import sqlite3

            con = sqlite3.connect(banco)
            con.execute("create table t (x)")
            con.execute("insert into t values (42)")
            con.commit()
            con.close()
            privado = raiz / "privado" / "certificados"
            privado.mkdir(parents=True)
            (privado / "empresa.pfx").write_bytes(b"certificado")
            (raiz / ".env").write_text("FOLHA_SECRET_KEY=x\n", encoding="utf-8")
            pasta = raiz / "backups"
            pasta.mkdir()
            for i in range(3):
                (pasta / f"folhaweb-2000010{i}-0000.zip").write_bytes(b"")

            dbs = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": banco}}
            with override_settings(BASE_DIR=raiz, PRIVATE_MEDIA_ROOT=raiz / "privado"), \
                    self.settings(DATABASES=dbs):
                call_command("backup", "--pasta", str(pasta), "--manter", "2", stdout=StringIO())

            zips = sorted(pasta.glob("folhaweb-*.zip"))
            self.assertEqual(len(zips), 2)
            with zipfile.ZipFile(zips[-1]) as z:
                nomes = set(z.namelist())
                self.assertIn("db.sqlite3", nomes)
                self.assertIn(".env", nomes)
                self.assertIn("private_media/certificados/empresa.pfx", nomes)
                copia = Path(tmp) / "copia.sqlite3"
                copia.write_bytes(z.read("db.sqlite3"))
            con = sqlite3.connect(copia)
            self.assertEqual(con.execute("select x from t").fetchone()[0], 42)
            con.close()


class ConfigurarDominioTests(TestCase):
    def test_grava_tunel_libera_dominio_e_salva_endereco(self):
        import json

        from django.core.management.base import CommandError

        with tempfile.TemporaryDirectory() as tmp, override_settings(BASE_DIR=Path(tmp)):
            raiz = Path(tmp)
            (raiz / ".env").write_text(
                "FOLHA_SECRET_KEY=x\nFOLHA_ALLOWED_HOSTS=localhost,127.0.0.1\nFOLHA_CSRF_TRUSTED_ORIGINS=\n",
                encoding="utf-8")
            cred = raiz / "cred.json"
            cred.write_text(json.dumps({"TunnelID": "abc-123"}), encoding="utf-8")
            for _ in range(2):  # rodar de novo não duplica
                call_command("configurar_dominio", "https://Folha.Exemplo.com.br/", "--credenciais", str(cred),
                             stdout=StringIO())
            env = (raiz / ".env").read_text(encoding="utf-8")
            self.assertIn("FOLHA_ALLOWED_HOSTS=localhost,127.0.0.1,folha.exemplo.com.br\n", env)
            self.assertIn("FOLHA_CSRF_TRUSTED_ORIGINS=https://folha.exemplo.com.br\n", env)
            yml = (raiz / "tools" / "cloudflared.yml").read_text(encoding="utf-8")
            self.assertIn("tunnel: abc-123", yml)
            self.assertIn("hostname: folha.exemplo.com.br", yml)
            self.assertIn("service: http://127.0.0.1:8000", yml)
            self.assertEqual((raiz / "ENDERECO.txt").read_text(), "https://folha.exemplo.com.br\n")
            with self.assertRaises(CommandError):
                call_command("configurar_dominio", "não é domínio", "--credenciais", str(cred), stdout=StringIO())


class NuvemTests(TestCase):
    def test_endereco_do_supabase_vira_configuracao_do_banco(self):
        from config.settings import _banco_pela_url

        b = _banco_pela_url("postgresql://postgres.abc:S3nh%40%23@aws-0-sa-east-1.pooler.supabase.com:5432/postgres")
        self.assertEqual(b["ENGINE"], "django.db.backends.postgresql")
        self.assertEqual(b["USER"], "postgres.abc")
        self.assertEqual(b["PASSWORD"], "S3nh@#")
        self.assertEqual(b["HOST"], "aws-0-sa-east-1.pooler.supabase.com")
        self.assertEqual(b["OPTIONS"]["sslmode"], "require")
        self.assertGreater(b["CONN_MAX_AGE"], 0)
        t = _banco_pela_url("postgres://u:p@h:6543/postgres?sslmode=verify-full")
        self.assertEqual(t["CONN_MAX_AGE"], 0)
        self.assertTrue(t["DISABLE_SERVER_SIDE_CURSORS"])
        self.assertEqual(t["OPTIONS"]["sslmode"], "verify-full")

    def test_certificado_guardado_no_banco(self):
        from django.core.files.base import ContentFile

        from empresas.armazenamento import BancoStorage
        from empresas.models import ArquivoPrivado

        st = BancoStorage()
        nome = st.save("certificados/empresa_1_cert.pfx", ContentFile(b"\x30\x82conteudo"))
        self.assertTrue(st.exists(nome))
        self.assertEqual(st.size(nome), len(b"\x30\x82conteudo"))
        with st.open(nome, "rb") as fh:
            self.assertEqual(fh.read(), b"\x30\x82conteudo")
        self.assertEqual(st.listdir("certificados"), ([], ["empresa_1_cert.pfx"]))
        outro = st.save("certificados/empresa_1_cert.pfx", ContentFile(b"novo"))
        self.assertNotEqual(outro, nome)  # não sobrescreve sem querer: gera outro nome
        st.delete(nome)
        self.assertFalse(st.exists(nome))
        self.assertEqual(ArquivoPrivado.objects.count(), 1)
