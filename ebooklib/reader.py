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

"""EpubReader - loads an EPUB file into an EpubBook."""

import os
import posixpath as zip_path
import warnings
from pathlib import Path
from typing import IO, Any
from zipfile import ZIP_DEFLATED, BadZipfile, LargeZipFile, ZipFile

from lxml.etree import QName  # pylint: disable=E0611

from .book import EpubBook
from .consts import CONTAINER_PATH, NAMESPACES
from .exceptions import EpubException
from .items import EpubHtml, EpubNav
from .ocf import OCFContainer
from .opf import OPF
from .pytype import XmlElement
from .toc import Link, Section
from .utils import Directory, join_path, parse_xhtml, parse_xml


class EpubReader:
    """EpubReader - loads an EPUB file into an EpubBook."""
    DEFAULT_OPTIONS: dict[str, Any] = {"ignore_ncx": True}

    def __init__(self, epub_file_name, options: dict[str, Any] | None = None) -> None:
        self.file_name = epub_file_name
        self.book = EpubBook()
        self.io: ZipFile | Directory | None = None
        self.opf: OPF | None = None

        self.opf_path = ""
        self.opf_dir = ""

        self.options = dict(self.DEFAULT_OPTIONS)
        if options:
            self.options.update(options)

        self._check_deprecated()

    def _check_deprecated(self) -> None:
        if self.options.get("ignore_ncx") is None:
            _w = ("In the future version we will turn default option ignore_ncx to True.")
            warnings.warn(_w, stacklevel=2)

    def process(self) -> None:
        """Load EPUB file into EpubBook object."""
        # should cache this html parsing so we don't do it for every plugin
        for plg in self.options.get("plugins", []):
            if hasattr(plg, "after_read"):
                plg.after_read(self.book)

        for item in self.book.get_items():
            if isinstance(item, EpubHtml):
                for plg in self.options.get("plugins", []):
                    if hasattr(plg, "html_after_read"):
                        plg.html_after_read(self.book, item)

    def load(self) -> EpubBook:
        """Load EPUB file into EpubBook object."""
        self._load()

        return self.book

    def _read(self, *name: str) -> bytes:
        # Raises KeyError for missing items in an archive, OSError for directory sources
        if self.io is None:
            raise EpubException(-1, "EPUB file is not opened")
        return self.io.read(join_path(*name))

    def _load_container(self) -> None:
        content = self._read(CONTAINER_PATH)
        self.opf_path = OCFContainer.get_full_path(content)
        opf_dir, opf_name = zip_path.split(self.opf_path)
        self.book.opf.file_name = opf_name
        self.book.package_dir = self.opf_dir = opf_dir

    def _parse_ncx(self, data: bytes) -> None:
        tree = parse_xml(data)
        root = tree.getroot()

        nav_map = root.find(QName(root, "navMap"))

        nav_label = QName(root, "navLabel")
        nav_content = QName(root, "content")
        nav_point = QName(root, "navPoint")

        def _get_children(elements, n, nid):
            label, content = "", ""
            children = []

            for child in elements:
                if child.tag == nav_label:
                    label = child[0].text
                if child.tag == nav_content:
                    content = child.get("src", "")
                if child.tag == nav_point:
                    children.append(_get_children(child, n + 1, child.get("id", "")))

            if children:
                if n == 0:
                    return children

                return (Section(label, href=content), children)
            return Link(content, label, nid)

        self.book.toc = _get_children(nav_map, 0, "")

    def _parse_nav(self, data: str | bytes, base_path: str, navtype: str = "toc") -> None:
        tree = parse_xhtml(data)
        nav_tag = QName(NAMESPACES["XHTML"], "nav")
        epub_type = QName(NAMESPACES["EPUB"], "type")
        nav_type = "toc" if navtype == "toc" else "page-list"
        nav = tree.find(f".//{nav_tag}[@{epub_type}='{nav_type}']")
        if nav is None:
            return

        ol_tag = QName(NAMESPACES["XHTML"], "ol")
        li_tag = QName(NAMESPACES["XHTML"], "li")
        a_tag = QName(NAMESPACES["XHTML"], "a")

        def parse_list(element: XmlElement):
            items = []

            for child in element.findall(li_tag):
                sub_element = child.find(ol_tag)
                href = ""
                if ((a_node := child.find(a_tag)) is not None
                        and (href := a_node.get("href"))):
                    href = join_path(base_path, href)

                if sub_element is not None:
                    title = child[0].text_content()
                    children = parse_list(sub_element)
                    items.append((Section(title, href=href), children))
                elif href:
                    title = a_node.text_content()
                    items.append(Link(href=href, title=title))

            return items

        if navtype == "toc":
            self.book.toc = parse_list(nav.find(ol_tag))
            return
        # generate the pages list if there is one
        self.book.pages = parse_list(nav.find(ol_tag))

        # generate the per-file pages lists
        # because of the order of parsing the files, this can't be done
        # when building the EpubHtml objects
        items = {x.file_name: x for x in self.book.items if isinstance(x, EpubHtml)}
        for page in self.book.pages:
            if (pos := page.href.find("#")) < 0:
                filename = page.href
            else:
                filename = page.href[:pos]
            if filename in items:
                items[filename].pages.append(page)

    def _load_opf_file(self) -> None:
        try:
            s = self._read(self.opf_path)
        except KeyError:
            raise EpubException(-1, "Can not find container file") from None

        self.opf = OPF(zip_path.basename(self.opf_path))
        self.opf.set_content(s, self.io, self.book, **self.options)

        toc = self.opf.spine.get("toc", "")
        nav_item = next((item for item in self.book.items if isinstance(item, EpubNav)), None)
        if toc and (not self.options.get("ignore_ncx") or not nav_item):
            # should read ncx or nav file
            ncx_item = self.book.get_item_with_id(toc)
            if ncx_item is None:
                raise EpubException(-1, "Can not find ncx file.")
            try:
                ncx = self._read(self.opf_dir, ncx_item.get_name())
            except KeyError:
                raise EpubException(-1, "Can not find ncx file.") from None
            self._parse_ncx(ncx)
        # read nav file if found
        if nav_item:
            nav_dir = zip_path.dirname(nav_item.file_name)
            if self.options.get("ignore_ncx") or not self.book.toc:
                self._parse_nav(nav_item.content, nav_dir, navtype="toc")
            self._parse_nav(nav_item.content, nav_dir, navtype="pages")

    def _io(self, path: Path | IO[bytes]) -> IO[bytes]:
        if isinstance(path, Path):
            if path.is_dir():
                return Directory(path)
            if not path.is_file():
                raise FileNotFoundError(f"{path} is not a file or directory.")
        return ZipFile(path, "r", compression=ZIP_DEFLATED, allowZip64=True)

    def _load(self) -> None:
        if isinstance(self.file_name, (str, os.PathLike)):
            source = Path(self.file_name)
        elif isinstance(self.file_name, bytes):
            source = Path(os.fsdecode(self.file_name))
        else:
            source = self.file_name
        if self.io is None:
            try:
                with self._io(source) as zf:
                    self.io = zf
                    # 1st check metadata
                    self._load_container()
                    self._load_opf_file()
                self.io = None
            except BadZipfile:
                raise EpubException(0, "Bad Zip file") from None
            except LargeZipFile:
                raise EpubException(1, "Large Zip file") from None


def read_epub(name, options: dict[str, Any] | None = None) -> EpubBook:
    """
    Creates new instance of EpubBook with the content defined in the input file.

    >>> book = ebooklib.read_epub('book.epub')

    :Args:
      - name: full path to the input file
      - options: extra options as dictionary (optional)

    :Returns:
      Instance of EpubBook.
    """
    reader = EpubReader(name, options)

    book = reader.load()
    reader.process()

    return book
