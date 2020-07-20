"""Enable Sphinx documentation to use MkDocs themes.
"""

import os

from .bridge import EventHandler, MkDocsTemplateBridge

__all__ = ["setup", "MkDocsTemplateBridge"]
__version__ = "0.0.1.dev0"


# Entry point for the sphinx extension
def setup(app):
    app.add_html_theme("mkdocs", os.path.abspath(os.path.dirname(__file__)))
    app.add_config_value("mkdocs_theme", default=None, rebuild="html")

    handler = EventHandler()
    app.connect("config-inited", handler.handle_config_inited)
    app.connect("builder-inited", handler.handle_builder_inited)
    app.connect("html-collect-pages", handler.handle_collect_pages)
