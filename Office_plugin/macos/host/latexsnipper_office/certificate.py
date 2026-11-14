"""Loopback TLS identity for the macOS Office add-in.

Office for Mac only loads add-in pages over HTTPS. The identity is a single
self-signed, non-CA leaf for ``localhost`` and ``127.0.0.1``: trusting it lets
Office reach the local server, and because it cannot sign other certificates a
leaked key never extends trust beyond this machine's loopback service.
"""

from __future__ import annotations

import hashlib
import os
import re
import ssl
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from latexsnipper_office.paths import ensure_private_directory

OPENSSL = "/usr/bin/openssl"
SECURITY = "/usr/bin/security"
CERTIFICATE_NAME = "LaTeXSnipper Office Add-in (localhost)"
# Apple rejects TLS server certificates valid for more than 825 days.
VALIDITY_DAYS = 800
RENEW_BEFORE = timedelta(days=30)

_OPENSSL_CONFIG = f"""[req]
distinguished_name = dn
x509_extensions = ext
prompt = no
[dn]
CN = {CERTIFICATE_NAME}
O = LaTeXSnipper
[ext]
basicConstraints = critical, CA:FALSE
keyUsage = critical, digitalSignature, keyEncipherment
extendedKeyUsage = serverAuth
subjectAltName = DNS:localhost, IP:127.0.0.1
subjectKeyIdentifier = hash
"""


class CertificateError(RuntimeError):
    """The local identity could not be created, trusted, or removed."""


@dataclass(frozen=True)
class LocalCertificate:
    certificate: Path
    private_key: Path

    def exists(self) -> bool:
        return self.certificate.is_file() and self.private_key.is_file()

    def sha1_fingerprint(self) -> str:
        der = ssl.PEM_cert_to_DER_cert(self.certificate.read_text(encoding="utf-8"))
        return hashlib.sha1(der, usedforsecurity=False).hexdigest().upper()

    def expires_at(self) -> datetime:
        output = _run(
            [OPENSSL, "x509", "-noout", "-enddate", "-in", str(self.certificate)]
        )
        value = output.strip().partition("=")[2]
        try:
            parsed = datetime.strptime(value, "%b %d %H:%M:%S %Y %Z")
        except ValueError as error:
            raise CertificateError("无法读取 Office 加载项证书有效期。") from error
        return parsed.replace(tzinfo=timezone.utc)

    def needs_renewal(self, now: datetime | None = None) -> bool:
        if not self.exists():
            return True
        try:
            expires = self.expires_at()
        except CertificateError:
            return True
        return expires - (now or datetime.now(timezone.utc)) < RENEW_BEFORE


def certificate_paths(directory: Path) -> LocalCertificate:
    return LocalCertificate(directory / "localhost.crt", directory / "localhost.key")


def ensure_certificate(directory: Path) -> tuple[LocalCertificate, bool]:
    """Return the identity, creating a new one when missing or near expiry.

    The boolean is ``True`` when a new certificate was written; callers must
    then ask the user to trust it again.
    """

    identity = certificate_paths(directory)
    if not identity.needs_renewal():
        return identity, False
    ensure_private_directory(directory)
    with tempfile.TemporaryDirectory(
        prefix=".office-cert-", dir=directory
    ) as temporary:
        work = Path(temporary)
        config = work / "openssl.cnf"
        config.write_text(_OPENSSL_CONFIG, encoding="utf-8")
        key = work / "localhost.key"
        cert = work / "localhost.crt"
        _run(
            [
                OPENSSL,
                "req",
                "-x509",
                "-newkey",
                "rsa:2048",
                "-nodes",
                "-sha256",
                "-days",
                str(VALIDITY_DAYS),
                "-config",
                str(config),
                "-keyout",
                str(key),
                "-out",
                str(cert),
            ]
        )
        os.chmod(key, 0o600)
        os.chmod(cert, 0o644)
        os.replace(key, identity.private_key)
        os.replace(cert, identity.certificate)
    return identity, True


def is_trusted(identity: LocalCertificate) -> bool:
    """Whether macOS accepts the certificate for SSL with the user's settings."""

    if not identity.exists():
        return False
    try:
        _run(
            [
                SECURITY,
                "verify-cert",
                "-c",
                str(identity.certificate),
                "-p",
                "ssl",
                "-s",
                "localhost",
                "-L",
                "-q",
            ]
        )
    except CertificateError:
        return False
    return True


def trust(identity: LocalCertificate) -> None:
    """Add a user-level SSL trust setting; macOS asks the user to authorize it."""

    if not identity.exists():
        raise CertificateError("Office 加载项证书不存在。")
    _run(
        [
            SECURITY,
            "add-trusted-cert",
            "-r",
            "trustRoot",
            "-p",
            "ssl",
            "-k",
            str(_login_keychain()),
            str(identity.certificate),
        ],
        timeout=300,
    )


def untrust(identity: LocalCertificate) -> None:
    """Remove this add-in's trust setting and keychain item; absent items are fine."""

    if not identity.exists():
        return
    try:
        _run([SECURITY, "remove-trusted-cert", str(identity.certificate)], timeout=300)
    except CertificateError:
        pass
    try:
        _run(
            [
                SECURITY,
                "delete-certificate",
                "-Z",
                identity.sha1_fingerprint(),
                str(_login_keychain()),
            ]
        )
    except CertificateError:
        pass


def _login_keychain() -> Path:
    return Path.home() / "Library/Keychains/login.keychain-db"


def _run(command: list[str], *, timeout: float = 60) -> str:
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise CertificateError(f"无法执行 {Path(command[0]).name}。") from error
    if completed.returncode != 0:
        detail = re.sub(r"\s+", " ", (completed.stderr or completed.stdout).strip())
        raise CertificateError(f"{Path(command[0]).name} 失败：{detail[:300]}")
    return completed.stdout
