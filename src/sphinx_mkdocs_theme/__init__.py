"""Enable Sphinx documentation to use MkDocs themes.
"""

import os

from .bridge import MkDocsTemplateBridge
from .builder import MkDocsBuilder

__all__ = ["setup", "MkDocsTemplateBridge"]
__version__ = "0.0.1.dev0"


# Entry point for the sphinx extension
def setup(app):
    app.add_config_value("mkdocs_theme", default=None, rebuild="html")
    app.add_builder(MkDocsBuilder)
