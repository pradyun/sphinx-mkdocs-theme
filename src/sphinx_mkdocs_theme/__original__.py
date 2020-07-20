"""Enable Sphinx documentation to use MkDocs themes.
"""

__version__ = "0.0.1.dev0"

import os
import functools
from importlib.metadata import entry_points

from mkdocs import __version__ as mkdocs_version
from mkdocs.theme import Theme as MkDocsTheme

from sphinx import __version__ as sphinx_version
from sphinx.application import TemplateBridge

import bs4

# --------------------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------------------


# Permanently borrowed from:
# https://github.com/sphinx-doc/sphinx/blob/e4c3e24e85a6e32e3f/sphinx/util/osutil.py#L93
def mtimes_of_files(dirnames, suffix):
    for dirname in dirnames:
        for root, dirs, files in os.walk(dirname):
            for sfile in files:
                if sfile.endswith(suffix):
                    try:
                        yield os.path.getmtime(os.path.join(root, sfile))
                    except OSError:
                        pass


class DumbNamespace:
    def __init__(self, adict):
        self.__dict__.update(adict)

    @classmethod
    def section(cls, title, children, parent, active):
        return cls(
            {
                "title": title,
                "parent": parent,
                "active": active,
                "children": children,
                "is_section": True,
                "is_page": False,
                "is_link": False,
            }
        )

    @classmethod
    def link(cls, title, url, parent, active):
        return cls(
            {
                "title": title,
                "url": url,
                "parent": parent,
                "active": active,
                "children": None,
                "is_section": False,
                "is_page": False,
                "is_link": True,
            }
        )


# --------------------------------------------------------------------------------------
# Things that interact with Sphinx internals
# --------------------------------------------------------------------------------------
class MkDocsTemplateBridge(TemplateBridge):
    def init(self, builder, theme, dirs=None):
        assert theme.name == "mkdocs"

    def actually_init(self, mkdocs_theme):
        self.theme = mkdocs_theme
        self.environment = mkdocs_theme.get_env()

        # import pdb; pdb.set_trace()

        # TODO: Patch the "url" filter, to actually use sphinx's topath maybe?

    def render(self, template, context):
        try:
            return self.environment.get_template(template).render(context)
        except Exception as e:
            return "<error occurred in render>" + str(e)

    def render_string(self, source, context):
        try:
            return self.environment.from_string(source).render(context)
        except Exception as e:
            return "<error occurred in render_string>" + str(e)

    def newest_template_mtime(self) -> float:
        return max(mtimes_of_files(self.theme.dirs, ".html"))


class Handler:
    """Handles Sphinx events, to hook in at appropriate locations.

    The methods are ordered in the order that they would have their first-calls.
    """

    def __init__(self):
        self.theme = None

    # https://www.sphinx-doc.org/en/3.x/extdev/appapi.html#event-config-inited
    def handle_config_inited(self, app, config):
        if config.html_theme != "mkdocs":
            return

        if config.template_bridge != "sphinx_mkdocs_theme.MkDocsTemplateBridge":
            raise Exception("Cannot be used without correct template_bridge")

        user_provided = app.config.mkdocs_theme
        if user_provided is None:
            raise Exception("Did not get mkdocs_theme from conf.py")

        theme_entry_points = entry_points()["mkdocs.themes"]
        available_themes = {ep.name: ep.value for ep in theme_entry_points}
        if user_provided not in available_themes:
            raise Exception(
                "Could not find mkdocs theme named: {}".format(user_provided)
            )

        self.theme = MkDocsTheme(app.config.mkdocs_theme)

    # https://www.sphinx-doc.org/en/3.x/extdev/appapi.html#event-builder-inited
    def handle_builder_inited(self, app):
        if not self.theme:
            return

        # This is called *after* the template bridge etc have been initialized.
        # We need to update the paths used by the Jinja2 builder.
        app.builder.templates.actually_init(self.theme)

    # https://www.sphinx-doc.org/en/3.x/extdev/appapi.html#event-html-collect-pages
    def handle_collect_pages(self, app):
        if not self.theme:
            return []

        # TODO: handle self.theme.static_templates?
        # TODO: figure out lunr.js index support, to be transparent to mkdocs themes.
        # TODO: should yield mkdocs files!

        return []

    # https://www.sphinx-doc.org/en/3.x/extdev/appapi.html#event-html-page-context
    def handle_page_context(self, app, pagename, templatename, context, doctree):
        if not self.theme:
            return

        # TODO: store global "nav" and "pages" from the first page, for use w/
        # genindex and search.

        # We have to return the same object, so we save a copy for potentially
        # using later, and clear the context that would be used to render the
        # template.
        original_context = context.copy()
        context.clear()

        if templatename == "genindex.html":
            original_context["title"] = "Index"
            original_context["toc"] = []
            original_context["meta"] = {}
            # TODO: actually create some usable HTML
            original_context["body"] = str(original_context["genindexentries"])
        if templatename == "search.html":
            original_context["title"] = "Search"
            original_context["toc"] = []
            original_context["meta"] = {}
            # TODO: actually create some usable HTML
            original_context["body"] = ""

        mkdocs_context = self.get_mkdocs_context(app, original_context)
        context.update(mkdocs_context)

        return "main.html"

    # This is the real magic happens -- where we "almost" mimic the theme
    # context for mkdocs themes, from the information available from sphinx.
    def get_theme_config(self, app, context):
        theme_config = {}
        extra_config = {}

        for key in self.theme:
            theme_config[key] = self.theme[key]

        # Load from html_theme_config
        prefix = "theme_"
        for key, value in context.items():
            if not key.startswith(prefix):
                continue

            name = key[len(prefix) :]
            if name == "extra":
                extra_config = value
            else:
                theme_config[name] = value

        if context["language"]:
            theme_config["language"] = context["language"]

        return theme_config, extra_config

    def get_page_details(self, context):
        # print(context)
        page_toc = self.process_page_toc(context["toc"])

        # This is used by the mkdocs's provided "url" filter, so this is trying
        # to make things "just work".
        if context["pagename"].endswith("index"):
            url = context["pagename"][:-6]
        else:
            url = context["pagename"] + ".html"

        return DumbNamespace(
            {
                "title": context["title"],
                "content": context["body"],
                "meta": context["meta"],
                "toc": page_toc,
                "url": url,
                "abs_url": None,  # TODO: figure this out
                "canonical_url": None,  # TODO: figure this out
                "edit_url": None,  # TODO: figure this out
                "is_homepage": None,  # TODO: figure this out
                "previous_page": None,  # TODO: figure this out
                "next_page": None,  # TODO: figure this out
                "parent": None,  # TODO: figure this out
                # Guaranteed constants
                "children": None,
                "active": True,
                "is_section": False,
                "is_page": True,
                "is_link": False,
            }
        )

    def get_navigation_trees(self, context):
        toctree = context["toctree"]
        page_toctree = functools.partial(toctree, collapse=False, titles_only=True)

        global_toc_html = page_toctree(maxdepth=2, includehidden=False)
        nav = self.process_global_toc(global_toc_html)

        all_pages_toc_html = page_toctree(maxdepth=-1, includehidden=True)
        pages = self.process_global_toc(all_pages_toc_html)

        return nav, pages

    def get_mkdocs_context(self, app, context):
        theme_config, extra_config = self.get_theme_config(app, context)
        nav, pages = self.get_navigation_trees(context)
        page = self.get_page_details(context)

        config = {
            "site_name": context["docstitle"],
            "site_url": None,  # TODO: figure this out
            "site_author": app.config.author,
            "site_description": None,  # TODO: figure this out
            "extra_javascript": [],  # TODO: figure this out
            "extra_css": [],  # TODO: figure this out
            "repo_url": None,  # TODO: figure this out
            "repo_name": None,  # TODO: figure this out
            "copyright": context["copyright"],
            "theme": theme_config,
            "extra": extra_config,
            # no need to do this IMO
            "google_analytics": None,
        }

        return {
            "base_url": ".",  # TODO: figure out what to do about this
            "build_date_utc": context["last_updated"],
            "encoding": context["encoding"],
            "mkdocs_version": (
                f"{mkdocs_version} and Sphinx {sphinx_version}, "
                f"using sphinx-mkdocs-theme {__version__}"
            ),
            "config": config,
            "page": page,
            "nav": nav,
            "pages": pages,
        }

    # TODO: revisit all of this stuff.
    def process_global_toc(self, html):
        tree = self.convert_toctree(html)

        class Nav:
            def __init__(self, li):
                self.li = li
                self.homepage = None

            def __iter__(self):
                return iter(self.li)

        return Nav(tree)

    def process_page_toc(self, html):
        return self.convert_toctree(html or "")

    @functools.lru_cache
    def convert_toctree(self, toc_html):
        soup = bs4.BeautifulSoup(toc_html, features="html.parser")

        def handle_ul(element, parent=None):
            retval = []
            for item in element.find_all("li", recursive=False):
                title = item.a.text
                active = "class" in item.attrs and "current" in item.attrs["class"]

                if item.ul:
                    children = handle_ul(item.ul)
                    retval.append(
                        DumbNamespace.section(title, children, parent, active)
                    )
                else:
                    url = item.a.attrs["href"]
                    retval.append(DumbNamespace.link(title, url, parent, active))

            return retval

        data = []
        for element in soup.children:
            # Nothing to do with strings here.
            if isinstance(element, str):
                continue
            if element.name != "ul":
                print(element)
                continue
            data.append(handle_ul(element))
        return data


# Entry point for the sphinx extension
def setup(app):
    app.add_html_theme("mkdocs", os.path.abspath(os.path.dirname(__file__)))
    app.add_config_value("mkdocs_theme", default=None, rebuild="html")

    handler = Handler()
    app.connect("config-inited", handler.handle_config_inited)
    app.connect("builder-inited", handler.handle_builder_inited)
    app.connect("html-collect-pages", handler.handle_collect_pages)
    app.connect("html-page-context", handler.handle_page_context)

    return {
        "version": __version__,
        # A little parallelization never hurt anyone right?
        "parallel_read_safe": True,
        "parallel_write_safe": True,
    }
