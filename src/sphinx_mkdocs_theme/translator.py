"""Translate Sphinx's Jinja2 context into MkDocs Jinja2 context.

This single file represents most of the hard-fought knowledge for this project.
"""

import pprint
from types import SimpleNamespace

import bs4
import mkdocs
from mkdocs.contrib.search import SearchIndex

import sphinx
import sphinx_mkdocs_theme as this_project


# from mkdocs.structure.files import File, Files
# from mkdocs.structure.nav import Navigation
# from mkdocs.structure.pages import Page
# from mkdocs.structure.toc import TableOfContents
# from mkdocs.theme import Theme

__all__ = ["ContextTranslator"]

#
# HTML Processing!
#
Link = Section = Page = SimpleNamespace


class Nav(SimpleNamespace):

    def __init__(self, items, **kwargs):
        self._items = items
        super().__init__(**kwargs)

    def __iter__(self):
        return iter(self._items)


def _handle_ul_in_toctree(ul_element, parent=None):
    retval = []
    for li_element in ul_element.find_all("li", recursive=False):
        # Extract the basic information
        title = li_element.a.text
        url = li_element.a.attrs["href"]
        active = "current" in li_element.attrs.get("class", [])

        # Does it have a "ul" tag in it?
        if li_element.ul:
            children = _handle_ul_in_toctree(li_element.ul)
            cls = Section
        else:
            children = None
            cls = Link

        item = cls(
            title=title, parent=parent, active=active, children=children, url=url,
        )
        retval.append(item)

    return retval


def convert_toctree(html):
    soup = bs4.BeautifulSoup(html, features="html.parser")

    # TODO: rewrite this?

    retval = []
    for element in soup.children:
        # Nothing to do with strings here.
        if isinstance(element, str):
            continue
        if element.name != "ul":
            print(element)
            continue
        retval.extend(_handle_ul_in_toctree(element))
    return retval


def flatten_toctree(toctree):
    retval = []
    to_process = toctree[:]
    while to_process:
        current = to_process.pop()
        retval.append(current)

        if current.children:
            to_process.extend(current.children)
    return retval

#
# The main attraction!
#
class ContextTranslator:
    def __init__(self, app, theme):
        self.app = app
        self.theme = theme

        self.sphinx_context = None
        self.template_name = None

        self.indexer = None
        if app.builder.search:
            self.indexer = SearchIndex(
                prebuild_index="python", lang=app.config.language or "en"
            )

    def translate(self, sphinx_context, template_name):
        self.sphinx_context = sphinx_context
        if template_name == "page.html":
            self.template_name = "main.html"
        else:
            self.template_name = template_name

        config = self.get_config()
        nav = self.get_site_navigation()
        all_pages = self.get_all_pages()
        page = self.get_page_details()

        if self.indexer:
            self.indexer.add_entry_from_context(page)

        base_url = "."  # HACK: somehow, this works?
        extra_css = sphinx_context["css_files"]
        extra_javascript = sphinx_context["script_files"]

        # Based on reading `mkdocs.commands.build`
        mkdocs_context = {
            "config": config,
            # navigation
            "nav": nav,
            "pages": all_pages,
            # this page
            "page": page,
            "base_url": base_url,
            # assets
            "extra_css": extra_css,
            "extra_javascript": extra_javascript,
            # meta
            "mkdocs_version": (
                f"{mkdocs.__version__} and Sphinx {sphinx.__version__}, "
                f"using sphinx-mkdocs-theme {this_project.__version__}"
            ),
            "build_date_utc": sphinx_context["last_updated"],
            # Because, Sphinx makes assumptions internally
            "encoding": sphinx_context["encoding"],
        }
        return mkdocs_context, self.template_name

    # https://mkdocs.readthedocs.io/en/latest/user-guide/custom-themes/#config
    def get_config(self):
        theme = self._convert_sphinx_theme_config()
        extra = theme.pop("extra", {})
        plugins = theme.pop("plugins", [])
        google_analytics = theme.pop("google_analytics", None)

        if self.indexer:
            plugins.append("search")

        return {
            "theme": theme,
            "extra": extra,
            "plugins": plugins,
            "copyright": "Copyright &copy; " + self.sphinx_context["copyright"],
            "site_name": self.sphinx_context["docstitle"],
            "site_author": self.app.config.author,
            # TODO: figure out the rest!
            "site_url": None,
            "site_description": None,
            "repo_url": None,
            "repo_name": None,
            # no need to do this IMO
            "google_analytics": google_analytics,
        }

    def _convert_sphinx_theme_config(self):
        """Convert Sphinx's theme_* variables into mkdocs' `theme` object."""
        theme_config = {}

        for key in self.theme:
            theme_config[key] = self.theme[key]

        # Load from html_theme_config
        prefix = "theme_"
        for key, value in self.sphinx_context.items():
            if not key.startswith(prefix):
                continue

            name = key[len(prefix) :]
            theme_config[name] = value

        if self.sphinx_context["language"]:
            theme_config["language"] = self.sphinx_context["language"]

        return theme_config

    # https://mkdocs.readthedocs.io/en/latest/user-guide/custom-themes/#nav
    def get_site_navigation(self):
        toctree = self.sphinx_context["toctree"]

        nav_html = toctree(
            maxdepth=2, includehidden=False, collapse=False, titles_only=True,
        )
        items = convert_toctree(nav_html)
        pages = flatten_toctree(items)

        homepage = Page(
            title="Home",
            content="",  # this cannot be filled in Sphinx.
            meta=None,  # this cannot be filled in Sphinx.
            is_homepage=True,
            url="",
            # TODO: figure these out!
            toc=None,
            abs_url=None,
            canonical_url=None,
            edit_url=None,
            previous_page=None,
            next_page=None,
            parent=None,
            # Guaranteed constants
            children=None,
            active=True,
            is_section=False,
            is_page=True,
            is_link=False,
        )

        return Nav(items, homepage=homepage, pages=pages)

    # https://mkdocs.readthedocs.io/en/latest/user-guide/custom-themes/#pages
    def get_all_pages(self):
        toctree = self.sphinx_context["toctree"]

        all_pages_html = toctree(
            maxdepth=-1, includehidden=False, collapse=False, titles_only=True,
        )
        items = convert_toctree(all_pages_html)
        return flatten_toctree(items)

    # https://mkdocs.readthedocs.io/en/latest/user-guide/custom-themes/#page
    def get_page_details(self):
        # This is used by the mkdocs's provided "url" filter, so this is trying
        # to make things "just work".
        pagename = self.sphinx_context["pagename"]
        master_doc = self.sphinx_context["master_doc"]
        if pagename.endswith("index"):
            url = pagename[:-6]
        else:
            url = pagename + "/"

        toc = self.sphinx_context["toc"]

        page = Page(
            title=self.sphinx_context.get("title", None),
            content=self.sphinx_context.get("body", None),
            meta=self.sphinx_context.get("meta", None),
            url=url,
            is_homepage=pagename == master_doc,
            # TODO: figure these out!
            toc=[],
            abs_url=None,
            canonical_url=None,
            edit_url=None,
            previous_page=None,
            next_page=None,
            parent=None,
            # Guaranteed constants
            children=None,
            active=True,
            is_section=False,
            is_page=True,
            is_link=False,
        )
        return page
