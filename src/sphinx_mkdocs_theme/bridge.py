"""
"""

import os
import html
import traceback
from importlib.metadata import entry_points

from mkdocs.theme import Theme as MkDocsTheme
from sphinx.application import TemplateBridge
from sphinx.errors import ExtensionError
from sphinx.util import mtimes_of_files

from .translator import ContextTranslator

__all__ = ["MkDocsTemplateBridge", "EventHandler"]


class MkDocsTemplateBridge(TemplateBridge):
    """A TemplateBridge that uses the mkdocs theme's Jinja2 environment for rendering.
    """

    def init(self, builder, theme, dirs=None):
        user_provided = builder.app.config.mkdocs_theme

        # Check that the theme actually exists.
        theme_entry_points = entry_points()["mkdocs.themes"]
        available_themes = {ep.name: ep.value for ep in theme_entry_points}
        if user_provided not in available_themes:
            raise ExtensionError(
                "Could not find mkdocs theme named: {}".format(user_provided)
            )

        self.mkdocs_theme = MkDocsTheme(user_provided)

        self._environment = self.mkdocs_theme.get_env()
        self._translator = ContextTranslator(builder.app, self.mkdocs_theme)

        # TODO: add in configuration from mkdocs_theme into the
        # RawConfigParser at theme.config
        for key in self.mkdocs_theme:
            value = self.mkdocs_theme[key]
            theme.config.set("options", key, value)

    @property
    def translator(self):
        assert hasattr(self, "_translator"), "WHAT."
        return self._translator

    @property
    def environment(self):
        assert hasattr(self, "_environment"), "WHAT."
        return self._environment

    def render(self, template, context):
        try:
            context, template = self._translator.translate(context, template)
            return self._environment.get_template(template).render(context)
        except Exception:
            return (
                "Error occurred in MkDocsTemplateBridge.render()\n"
                f"<pre>{html.escape(traceback.format_exc())}</pre>"
            )

    def render_string(self, source, context):
        try:
            context, _ = self._translator.translate(context, template_name=None)
            return self._environment.from_string(source).render(context)
        except Exception:
            return (
                "Error occurred in MkDocsTemplateBridge.render_string()\n"
                f"<pre>{html.escape(traceback.format_exc())}</pre>"
            )

    def newest_template_mtime(self) -> float:
        return max(mtimes_of_files(self.mkdocs_theme.dirs, ".html"))
