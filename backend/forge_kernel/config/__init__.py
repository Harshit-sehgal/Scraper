"""
Configuration — grouped settings for the product kernel.

Settings are split into focused groups rather than one giant object.
"""

from forge_kernel.config.settings import KernelSettings

settings = KernelSettings()

__all__ = ["settings"]
