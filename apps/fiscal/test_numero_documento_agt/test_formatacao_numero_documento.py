from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from apps.fiscal.services.numero_documento_agt import (
    _formatar_numero_documento,
    _normalizar_serie_solicitada,
)


class FormatacaoNumeroDocumentoAGTTests(SimpleTestCase):
    def test_formato_oficial_com_codigo_de_serie_atribuido(self):
        self.assertEqual(
            _formatar_numero_documento("FT", "FT6325S2C", 10006),
            "FT FT6325S2C/10006",
        )

    def test_sequencia_nao_adiciona_zeros_a_esquerda(self):
        self.assertEqual(
            _formatar_numero_documento("FR", "FR6325S2C", 2),
            "FR FR6325S2C/2",
        )

    def test_remove_prefixo_de_tipo_repetido_na_serie_recebida(self):
        self.assertEqual(
            _normalizar_serie_solicitada("FR", "FR FR6325S2C"),
            "FR6325S2C",
        )

    def test_valor_legado_a_nao_e_tomado_como_seriescode_agt(self):
        self.assertIsNone(_normalizar_serie_solicitada("FR", "A"))
        self.assertIsNone(_normalizar_serie_solicitada("FR", "FR FR A"))

    def test_rejeita_serie_com_barra_e_espaco_interno(self):
        with self.assertRaises(ValidationError):
            _normalizar_serie_solicitada("FR", "A/2")
        with self.assertRaises(ValidationError):
            _normalizar_serie_solicitada("FR", "SERIE TESTE")
