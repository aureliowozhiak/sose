"""#477: external detached issuer cannot be self-asserted by bundle contents."""
from __future__ import annotations

import json
import shutil
import subprocess

import pytest

from scripts.verify_od5a_477_attestation import (
    public_key_fingerprint, statement, verify_attestation,
)
from tests.unit.sose.organizational.test_od5a_477_recovery_evidence import _bundle


ISSUER = "od5a:operational-validation-issuer"


@pytest.fixture
def signed_bundle(tmp_path):
    if shutil.which("openssl") is None:
        pytest.fail("OpenSSL mandatory for detached issuer authenticity gate")
    root = _bundle(tmp_path / "raw-five-arm-evidence")
    private = tmp_path / "private-test-only.pem"
    public = tmp_path / "public-trusted.pem"
    signature = tmp_path / "detached-issuer.sig"
    subprocess.run(
        ["openssl", "genpkey", "-algorithm", "RSA", "-pkeyopt", "rsa_keygen_bits:2048",
         "-out", str(private)],
        capture_output=True, check=True,
    )
    subprocess.run(
        ["openssl", "pkey", "-in", str(private), "-pubout", "-out", str(public)],
        capture_output=True, check=True,
    )
    subprocess.run(
        ["openssl", "dgst", "-sha256", "-sign", str(private),
         "-out", str(signature)],
        input=statement(root, issuer_id=ISSUER), capture_output=True, check=True,
    )
    return root, public, signature, public_key_fingerprint(public)


def _verify(data, **options):
    root, public, signature, fingerprint = data
    return verify_attestation(
        root, issuer_id=options.get("issuer_id", ISSUER),
        trusted_public_key=options.get("public", public),
        signature_path=options.get("signature", signature),
        expected_key_sha256=options.get("fingerprint", fingerprint),
    )


def test_detached_signature_requires_independently_pinned_trust_root(signed_bundle):
    result = _verify(signed_bundle)
    assert result["signature_status"] == "VERIFIED_DETACHED_EXTERNAL_KEY"
    assert result["issuer_id"] == ISSUER
    assert result["evidence_class"] == "NON_CONFIRMATORY"
    assert result["scientific_admission"] == "NOT_ADMITTED"
    assert result["issue_477_fully_certified"] is False


def test_mutated_valid_evidence_invalidates_detached_signature(signed_bundle):
    root = signed_bundle[0]
    baseline = root / "baseline.json"
    record = json.loads(baseline.read_text())
    # Still internally coherent: only the detached external signature detects
    # modification to the originally approved experiment identity.
    record["model_spec_hash"] = "9" * 64
    baseline.write_text(json.dumps(record))
    with pytest.raises(ValueError, match="external detached signature invalid"):
        _verify(signed_bundle)


def test_bundle_cannot_replace_independent_pinned_key_fingerprint(signed_bundle):
    with pytest.raises(ValueError, match="trust root fingerprint mismatch"):
        _verify(signed_bundle, fingerprint="f" * 64)


def test_wrong_issuer_identity_and_empty_signature_fail_closed(signed_bundle, tmp_path):
    with pytest.raises(ValueError, match="external detached signature invalid"):
        _verify(signed_bundle, issuer_id="foreign:untrusted")
    empty = tmp_path / "absent.sig"
    with pytest.raises(ValueError, match="external detached signature missing"):
        _verify(signed_bundle, signature=empty)


def test_unpinned_external_key_cannot_be_used_as_root(signed_bundle):
    with pytest.raises(ValueError, match="independently pinned"):
        _verify(signed_bundle, fingerprint="")


def test_no_scientific_promotion_by_attestation(signed_bundle):
    root = signed_bundle[0]
    record = json.loads((root / "baseline.json").read_text())
    record["scientific_admission"] = "ADMITTED"
    (root / "baseline.json").write_text(json.dumps(record))
    with pytest.raises(ValueError, match="provenance"):
        _verify(signed_bundle)
