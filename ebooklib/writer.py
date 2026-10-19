# pylint: disable=missing-module-docstring, missing-class-docstring, missing-function-docstring, c-extension-no-member
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

"""EpubWriter - serialises an EpubBook to an EPUB file."""

import logging
import os
import os.path
import posixpath as zip_path
from datetime import datetime, timezone
from pathlib import Path
from typing import IO, Any, Protocol, TypeAlias
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile, ZipInfo

from lxml import etree
from lxml.etree import QName  # pylint: disable=E0611
from .book import EpubBook
from .consts import (
    COMPRESSED,
    CONTAINER_PATH,
    CONTAINER_XML,
    ITEM_DOCUMENT,
    NAMESPACES,
    VERSION,
)
from .items import EpubCover, EpubHtml, EpubItem, EpubNav, EpubNcx
from .toc import Link, Section
from .utils import get_pages_for_items, get_qname, parse_xml, xml_tostring

logger = logging.getLogger(__name__)


class _WritableFile(Protocol):
    """Minimal structural interface required by zipfile.ZipFile for writing."""

    def write(self, data: bytes, /) -> object: ...

    def seek(self, offset: int, whence: int = ..., /) -> object: ...

    def tell(self) -> int: ...


# Anything accepted by zipfile.ZipFile: a path or a writable binary file-like object.
EpubTarget: TypeAlias = str | os.PathLike[str] | _WritableFile


class EpubWriter:
    DEFAULT_OPTIONS: dict[str, Any] = {
        "epub2_guide": True,
        "epub3_landmark": True,
        "epub3_pages": True,
        "landmark_title": "Guide",
        "pages_title": "Pages",
        "spine_direction": True,
        "package_direction": False,
        "play_order": {"enabled": False, "start_from": 1},
        "raise_exceptions": True,
        "compresslevel": 6,
    }

    @classmethod
    def get_default_options(cls) -> dict[str, Any]:
        default = dict(cls.DEFAULT_OPTIONS)
        default["mtime"] = datetime.now(timezone.utc)
        return default

    @classmethod
    def datetime_to_zipinfo_datetime(cls, dt: datetime) -> tuple[int, int, int, int, int, int]:
        """
        Converts a datetime object to a tuple format compatible with zipfile.ZipInfo.

        :Args:
          - dt: datetime.datetime object

        :Returns:
          Tuple of (year, month, day, hour, minute, second) for use in ZipInfo
        """
        # ZIP timestamps carry no timezone information and are conventionally
        # interpreted as local time, so convert aware datetimes to local time first.
        if dt.tzinfo is not None:
            dt = dt.astimezone()
        return (dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second)

    def zipinfo(self, name: str) -> ZipInfo:
        info = ZipInfo(name, self.datetime_to_zipinfo_datetime(self.options["mtime"]))
        suffix = Path(name).suffix.lower()
        if suffix in COMPRESSED:
            info.compress_type = ZIP_STORED
        else:
            info.compress_type = ZIP_DEFLATED
            compresslevel = self.options["compresslevel"]
            if hasattr(info, 'compress_level'):
                info.compress_level = compresslevel
            else:
                # Python 3.10-3.12
                info._compresslevel = compresslevel  # pylint: disable=protected-access
        if info.is_dir():  # pragma: no cover
            info.external_attr = 0o40775 << 16  # drwxrwxr-x
            info.external_attr |= 0x10  # MS-DOS directory flag
        else:
            info.external_attr = 0o600 << 16  # ?rw-------
        return info

    def __init__(self, name: EpubTarget, book: EpubBook, options: dict[str, Any] | None = None) -> None:
        self.file_name: EpubTarget | IO[bytes] = name
        self.book = book

        self.options = self.get_default_options()
        if options:
            self.options.update(options)

        self._init_play_order()

    def _init_play_order(self) -> None:
        self._play_order = {"enabled": False, "start_from": 1}

        try:
            self._play_order["enabled"] = self.options["play_order"]["enabled"]
            self._play_order["start_from"] = self.options["play_order"]["start_from"]
        except KeyError:
            pass

    def process(self) -> None:
        # should cache this html parsing so we don't do it for every plugin
        for plg in self.options.get("plugins", []):
            if hasattr(plg, "before_write"):
                plg.before_write(self.book)

        for item in self.book.get_items():
            if isinstance(item, EpubHtml):
                for plg in self.options.get("plugins", []):
                    if hasattr(plg, "html_before_write"):
                        plg.html_before_write(self.book, item)

    def _write_container(self) -> None:
        container_xml = CONTAINER_XML % {"folder_name": self.book.FOLDER_NAME}
        self.out.writestr(self.zipinfo(CONTAINER_PATH), container_xml)

    def _iter_metadata(self):
        """Yield ``(value, attributes)`` for every metadata entry."""
        for ns_values in self.book.metadata.values():
            for values in ns_values.values():
                yield from values

    def _has_meta_property(self, prop: str) -> bool:
        return any(
            attrib and attrib.get("property") == prop
            for _, attrib in self._iter_metadata()
        )

    def _write_opf_metadata(self, root: etree._Element) -> None:
        nsmap = {"dc": NAMESPACES["DC"]}
        nsmap.update(self.book.namespaces)

        metadata = etree.SubElement(root, QName(root, "metadata"), nsmap=nsmap)

        # Write these directly instead of adding them to book.metadata: the
        # writer must not mutate the book, otherwise a second write would keep
        # the first timestamp and append duplicate provenance entries.
        if not self._has_meta_property("dcterms:modified"):
            # The EPUB specification requires dcterms:modified to be a UTC timestamp.
            # astimezone() treats a naive datetime as local time before converting.
            mtime_utc = self.options["mtime"].astimezone(timezone.utc)
            el = etree.SubElement(metadata, QName(root, "meta"),
                                  {"property": "dcterms:modified"})
            el.text = mtime_utc.strftime("%Y-%m-%dT%H:%M:%SZ")

        if not self._has_meta_property("dcterms:provenance"):
            version = ".".join([str(s) for s in VERSION])
            el = etree.SubElement(metadata, QName(root, "meta"),
                                  {"property": "dcterms:provenance"})
            el.text = f"Ebook-lib {version}"

        for ns_name, ns_values in self.book.metadata.items():
            for name, values in ns_values.items():
                tag = get_qname(ns_name, name)
                for value in values:
                    try:
                        text, attrib = value
                        el = etree.SubElement(metadata, tag, attrib)
                        if text:
                            el.text = text
                    except ValueError:
                        logging.info('Could not create metadata "%s".', name)

    def _write_opf_manifest(self, root: etree._Element) -> str | None:
        manifest = etree.SubElement(root, QName(root, "manifest"))
        _ncx_id = None

        # mathml, scripted, svg, remote-resources, and switch
        # nav
        # cover-image

        for item in (x for x in self.book.get_items() if x.manifest):
            item_id = item.id or ""
            attrib = {"id": item_id,
                    "href": item.file_name,
                    "media-type": item.media_type}
            if isinstance(item, EpubNav):
                attrib["properties"] = "nav"
            elif isinstance(item, EpubNcx):
                _ncx_id = item.id
            elif isinstance(item, EpubCover):
                attrib["properties"] = "cover-image"
            else:
                properties = getattr(item, "properties", None)
                if properties:
                    attrib["properties"] = " ".join(properties)

                media_overlay = getattr(item, "media_overlay", None)
                if media_overlay is not None:
                    attrib["media-overlay"] = media_overlay

                media_duration = getattr(item, "media_duration", None)
                if media_duration is not None:
                    attrib["duration"] = media_duration

            etree.SubElement(manifest, QName(root, "item"), attrib=attrib)

        return _ncx_id

    def _write_opf_spine(self, root: etree._Element, ncx_id: str | None) -> None:
        attrib = {"toc": ncx_id or "ncx"}
        if self.book.direction and self.options["spine_direction"]:
            attrib["page-progression-direction"] = self.book.direction

        spine = etree.SubElement(root, QName(root, "spine"), attrib=attrib)

        for _item in self.book.spine:
            # this is for now
            # later we should be able to fetch things from tuple

            is_linear = True

            if isinstance(_item, tuple):
                item = _item[0]

                if len(_item) > 1:
                    if _item[1] == "no":
                        is_linear = False
            else:
                item = _item

            if isinstance(item, EpubHtml):
                opts = {"idref": item.get_id() or ""}

                if not item.is_linear or not is_linear:
                    opts["linear"] = "no"
            elif isinstance(item, EpubItem):
                opts = {"idref": item.get_id() or ""}

                if not item.is_linear or not is_linear:
                    opts["linear"] = "no"
            else:
                opts = {"idref": item}

                itm = self.book.get_item_with_id(item)

                if itm is not None and (not itm.is_linear or not is_linear):
                    opts["linear"] = "no"

            etree.SubElement(spine, QName(root, "itemref"), attrib=opts)

    def _write_opf_guide(self, root: etree._Element) -> None:
        # - http://www.idpf.org/epub/20/spec/OPF_2.0.1_draft.htm#Section2.6

        if not self.book.guide or not self.options.get("epub2_guide"):
            return
        guide = etree.SubElement(root, QName(root, "guide"))

        for ref in self.book.guide:
            item = ref.get("item")
            if item is not None:
                _href = item.file_name or ""
                _title = item.title or ""
            else:
                _href = ref.get("href", "")
                _title = ref.get("title", "")
            attrib = {"type": ref.get("type", ""),
                      "title": _title,
                      "href": _href}
            etree.SubElement(guide, QName(root, "reference"), attrib=attrib)

    def _write_opf_bindings(self, root: etree._Element) -> None:
        if not self.book.bindings:
            return
        bindings = etree.SubElement(root, QName(root, "bindings"))
        for attrib in self.book.bindings:
            etree.SubElement(bindings, QName(root, "mediaType"), attrib=attrib)

    def _write_opf_file(self, root: etree._Element) -> None:
        self.out.writestr(self.zipinfo(f"{self.book.FOLDER_NAME}/content.opf"), xml_tostring(root))

    def _write_opf(self) -> None:
        prefixes = self.book.prefixes
        prefix = " ".join(f"{k}: {v}" for k, v in prefixes.items() if k and v)
        attrib = {
            "version": "3.0",
            "unique-identifier": self.book.IDENTIFIER_ID
        }
        if prefix:
            attrib["prefix"] = prefix
        if self.book.direction and self.options["package_direction"]:
            attrib["dir"] = self.book.direction

        xmlns = NAMESPACES["OPF"]

        root = etree.Element(QName(xmlns, "package"),
                             attrib=attrib,
                             nsmap={None: xmlns})

        # METADATA
        self._write_opf_metadata(root)

        # MANIFEST
        _ncx_id = self._write_opf_manifest(root)

        # SPINE
        self._write_opf_spine(root, _ncx_id)

        # GUIDE
        self._write_opf_guide(root)

        # BINDINGS
        self._write_opf_bindings(root)

        # WRITE FILE
        self._write_opf_file(root)

    def _get_nav(self, item: EpubNav) -> bytes:
        # just a basic navigation for now
        nav_xml = parse_xml(self.book.get_template("nav") or b"")
        root = nav_xml.getroot()

        root.set("lang", self.book.language)
        root.attrib[get_qname("xml", "lang")] = self.book.language

        nav_dir_name = os.path.dirname(item.file_name)

        head = etree.SubElement(root, "head")
        title = etree.SubElement(head, "title")
        title.text = item.title or self.book.title

        # for now this just handles css files and ignores others
        for link in item.links:
            opts = {"href": link.get("href", ""),
                    "rel": "stylesheet",
                    "type": "text/css"}
            _ = etree.SubElement(head, "link", opts)

        body = etree.SubElement(root, "body")
        if item.direction:
            body.set("dir", item.direction)
        epub_type_attr = get_qname("epub", "type")
        nav = etree.SubElement(
            body,
            "nav",
            {
                epub_type_attr: "toc",
                "id": "id",
                "role": "doc-toc",
            },
        )

        content_title = etree.SubElement(nav, "h2")
        content_title.text = item.title or self.book.title

        def _create_section(node, items):
            ol = etree.SubElement(node, "ol")
            for item in items:
                if isinstance(item, tuple | list):
                    parent, children, *_ = item
                    li = etree.SubElement(ol, "li")
                    if isinstance(parent, EpubHtml):
                        href = zip_path.relpath(parent.file_name, nav_dir_name)
                        a = etree.SubElement(li, "a", {"href": href})
                    elif isinstance(parent, Section) and parent.href != "":
                        href = zip_path.relpath(parent.href, nav_dir_name)
                        a = etree.SubElement(li, "a", {"href": href})
                    elif isinstance(parent, Link):
                        href = zip_path.relpath(parent.href, nav_dir_name)
                        a = etree.SubElement(li, "a", {"href": href})
                    else:
                        a = etree.SubElement(li, "span")
                    a.text = parent.title
                    if children:
                        _create_section(li, children)

                elif isinstance(item, Link):
                    li = etree.SubElement(ol, "li")
                    href = zip_path.relpath(item.href, nav_dir_name)
                    a = etree.SubElement(li, "a", {"href": href})
                    a.text = item.title
                elif isinstance(item, EpubHtml):
                    li = etree.SubElement(ol, "li")
                    href = zip_path.relpath(item.file_name, nav_dir_name)
                    a = etree.SubElement(li, "a", {"href": href})
                    a.text = item.title

        _create_section(nav, self.book.toc)

        # LANDMARKS / GUIDE
        # - http://www.idpf.org/epub/30/spec/epub30-contentdocs.html#sec-xhtml-nav-def-types-landmarks

        if len(self.book.guide) > 0 and self.options.get("epub3_landmark"):
            # Epub2 guide types do not map completely to epub3 landmark types.
            guide_to_landscape_map = {"notes": "rearnotes", "text": "bodymatter"}

            guide_nav = etree.SubElement(body, "nav", {epub_type_attr: "landmarks"})

            guide_content_title = etree.SubElement(guide_nav, "h2")
            guide_content_title.text = self.options.get("landmark_title", "Guide")

            guild_ol = etree.SubElement(guide_nav, "ol")

            for elem in self.book.guide:
                chap = elem.get("item")
                if chap is not None:
                    _href = chap.file_name
                    _title = chap.title
                else:
                    _href = elem.get("href", "")
                    _title = elem.get("title", "")

                if not _href:
                    # a landmark entry without a target can not be represented in the nav document
                    continue

                li_item = etree.SubElement(guild_ol, "li")

                guide_type = elem.get("type") or ""
                a_item = etree.SubElement(
                    li_item,
                    "a",
                    {
                        epub_type_attr: guide_to_landscape_map.get(guide_type, guide_type),
                        "href": zip_path.relpath(_href, nav_dir_name),
                    },
                )
                a_item.text = _title

        # PAGE-LIST
        if self.options.get("epub3_pages"):
            inserted_pages = get_pages_for_items(
                [item for item in self.book.get_items_of_type(ITEM_DOCUMENT) if not isinstance(item, EpubNav)]
            )

            if len(inserted_pages) > 0:
                pagelist_nav = etree.SubElement(
                    body,
                    "nav",
                    {
                        epub_type_attr: "page-list",
                        "id": "pages",
                        "hidden": "hidden",
                    },
                )
                pagelist_content_title = etree.SubElement(pagelist_nav, "h2")
                pagelist_content_title.text = self.options.get("pages_title", "Pages")

                pages_ol = etree.SubElement(pagelist_nav, "ol")

                for filename, pageref, label in inserted_pages:
                    li_item = etree.SubElement(pages_ol, "li")

                    _href = f"{filename}#{pageref}"
                    _title = label

                    a_item = etree.SubElement(
                        li_item,
                        "a",
                        {
                            "href": zip_path.relpath(_href, nav_dir_name),
                        },
                    )
                    a_item.text = _title

        return xml_tostring(nav_xml)

    def _get_ncx(self) -> bytes:
        # we should be able to setup language for NCX as also
        ncx = parse_xml(self.book.get_template("ncx") or b"")
        root = ncx.getroot()

        head = etree.SubElement(root, "head")

        # get this id
        _uid = etree.SubElement(head, "meta", {"content": self.book.uid, "name": "dtb:uid"})
        _uid = etree.SubElement(head, "meta", {"content": "0", "name": "dtb:depth"})
        _uid = etree.SubElement(head, "meta", {"content": "0", "name": "dtb:totalPageCount"})
        _uid = etree.SubElement(head, "meta", {"content": "0", "name": "dtb:maxPageNumber"})

        doc_title = etree.SubElement(root, "docTitle")
        title = etree.SubElement(doc_title, "text")
        title.text = self.book.title

        # For now just make a very simple navMap
        nav_map = etree.SubElement(root, "navMap")

        def _add_play_order(nav_point):
            nav_point.set("playOrder", str(self._play_order["start_from"]))
            self._play_order["start_from"] += 1

        def _create_section(node, items, uid):
            for item in items:
                if isinstance(item, tuple | list):
                    section, subsection = item[0], item[1]
                    if isinstance(section, EpubHtml):
                        _id = section.get_id() or ""
                    else:
                        _id = f"sep_{uid}"
                    np = etree.SubElement(node,"navPoint", {"id": _id})

                    if self._play_order["enabled"]:
                        _add_play_order(np)

                    nl = etree.SubElement(np, "navLabel")
                    nt = etree.SubElement(nl, "text")
                    nt.text = section.title

                    # CAN NOT HAVE EMPTY SRC HERE
                    href = ""
                    if isinstance(section, EpubHtml):
                        href = section.file_name
                    elif isinstance(section, Section) and section.href != "":
                        href = section.href
                    elif isinstance(section, Link):
                        href = section.href

                    _nc = etree.SubElement(np, "content", {"src": href})

                    uid = _create_section(np, subsection, uid + 1)
                elif isinstance(item, Link):
                    _parent = node
                    _content = _parent.find("content")

                    if _content is not None:
                        if _content.get("src") == "":
                            _content.set("src", item.href)

                    np = etree.SubElement(node, "navPoint", {"id": item.uid or ""})

                    if self._play_order["enabled"]:
                        _add_play_order(np)

                    nl = etree.SubElement(np, "navLabel")
                    nt = etree.SubElement(nl, "text")
                    nt.text = item.title

                    _nc = etree.SubElement(np, "content", {"src": item.href})
                elif isinstance(item, EpubHtml):
                    _parent = node
                    _content = _parent.find("content")

                    if _content is not None:
                        if _content.get("src") == "":
                            _content.set("src", item.file_name)

                    np = etree.SubElement(node, "navPoint", {"id": item.get_id() or ""})

                    if self._play_order["enabled"]:
                        _add_play_order(np)

                    nl = etree.SubElement(np, "navLabel")
                    nt = etree.SubElement(nl, "text")
                    nt.text = item.title

                    _nc = etree.SubElement(np, "content", {"src": item.file_name})

            return uid

        _create_section(nav_map, self.book.toc, 0)

        return xml_tostring(ncx)

    def _write_items(self) -> None:
        for item in self.book.get_items():
            if isinstance(item, EpubNcx):
                self.out.writestr(self.zipinfo(f"{self.book.FOLDER_NAME}/{item.file_name}"),
                                  self._get_ncx())
            elif isinstance(item, EpubNav):
                self.out.writestr(self.zipinfo(f"{self.book.FOLDER_NAME}/{item.file_name}"),
                                  self._get_nav(item))
            elif item.manifest:
                self.out.writestr(self.zipinfo(f"{self.book.FOLDER_NAME}/{item.file_name}"),
                                  item.get_content())
            else:
                self.out.writestr(self.zipinfo(item.file_name),
                                  item.get_content())

    def write(self) -> None:
        # zipfile stubs expect IO[bytes], but any object with write/seek/tell works
        with ZipFile(self.file_name,
                     "w",
                     ZIP_DEFLATED,
                     compresslevel=self.options["compresslevel"]) as self.out:  # pylint: disable=W0201
            self.out.writestr("mimetype", "application/epub+zip", compress_type=ZIP_STORED)
            self._write_container()
            self._write_opf()
            self._write_items()


def write_epub(name: EpubTarget, book: EpubBook, options: dict[str, Any] | None = None) -> bool:
    """
    Creates epub file with the content defined in EpubBook.

    >>> ebooklib.write_epub('book.epub', book)

    :Args:
      - name: file name for the output file
      - book: instance of EpubBook
      - options: extra opions as dictionary (optional)
    """
    epub = EpubWriter(name, book, options)

    epub.process()

    try:
        epub.write()
    except Exception as e:  # pylint: disable=W0718
        if options and options.get("raise_exceptions"):
            raise e
        else:
            return False

    return True
