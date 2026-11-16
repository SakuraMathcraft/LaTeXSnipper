"""Start and stop the add-in host as one unit.

Starting checks the loopback certificate, starts the HTTPS host and sideloads
the manifest. It never prompts: trusting the certificate is part of
installation (``install.py``), because the host also starts unattended at
login. Stopping removes nothing; uninstalling does.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from latexsnipper_office import certificate, sideload
from latexsnipper_office.assets import OfficeAddinAssets, resolve_assets
from latexsnipper_office.outlines import SystemFontOutlines
from latexsnipper_office.paths import state_directory
from latexsnipper_office.recognition import AutomationRelay
from latexsnipper_office.server import DEFAULT_PORT, OfficeAddinServer
from latexsnipper_office.services import (
    FileChooser,
    OfficeAddinServiceImpl,
    mathjax_version,
    read_symbol_fonts,
)
from latexsnipper_office.typography import SettingsStore
from latexsnipper_office.word_variables import WordVariables


@dataclass(frozen=True)
class Running:
    server: OfficeAddinServer
    manifests: list[Path]


class OfficeAddinError(RuntimeError):
    pass


class CertificateNotTrusted(OfficeAddinError):
    """The certificate is missing, expiring or untrusted; installation must run again."""


def prepare_certificate(
    state: Path, *, interactive: bool
) -> certificate.LocalCertificate:
    """Return a trusted identity, renewing it when needed.

    With ``interactive`` false (login start) a certificate that needs the
    user's approval raises ``CertificateNotTrusted`` instead of prompting.
    """
    try:
        identity, created = certificate.ensure_certificate(state)
        if created or not certificate.is_trusted(identity):
            if not interactive:
                raise CertificateNotTrusted(
                    "Office 加载项证书需要重新信任，请打开 LaTeXSnipper Office 完成设置。"
                )
            certificate.trust(identity)
        if not certificate.is_trusted(identity):
            raise CertificateNotTrusted(
                "macOS 未信任 Office 加载项证书，Office 将无法加载插件页面。"
            )
    except certificate.CertificateError as error:
        raise OfficeAddinError(f"无法设置 Office 加载项证书：{error}") from None
    return identity


def serve(
    *,
    product_version: str,
    files: FileChooser | None,
    interactive: bool,
    port: int = DEFAULT_PORT,
    state: Path | None = None,
    assets: OfficeAddinAssets | None = None,
    home: Path | None = None,
) -> Running:
    state = state or state_directory()
    assets = assets or resolve_assets()
    try:
        assets.validate()
    except FileNotFoundError as error:
        raise OfficeAddinError(str(error)) from None
    identity = prepare_certificate(state, interactive=interactive)

    symbol_fonts = read_symbol_fonts(assets.mathjax)
    services = OfficeAddinServiceImpl(
        settings=SettingsStore(state / "settings.json", symbol_fonts),
        outlines=SystemFontOutlines(),
        relay=AutomationRelay(),
        word_variables=WordVariables(),
        files=files,
        mathjax_version=mathjax_version(assets.mathjax),
    )
    server = OfficeAddinServer(
        assets=assets, certificate=identity, services=services, port=port
    )
    try:
        server.start()
    except OSError as error:
        raise OfficeAddinError(
            f"无法监听 127.0.0.1:{port}，端口可能已被占用。"
        ) from error
    try:
        manifest = sideload.render_manifest(
            assets.manifest_template.read_text(encoding="utf-8"),
            base_url=server.base_url,
            product_version=product_version,
            icons=assets.web / "icons",
        )
        manifests = sideload.install_manifest(manifest, home=home)
    except (OSError, ValueError) as error:
        server.stop()
        raise OfficeAddinError(f"无法安装 Office 加载项清单：{error}") from None
    return Running(server, manifests)
