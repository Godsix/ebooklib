# pylint: disable=missing-module-docstring, missing-class-docstring, c-extension-no-member
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

from urllib.parse import urljoin, urlparse

from lxml import etree

from ..utils import get_qname, parse_xhtml_to_html, xhtml_tostring
from .base import BasePlugin


class BooktypeLinks(BasePlugin):
    NAME = "Booktype Links"

    def __init__(self, booktype_book):
        self.booktype_book = booktype_book

    def html_before_write(self, book, chapter):
        try:
            tree = parse_xhtml_to_html(chapter.content)
        except Exception:  # pylint: disable=broad-exception-caught
            return

        body = tree.find("body")

        if body is not None and len(body) != 0:
            # should also be aware to handle
            # ../chapter/
            # ../chapter/#reference
            # ../chapter#reference

            for child in body.xpath("//a"):
                # This is just temporary for the footnotes
                href = child.get("href", "")
                if href.find("InsertNoteID") != -1:
                    i = href.find("#")
                    child.set("href", href[i:])
                    continue

                url = urlparse(href)

                # Let us care only for internal links at the moment
                if url.scheme == "":
                    if url.path != "":
                        child.set("href", f"{url.path}.xhtml")

                    if url.fragment != "":
                        child.set("href", urljoin(child.get("href", ""), f"#{url.fragment}"))

                    name = child.get("name")
                    if name is not None:
                        child.set("id", name)
                        etree.strip_attributes(child, "name")

        chapter.content = xhtml_tostring(tree)


class BooktypeFootnotes(BasePlugin):
    NAME = "Booktype Footnotes"

    def __init__(self, booktype_book):
        self.booktype_book = booktype_book

    def html_before_write(self, book, chapter):
        try:
            tree = parse_xhtml_to_html(chapter.content)
        except Exception:  # pylint: disable=broad-exception-caught
            return

        body = tree.find("body")

        if body is not None and len(body) != 0:
            # <span id="InsertNoteID_1_marker1" class="InsertNoteMarker">
            #   <sup><a href="#InsertNoteID_1">1</a></sup>
            # <span>

            # <ol id="InsertNote_NoteList">
            #   <li id="InsertNoteID_1">prvi footnote
            #     <span id="InsertNoteID_1_LinkBacks">
            #       <sup><a href="#InsertNoteID_1_marker1">^</a></sup>
            #     </span>
            #   </li>
            # </ol>

            # <a epub:type="noteref" href="#n1">1</a></p>
            # <aside epub:type="footnote" id="n1"><p>These have been corrected in this EPUB3 edition.</p></aside>
            for footnote in body.xpath('//span[@class="InsertNoteMarker"]'):
                footnote_id = footnote.get("id", "")[:-8]
                a = footnote[0][0]

                footnote_text = body.xpath(f'//li[@id="{footnote_id}"]')[0]

                a.attrib[get_qname('epub', 'type')] = "noteref"
                ftn = etree.SubElement(body, "aside", {"id": footnote_id})
                ftn.attrib[get_qname('epub', 'type')] = "footnote"
                ftn_p = etree.SubElement(ftn, "p")
                ftn_p.text = footnote_text.text

            old_footnote = body.xpath('//ol[@id="InsertNote_NoteList"]')
            if len(old_footnote) > 0:
                body.remove(old_footnote[0])

        chapter.content = xhtml_tostring(tree)
