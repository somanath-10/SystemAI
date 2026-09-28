from systemai.execution.cua_cli import _parse_json_output


def test_parse_json_output_accepts_direct_json():
    assert _parse_json_output('{"effect":"confirmed"}') == {"effect": "confirmed"}


def test_parse_json_output_accepts_diagnostic_prefix():
    value = _parse_json_output('diagnostic line\n{"effect":"unverifiable","verified":false}\n')
    assert value["effect"] == "unverifiable"
    assert value["verified"] is False
