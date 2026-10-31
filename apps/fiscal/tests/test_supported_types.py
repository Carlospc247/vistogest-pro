"""Testes simples independentes da BD para a lista de tipos API suportados."""
from apps.fiscal.services.agt_payload_builder import AGT_DOCUMENT_TYPES


def test_all_model_types_supported_by_online_agt_are_present():
    expected = {
        "FA", "FT", "FR", "FG", "GF", "AC", "AR", "TV", "RC", "RG",
        "RE", "ND", "NC", "AF", "RP", "RA", "CS", "LD",
    }
    assert AGT_DOCUMENT_TYPES == expected


def test_local_non_api_types_are_not_misrepresented_as_agt_document_types():
    assert "DT" not in AGT_DOCUMENT_TYPES
    assert "FP" not in AGT_DOCUMENT_TYPES
