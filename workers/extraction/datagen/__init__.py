"""Test data for the extraction module: images of synthetic report texts (``render``).

Development tooling, like ``evaluation``: the worker never imports it.
"""

from .render import RenderOptions, render_directory, render_report

__all__ = ["RenderOptions", "render_directory", "render_report"]
