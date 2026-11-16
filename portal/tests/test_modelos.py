from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from empresas.models import Convite
from folha.tests.fabrica import empresa


class ModelosTests(TestCase):
    def test_empresa_nova_nasce_ativa(self):
        self.assertEqual(empresa().situacao, "ativa")

    def test_convite_vale_uma_vez_e_expira_em_7_dias(self):
        emp = empresa()
        staff = User.objects.create_user("escritorio", is_staff=True)
        convite, codigo = Convite.criar(emp, staff)
        self.assertNotIn(codigo, convite.codigo_hash)  # o banco guarda só o hash
        self.assertEqual(Convite.pelo_codigo(codigo), convite)
        self.assertIsNone(Convite.pelo_codigo("codigo-errado"))
        convite.usado_em = timezone.now()
        convite.save()
        self.assertIsNone(Convite.pelo_codigo(codigo))
        velho, codigo_velho = Convite.criar(emp, staff)
        Convite.objects.filter(pk=velho.pk).update(criado_em=timezone.now() - timedelta(days=8))
        self.assertIsNone(Convite.pelo_codigo(codigo_velho))
        novo, codigo_novo = Convite.criar(emp, staff)
        Convite.objects.filter(pk=novo.pk).update(criado_em=timezone.now() - timedelta(days=6))
        self.assertEqual(Convite.pelo_codigo(codigo_novo), novo)
