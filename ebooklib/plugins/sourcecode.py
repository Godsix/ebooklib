# pylint: disable=missing-module-docstring, missing-class-docstring, no-name-in-module
# This file is part of EbookLib.
# Copyright (c) 2013 Aleksandar Erkalovic <aerkalov@gmail.com>
#
# EbookLib is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# EbookLib is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with EbookLib.  If not, see <http://www.gnu.org/licenses/>.

from lxml import etree, html

from ..utils import parse_html
from .base import BasePlugin


class SourceHighlighter(BasePlugin):
    def __init__(self):
        pass

    def html_before_write(self, book, chapter):
        # Pygments is an optional dependency of this plugin, so import it lazily.
        try:
            from pygments import highlight
            from pygments.formatters import HtmlFormatter
            from pygments.lexers import CssLexer, PythonLexer
        except ImportError as exc:
            raise ImportError(
                "SourceHighlighter requires the optional 'pygments' package."
            ) from exc

        try:
            tree = parse_html(chapter.content)
        except Exception:  # pylint: disable=broad-exception-caught
            return

        had_source = False

        body = tree.find("body")
        if body is not None and len(body) != 0:
            # check for embeded source
            for source in body.xpath('//pre[contains(@class,"source-")]'):
                css_class = source.get("class", "")

                source_text = (source.text or "") + "".join([html.tostring(child) for child in source.iterchildren()])

                _text = None

                if "source-python" in css_class:
                    # _text =  highlight(source_text, PythonLexer(), HtmlFormatter(linenos="inline"))
                    _text = highlight(source_text, PythonLexer(), HtmlFormatter())

                if "source-css" in css_class:
                    _text = highlight(source_text, CssLexer(), HtmlFormatter())

                if _text is None:
                    # unknown source language; leave the element untouched
                    continue

                _parent = source.getparent()
                if _parent is not None:
                    _parent.replace(source, etree.XML(_text))
                    had_source = True

        if had_source:
            chapter.add_link(href="style/code.css", rel="stylesheet", type="text/css")
            chapter.content = etree.tostring(tree, pretty_print=True, encoding="utf-8")
