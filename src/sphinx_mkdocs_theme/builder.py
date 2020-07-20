"""A Sphinx Builder for building using an mkdocs theme.
"""

import os
import fnmatch
import logging
from pprint import pprint

from sphinx.builders.html import (
    __,
    progress_message,
    JavaScript,
    Stylesheet,
    Matcher,
    copy_asset,
    movefile,
)
from sphinx.builders.dirhtml import DirectoryHTMLBuilder
from mkdocs.contrib.search import SearchPlugin as MkDocsSearchPlugin

from .bridge import MkDocsTemplateBridge

logger = logging.getLogger(__name__)


class MkDocsBuilder(DirectoryHTMLBuilder):
    """Builder that uses mkdocs-like Jinja2 environment.
    """

    name = "mkdocs"
    searchindex_filename = os.path.join("search", "search_index.json")

    def get_builder_config(self, option, default):
        if (option, default) == ("use_index", "html"):
            return False  # disable the creation of genindex
        return super().get_builder_config(option, default)

    def create_template_bridge(self) -> None:
        self.templates = MkDocsTemplateBridge()

    def init_templates(self) -> None:
        super().init_templates()

    def init_js_files(self) -> None:
        # Drops hard-coded JS files and special handling of translations.js
        for filename, attrs in self.app.registry.js_files:
            self.add_js_file(filename, **attrs)

        for filename, attrs in self.get_builder_config("js_files", "html"):
            self.add_js_file(filename, **attrs)

    #
    # We don't create the _static directory!
    #
    def copy_static_files(self) -> None:
        try:
            with progress_message(__("copying static files... ")):
                # prepare context for templates
                context = self.globalcontext.copy()
                if self.indexer is not None:
                    context.update(self.indexer.context_for_searchtool())

                # Changed to skip unnecessary files.
                self.copy_theme_static_files(context)
                self.copy_html_static_files(context)
                self.copy_html_logo()
                self.copy_html_favicon()
        except OSError as err:
            logger.warning(__("cannot copy static file %r"), err)

    def copy_html_static_files(self, context) -> None:
        excluded = Matcher(self.config.exclude_patterns + ["**/.*"])
        for entry in self.config.html_static_path:
            copy_asset(
                os.path.join(self.confdir, entry),
                self.outdir,
                excluded,
                context=context,
                renderer=self.templates,
            )

    def add_js_file(self, filename: str, **kwargs: str) -> None:
        self.script_files.append(JavaScript(filename, **kwargs))

    def add_css_file(self, filename: str, **kwargs: str) -> None:
        self.css_files.append(Stylesheet(filename, **kwargs))  # type: ignore

    def copy_html_logo(self) -> None:
        if not self.config.html_logo:
            return

        copy_asset(os.path.join(self.confdir, self.config.html_logo), self.outdir)

    def copy_html_favicon(self) -> None:
        if not self.config.html_logo:
            return

        copy_asset(os.path.join(self.confdir, self.config.html_favicon), self.outdir)

    def finish(self) -> None:
        # no index generation!
        self.finish_tasks.add_task(self.gen_pages_from_extensions)
        self.finish_tasks.add_task(self.gen_additional_pages)
        self.finish_tasks.add_task(self.copy_image_files)
        self.finish_tasks.add_task(self.copy_download_files)
        self.finish_tasks.add_task(self.copy_static_files)
        self.finish_tasks.add_task(self.copy_extra_files)
        self.finish_tasks.add_task(self.write_buildinfo)
        self.finish_tasks.add_task(self.dump_inventory)

        translator = self.templates.translator
        if translator.indexer:
            self.finish_tasks.add_task(self.dump_search_files)

    def copy_theme_static_files(self, context) -> None:
        """Mimic mkdocs's theme asset copy behavior."""

        # Generic files, copied over from mkdoc's build.py
        exclude_patterns = [
            ".*",
            "*/.*",
            "*.py",
            "*.pyc",
            "*.html",
            "*readme*",
            "mkdocs_theme.yml",
        ]
        # Filenames for rendered documents
        exclude_patterns.extend(f"*{x}" for x in self.app.config.source_suffix.keys())

        def exclude_filter(name):
            for pattern in exclude_patterns:
                if fnmatch.fnmatch(name.lower(), pattern):
                    return False
            return True

        to_write = []
        environment = self.templates.environment
        for path in environment.list_templates(filter_func=exclude_filter):
            path = os.path.normpath(path)

            for location in self.templates.translator.theme.dirs:
                if os.path.isfile(os.path.join(location, path)):
                    to_write.append((location, path))
                    break

        for location, path in to_write:
            source = os.path.join(location, path)
            destination = os.path.join(self.outdir, path)
            renderer = self.templates

            # Ensure directory exists
            parent_dir = os.path.dirname(destination)

            # HACK: We only "render" template-y files.
            if "templates" not in path:
                copy_asset(source, os.path.dirname(destination))
                continue

            os.makedirs(parent_dir, exist_ok=True)
            with open(source, "rb") as fsrc:
                with open(destination, "wb", encoding="utf-8") as fdst:
                    source_text = fsrc.read()
                    result = renderer.render_string(source_text, context)
                    fdst.write(result)

    def dump_search_files(self) -> None:
        indexer = self.templates.translator.indexer

        # HACK: Yes, I felt dirty after writing this.
        plugin = MkDocsSearchPlugin()
        plugin.search_index = indexer
        plugin.config = indexer.config
        plugin.on_post_build(indexer.config)
