import xml.etree.ElementTree as etree

import markdown
from markdown.extensions import Extension
from markdown.treeprocessors import Treeprocessor
from markupsafe import Markup

_SAFE_URL_PREFIXES = ("http://", "https://", "mailto:", "/", "#")


class _SafeUrls(Treeprocessor):
    def run(self, root: etree.Element) -> None:
        for el in root.iter():
            for attr in ("href", "src"):
                url = el.get(attr)
                if url is not None and not url.strip().lower().startswith(_SAFE_URL_PREFIXES):
                    del el.attrib[attr]
            if el.tag == "a" and el.get("href", "").startswith(("http://", "https://")):
                el.set("target", "_blank")
                el.set("rel", "noopener noreferrer")


class _SafeMarkdown(Extension):
    """Treat raw HTML in model output as text and drop javascript:/data: URLs."""

    def extendMarkdown(self, md: markdown.Markdown) -> None:
        md.preprocessors.deregister("html_block")
        md.inlinePatterns.deregister("html")
        md.treeprocessors.register(_SafeUrls(md), "safe_urls", 0)


def render_markdown(text: str) -> Markup:
    md = markdown.Markdown(extensions=["fenced_code", "tables", "sane_lists", _SafeMarkdown()])
    return Markup(md.convert(text))
