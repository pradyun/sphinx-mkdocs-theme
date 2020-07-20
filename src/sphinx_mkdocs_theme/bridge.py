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
        pass  # no-op

    def actually_init(self, app):
        user_provided = app.config.mkdocs_theme

        # Check that the theme actually exists.
        theme_entry_points = entry_points()["mkdocs.themes"]
        available_themes = {ep.name: ep.value for ep in theme_entry_points}
        if user_provided not in available_themes:
            raise ExtensionError(
                "Could not find mkdocs theme named: {}".format(user_provided)
            )

        self.mkdocs_theme = MkDocsTheme(user_provided)

        self._environment = self.mkdocs_theme.get_env()
        self._translator = ContextTranslator(app, self.mkdocs_theme)

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


class EventHandler:
    """Handles Sphinx events, modifying behaviours to mimic mkdocs' output.

    The methods are ordered in the order that they would have their first-calls.
    """

    # https://www.sphinx-doc.org/en/3.x/extdev/appapi.html#event-config-inited
    def handle_config_inited(self, app, config):
        if config.html_theme != "mkdocs":
            # Do nothing if this is not used with the "mkdocs" theme.
            return

        # Check that we got a theme.
        user_provided = app.config.mkdocs_theme
        if user_provided is None:
            raise Exception("Did not get mkdocs_theme from conf.py")

        # Hook in the compatibility TemplateBridge.
        if config.template_bridge is None:
            config.template_bridge = "sphinx_mkdocs_theme.MkDocsTemplateBridge"
        else:
            raise Exception(
                f"Cannot be used with `template_bridge` set: {config.template_bridge}"
            )

        # No need to generate the index.
        app.config.html_use_index = False

    # https://www.sphinx-doc.org/en/3.x/extdev/appapi.html#event-builder-inited
    def handle_builder_inited(self, app):
        if app.config.html_theme != "mkdocs":
            # Do nothing if this is not used with the "mkdocs" theme.
            return

        # Operating Premise
        #     Accessing TemplateBridge as app.builder.templates and this is called
        #     *after* the template bridge has been initialized.
        app.builder.templates.actually_init(app)

        # Only generate the search page if requested.
        app.builder.search = app.builder.templates.mkdocs_theme["include_search_page"]

    # https://www.sphinx-doc.org/en/3.x/extdev/appapi.html#event-html-collect-pages
    def handle_collect_pages(self, app):
        if app.config.html_theme != "mkdocs":
            # Do nothing if this is not used with the "mkdocs" theme.
            return

        # TODO: handle self._theme.static_templates?
        # TODO: figure out lunr.js index support, to be transparent to mkdocs themes.
        # TODO: should yield mkdocs files!

        for path in []:
            yield (pagename, {"content": content}, _STATIC_FILE_INDICATOR)
