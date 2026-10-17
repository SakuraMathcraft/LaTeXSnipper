"""Select the native installation adapter without importing Qt."""

from pathlib import Path

from runtime.installed_resources import current_target
from update.deployment_transaction import DeploymentTransaction


def deployment_transaction(root: Path) -> DeploymentTransaction:
    system, _ = current_target()
    if system == "linux":
        from update.debian_transaction import DebianDeploymentTransaction

        return DebianDeploymentTransaction(root)
    if system == "macos":
        from update.macos_transaction import MacOSDeploymentTransaction

        return MacOSDeploymentTransaction(root)
    from update.windows_transaction import WindowsDeploymentTransaction

    return WindowsDeploymentTransaction(root)
