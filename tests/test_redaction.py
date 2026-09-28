from systemai.security.redaction import persistence_safe


def test_persistence_safe_redacts_screenshot_payloads():
    out = persistence_safe({"screenshot_png_b64": "A" * 100, "ok": True})
    assert out["ok"] is True
    assert out["screenshot_png_b64"]["redacted"] is True
    assert out["screenshot_png_b64"]["characters"] == 100
