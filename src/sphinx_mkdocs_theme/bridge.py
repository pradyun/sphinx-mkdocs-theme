"""
"""

import os
import html
import traceback
from importlib.metadata import entry_points

from mkdocs.theme import Theme as MkDocsTheme
from sphinx.application import TemplateBridge
from sphinx.util import mtimes_of_files

from .translator import ContextTranslator

__all__ = ["MkDocsTemplateBridge", "EventHandler"]

_STATIC_FILE_INDICATOR = "<static>"


class MkDocsTemplateBridge(TemplateBridge):
    """A TemplateBridge that uses the mkdocs theme's Jinja2 environment for rendering.
    """

    def init(self, builder, theme, dirs=None):
        assert theme.name == "mkdocs"

    def actually_init(self, mkdocs_theme):
        self._theme = mkdocs_theme
        self._environment = mkdocs_theme.get_env()

        # TODO: Patch the "url" filter, to actually use sphinx's topath maybe?
        #       NOTE: seems like if we manage page.url correctly, it'll be fine.

    def render(self, template, context):
        try:
            return self._environment.get_template(template).render(context)
        except Exception:
            return (
                "Error occurred in MkDocsTemplateBridge.render()\n"
                f"<pre>{html.escape(traceback.format_exc())}</pre>"
            )

    def render_string(self, source, context):
        try:
            return self._environment.from_string(source).render(context)
        except Exception:
            return (
                "Error occurred in MkDocsTemplateBridge.render_string()\n"
                f"<pre>{html.escape(traceback.format_exc())}</pre>"
            )

    def newest_template_mtime(self) -> float:
        return max(mtimes_of_files(self._theme.dirs, ".html"))


class EventHandler:
    """Handles Sphinx events, modifying behaviours to mimic mkdocs' output.

    The methods are ordered in the order that they would have their first-calls.
    """

    def __init__(self):
        self._theme: MkDocsTheme = None
        self._translator = None

    # https://www.sphinx-doc.org/en/3.x/extdev/appapi.html#event-config-inited
    def handle_config_inited(self, app, config):
        if config.html_theme != "mkdocs":
            # Do nothing if this is not used with the "mkdocs" theme.
            return

        # Check that we got a theme.
        user_provided = app.config.mkdocs_theme
        if user_provided is None:
            raise Exception("Did not get mkdocs_theme from conf.py")

        # Check that the theme actually exists.
        theme_entry_points = entry_points()["mkdocs.themes"]
        available_themes = {ep.name: ep.value for ep in theme_entry_points}
        if user_provided not in available_themes:
            raise Exception(
                "Could not find mkdocs theme named: {}".format(user_provided)
            )

        # Hook in the compatibility TemplateBridge.
        if config.template_bridge is None:
            config.template_bridge = "sphinx_mkdocs_theme.MkDocsTemplateBridge"
        else:
            raise Exception(
                f"Cannot be used with `template_bridge` set: {config.template_bridge}"
            )

        self._theme = MkDocsTheme(app.config.mkdocs_theme)
        self._translator = ContextTranslator(app, self._theme)

    # https://www.sphinx-doc.org/en/3.x/extdev/appapi.html#event-builder-inited
    def handle_builder_inited(self, app):
        if not self._theme:
            return

        # Operating Premise
        #     Accessing TemplateBridge as app.builder.templates and this is called
        #     *after* the template bridge has been initialized.
        app.builder.templates.actually_init(self._theme)

        # No need to generate
        app.config.html_use_index = False
        app.builder.search = False
        # app.config.html_use_index = False

    # https://www.sphinx-doc.org/en/3.x/extdev/appapi.html#event-html-collect-pages
    def handle_collect_pages(self, app):
        if not self._theme:
            return

        # TODO: handle self._theme.static_templates?
        # TODO: figure out lunr.js index support, to be transparent to mkdocs themes.
        # TODO: should yield mkdocs files!

        for path in []:
            yield (pagename, {"content": content}, _STATIC_FILE_INDICATOR)


    # https://www.sphinx-doc.org/en/3.x/extdev/appapi.html#event-html-page-context
    def handle_page_context(self, app, pagename, templatename, context, doctree):
        if not self._theme:
            return

        # We have to return the same object, so we use a copy for the
        # translation, and replace the original inline.
        mkdocs_context = self._translator.translate(templatename, context.copy())
        context.clear()
        context.update(mkdocs_context)

        return "main.html"
