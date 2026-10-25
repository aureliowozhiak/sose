"""Detached external-issuer authenticity gate for #477 nonconfirmatory bundle.

A valid SHA-256 index proves consistency, not authorship. Independently pinned
public-key material and a detached private-key signature establish issuer proof.
Scientific admission remains NOT_ADMITTED, regardless of the signature.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from hashlib import sha256
from pathlib import Path

from scripts.verify_od5a_477_evidence import verify

SCHEMA = "sose-od5a-477-external-recovery-attestation-v1"
_HEX64 = re.compile(r"[0-9a-f]{64}\Z")


def _canonical(data: dict) -> bytes:
    return (json.dumps(data, sort_keys=True, separators=(",", ":"), allow_nan=False)
            + "\n").encode("utf-8")


def statement(root: Path, *, issuer_id: str) -> bytes:
    """Derive all bundle claims from independently reverified raw arm files."""
    if not isinstance(issuer_id, str) or not issuer_id.strip() or issuer_id != issuer_id.strip():
        raise ValueError("explicit external issuer_id required")
    index = verify(root)
    if (index.get("signature_status") != "UNSIGNED_NO_TRUSTED_ISSUER"
        or index.get("scientific_admission") != "NOT_ADMITTED"
        or index.get("evidence_class") != "NON_CONFIRMATORY"):
        raise ValueError("external attestation only supports nonconfirmatory unsigned evidence")
    return _canonical({
        "schema": SCHEMA,
        "issuer_id": issuer_id,
        "index_sha256": sha256(_canonical(index)).hexdigest(),
        "source_git_oid": index["source_git_oid"],
        "uv_lock_sha256": index["uv_lock_sha256"],
        "evidence_class": "NON_CONFIRMATORY",
        "scientific_admission": "NOT_ADMITTED",
    })


def public_key_fingerprint(public_key: Path) -> str:
    """SHA-256 over DER SubjectPublicKeyInfo, not variable PEM whitespace."""
    try:
        result = subprocess.run(
            ["openssl", "pkey", "-pubin", "-in", str(public_key), "-outform", "DER"],
            check=True, capture_output=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        raise ValueError("trusted public key or OpenSSL cannot be loaded") from exc
    if not result.stdout:
        raise ValueError("trusted public key has no SubjectPublicKeyInfo")
    return sha256(result.stdout).hexdigest()


def verify_attestation(
    root: Path, *, issuer_id: str, trusted_public_key: Path,
    expected_key_sha256: str, signature_path: Path,
) -> dict:
    """Fail closed; never import a signer key or fingerprint from evidence."""
    if not isinstance(expected_key_sha256, str) or not _HEX64.fullmatch(expected_key_sha256):
        raise ValueError("independently pinned 64-digit key SHA-256 is mandatory")
    actual_fingerprint = public_key_fingerprint(trusted_public_key)
    if actual_fingerprint != expected_key_sha256:
        raise ValueError("external trust root fingerprint mismatch")
    content = statement(root, issuer_id=issuer_id)
    if not signature_path.is_file() or not signature_path.read_bytes():
        raise ValueError("external detached signature missing or empty")
    try:
        checked = subprocess.run(
            ["openssl", "dgst", "-sha256", "-verify", str(trusted_public_key),
             "-signature", str(signature_path)],
            input=content, capture_output=True, check=False,
        )
    except FileNotFoundError as exc:
        raise ValueError("OpenSSL signature verifier unavailable") from exc
    if checked.returncode != 0 or b"Verified OK" not in checked.stdout:
        raise ValueError("external detached signature invalid for current bundle")
    return {
        "attestation_schema": SCHEMA,
        "signature_status": "VERIFIED_DETACHED_EXTERNAL_KEY",
        "issuer_id": issuer_id,
        "issuer_public_key_sha256": actual_fingerprint,
        "statement_sha256": sha256(content).hexdigest(),
        "evidence_class": "NON_CONFIRMATORY",
        "scientific_admission": "NOT_ADMITTED",
        # This is AUTHENTICITY of one bounded bundle, not proof that all #477
        # operational/cost/fairness faults were tested or scientifically admitted.
        "issue_477_fully_certified": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path)
    parser.add_argument("--issuer-id", required=True)
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument("--emit-statement", type=Path)
    actions.add_argument("--signature", type=Path)
    parser.add_argument("--trusted-public-key", type=Path)
    parser.add_argument("--expected-key-sha256")
    args = parser.parse_args()
    if args.emit_statement is not None:
        args.emit_statement.write_bytes(statement(args.bundle, issuer_id=args.issuer_id))
        return 0
    if args.trusted_public_key is None or args.expected_key_sha256 is None:
        parser.error("verification requires external public key AND pinned fingerprint")
    result = verify_attestation(
        args.bundle, issuer_id=args.issuer_id,
        trusted_public_key=args.trusted_public_key,
        expected_key_sha256=args.expected_key_sha256,
        signature_path=args.signature,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
