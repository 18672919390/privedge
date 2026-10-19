import hashlib
import json

from privedge.server.version import public_version


def test_public_identifier_tracks_payload_without_reading_private_files(tmp_path):
    def put(name, content):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    put("pyproject.toml", '[project]\nversion="0.4.1"\n')
    put("requirements.lock", "numpy==2.3.5")
    code = put("privedge/core.py", "original")
    page = put("web/dist/index.html", "page")
    data = put("data/meituan_trd/domain.json", "[]")
    secret = put(".env", "PRIVATE_SECRET")
    put("internal_handoff.md", "PRIVATE_INSTRUCTIONS")
    before = public_version(tmp_path)
    assert before["application_version"] == "0.4.1"
    assert before["fingerprint_file_count"] == 4
    assert before["data_sha256"] == {"meituan_trd/domain.json": hashlib.sha256(b"[]").hexdigest()}
    assert str(tmp_path) not in json.dumps(before)
    assert "PRIVATE" not in json.dumps(before)
    secret.write_text("changed credential", encoding="utf-8")
    assert public_version(tmp_path) == before
    code.write_text("changed", encoding="utf-8")
    after_code = public_version(tmp_path)
    assert after_code["source_fingerprint_sha256"] != before["source_fingerprint_sha256"]
    page.write_text("new page", encoding="utf-8")
    after_page = public_version(tmp_path)
    assert after_page["source_fingerprint_sha256"] != after_code["source_fingerprint_sha256"]
    data.write_text('["new"]', encoding="utf-8")
    after_data = public_version(tmp_path)
    assert after_data["source_fingerprint_sha256"] == after_page["source_fingerprint_sha256"]
    assert after_data["data_sha256"] != after_page["data_sha256"]


def test_version_route_returns_json_from_current_payload():
    from fastapi.testclient import TestClient
    from privedge.server.app import app
    response = TestClient(app).get("/api/version")
    assert response.status_code == 200
    assert response.json() == public_version()
    assert response.json()["fingerprint_file_count"] > 40
    assert len(response.json()["data_sha256"]) == 8
