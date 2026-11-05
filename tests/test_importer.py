"""Round trip of a sealed drop and the China directory adapter's rules (no network, temporary key)."""
import base64, gzip, json, tempfile
from pathlib import Path

import leads.importer as im


def test_seal_roundtrip():
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding, rsa
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    d = Path(tempfile.mkdtemp())
    im.DIR, im.PUB = d, d / "pub.pem"
    im.PUB.write_bytes(priv.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
    src = d / "rows.jsonl"; src.write_text('{"supplier": "国家电网有限公司", "country": "CHN"}\n', encoding="utf-8")
    b = json.loads(im.seal(str(src), "test-drop").read_text())
    assert "国家" not in json.dumps(b)  # nothing readable in the sealed file
    key = priv.decrypt(base64.b64decode(b["wrapped"]), padding.OAEP(mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=None))
    raw = gzip.decompress(AESGCM(key).decrypt(base64.b64decode(b["nonce"]), base64.b64decode(b["data"]), b"test-drop")).decode()
    assert json.loads(raw)["supplier"] == "国家电网有限公司"


def test_china_adapter():
    f = Path(tempfile.mkdtemp()) / "c.json"
    f.write_text(json.dumps({"companies": [{"company_id": "CN-1", "company_name_zh": "测试有限公司", "company_name_en": None, "location": {"province_en": "Hunan"},
        "industry": {"en": "Advanced materials"}, "products": [], "website": None, "contacts": {"emails": [{"value": "support@x.cn", "commercial": False}], "phones": []},
        "selection_evidence": [{"type": "reported_national_specialized_sme_recognition", "year": 2021, "source_url": "https://s"}], "financials": None, "quality_flags": []}],
        "supplemental_contact_candidates": [{"company_name_en_as_reported": "Acme", "country_as_reported": "China", "email_as_reported": "old@acme.cn",
                                             "current_page_check": {"outcome": "page_read", "previous_email_present": []}},
                                            {"company_name_en_as_reported": "NotRead", "current_page_check": {"outcome": "not_read"}}]}), encoding="utf-8")
    r = im.china_directory(str(f))
    assert r[0]["supplier"] == "测试有限公司" and r[0]["email"] == "" and not r[0]["notable"]  # a support (non-commercial) mailbox is not a sales contact
    assert len(r) == 2 and r[1]["email"] == ""  # an address no longer on the current page is left out; unread pages stay out


if __name__ == "__main__":
    test_seal_roundtrip(); test_china_adapter()
    print("importer: all checks passed")
