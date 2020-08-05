"""Mimic mkdocs' model for objects passed into the context.
"""

#
# Permanently borrowed from the mkdocs' `nav.py`
#
class Navigation:
    def __init__(self, items, pages, homepage):
        self.items = items  # Nested List with full navigation of Sections, Pages, and Links.
        self.pages = pages  # Flat List of subset of Pages in nav, in order.
        self.homepage = homepage

    def __repr__(self):
        return "Navigation: " + (
            '\n'.join([item._indent_print() for item in self]) or "<nothing>"
        )

    def __iter__(self):
        return iter(self.items)

    def __len__(self):
        return len(self.items)
