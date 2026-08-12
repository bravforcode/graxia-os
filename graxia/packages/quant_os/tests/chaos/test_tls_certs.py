"""Tests for TLS certificate generation script."""
import os
import shutil
import subprocess
import tempfile

import pytest

SCRIPT = os.path.join(os.path.dirname(__file__), "..", "..", "docker", "generate-certs.sh")
SCRIPT = os.path.normpath(SCRIPT)


@pytest.fixture()
def cert_dir():
    """Generate certs in a temp dir, yield it, then clean up."""
    d = tempfile.mkdtemp(prefix="tls_test_")
    subprocess.run(
        ["bash", SCRIPT, d],
        check=True,
        capture_output=True,
    )
    yield d
    shutil.rmtree(d, ignore_errors=True)


def _cert_files_present(d: str) -> bool:
    return all(
        os.path.isfile(os.path.join(d, f))
        for f in ("ca.key", "ca.crt", "server.key", "server.crt")
    )


@pytest.mark.skipif(
    shutil.which("openssl") is None,
    reason="openssl not available",
)
class TestTLSCertGeneration:
    def test_creates_all_cert_files(self, cert_dir: str):
        assert _cert_files_present(cert_dir), (
            f"Missing cert files in {cert_dir}: {os.listdir(cert_dir)}"
        )

    def test_ca_is_valid_x509(self, cert_dir: str):
        result = subprocess.run(
            ["openssl", "x509", "-in", os.path.join(cert_dir, "ca.crt"), "-noout", "-text"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "Certificate:" in result.stdout

    def test_server_cert_signed_by_ca(self, cert_dir: str):
        result = subprocess.run(
            [
                "openssl", "verify",
                "-CAfile", os.path.join(cert_dir, "ca.crt"),
                os.path.join(cert_dir, "server.crt"),
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"CA verification failed: {result.stderr}"
        assert "OK" in result.stdout

    def test_server_cert_has_correct_san(self, cert_dir: str):
        result = subprocess.run(
            [
                "openssl", "x509", "-in",
                os.path.join(cert_dir, "server.crt"),
                "-noout", "-text",
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        text = result.stdout
        for name in ("graxia-api", "graxia-signal", "graxia-executor", "localhost", "127.0.0.1"):
            assert name in text, f"SAN missing: {name}"

    def test_server_key_matches_cert(self, cert_dir: str):
        cert_mod = subprocess.run(
            ["openssl", "x509", "-in", os.path.join(cert_dir, "server.crt"),
             "-noout", "-modulus"],
            capture_output=True, text=True,
        )
        key_mod = subprocess.run(
            ["openssl", "rsa", "-in", os.path.join(cert_dir, "server.key"),
             "-noout", "-modulus"],
            capture_output=True, text=True,
        )
        assert cert_mod.stdout == key_mod.stdout, "Server key and cert modulus mismatch"
