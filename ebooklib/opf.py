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

"""OPF(Open Packaging Format) file in EPUB book."""
from __future__ import annotations
import logging
from datetime import timezone
from decimal import Decimal
from typing import Any, TYPE_CHECKING
from urllib.parse import unquote

from lxml import etree
from lxml.etree import QName, SubElement  # pylint: disable=E0611

from .base import FileObject
from .consts import FONT_MEDIA_TYPES, IMAGE_MEDIA_TYPES, NAMESPACES, VERSION
from .exceptions import EpubException
from .items import (
    EpubCover,
    EpubCoverHtml,
    EpubFont,
    EpubHtml,
    EpubImage,
    EpubItem,
    EpubNav,
    EpubNcx,
    EpubSMIL
)
from .pytype import FileReader, XmlElement
from .utils import get_qname, join_path, parse_xhtml, parse_xml, xml_tostring
if TYPE_CHECKING:
    from .book import EpubBook

_DURATION_UNITS = {
    "ms": Decimal("0.001"),
    "s": Decimal(1),
    "min": Decimal(60),
    "h": Decimal(3600),
}


def duration_to_seconds(value: str) -> Decimal:
    """Convert a SMIL clock value to seconds.

    Supports both full/partial clock values
    (``"01:02:03.5"``, ``"02:03.5"``)
    and
    timecount values (``"10.5s"``, ``"500ms"``, ``"2min"``, ``"1h"``).
    """
    value = value.strip()
    if ":" in value:
        result = Decimal(0)
        for part in value.split(":"):
            result = result * 60 + Decimal(part)
        return result

    # Check "ms" before "s" because it is a suffix of the latter.
    for unit in ("ms", "min", "h", "s"):
        if value.endswith(unit):
            return Decimal(value[:-len(unit)].strip()) * _DURATION_UNITS[unit]
    return Decimal(value)


def seconds_to_duration(seconds: Decimal) -> str:
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    sec = format(seconds.normalize(), "f")
    return f"{int(hours):02d}:{int(minutes):02d}:{sec.zfill(2)}"


# pylint: disable=unused-argument
class OPF(FileObject):
    """
    OPF(Open Packaging Format) 3.0 file in EPUB book.
    """

    def __init__(self, file_name: str = "content.opf") -> None:
        super().__init__()
        self.file_name = file_name
        self.root: XmlElement | None
        self.metadata: XmlElement | None
        self.manifest: XmlElement | None
        self.spine: XmlElement | None
        self.guide: XmlElement | None
        self.bindings: XmlElement | None
        self.ncx_id: str | None
        self._reset()

    def _reset(self):
        self.root = None
        self.metadata = None
        self.manifest = None
        self.spine = None
        self.guide = None
        self.bindings = None
        self.ncx_id = None

    @property
    def tree(self):
        if self.root is not None:
            return self.root.getroottree()
        return None

    def _iter_metadata(self, book: EpubBook):
        """Yield ``(value, attributes)`` for every metadata entry."""
        for ns_values in book.metadata.values():
            for values in ns_values.values():
                yield from values

    def _has_meta_property(self, book: EpubBook, prop: str) -> bool:
        return any(
            attrib and attrib.get("property") == prop
            for _, attrib in self._iter_metadata(book)
        )

    def _dump_package(self, book: EpubBook, **options):
        attrib = {
            "version": book.EPUB_VERSION,
            "unique-identifier": book.identifier_id or book.IDENTIFIER_ID
        }
        if prefixes := book.prefixes:
            prefix = " ".join(f"{k}: {v}" for k, v in prefixes.items() if k and v)
            attrib["prefix"] = prefix
        if book.direction and options["package_direction"]:
            attrib["dir"] = book.direction

        xmlns = NAMESPACES["OPF"]

        self.root = etree.Element(QName(xmlns, "package"),
                                  attrib=attrib,
                                  nsmap={None: xmlns})

    def _dump_metadata(self, book: EpubBook, **options) -> None:
        nsmap = {"dc": NAMESPACES["DC"]}
        nsmap.update(book.namespaces)

        metadata = SubElement(self.root,
                              QName(self.root, "metadata"),
                              nsmap=nsmap)

        for ns_name, ns_values in book.metadata.items():
            for name, values in ns_values.items():
                tag = get_qname(ns_name, name)
                for text, attrib in values:
                    try:
                        el = SubElement(metadata, tag, attrib=attrib)
                        if text:
                            el.text = text
                    except ValueError:
                        logging.info('Could not create metadata "%s".', name)

        # Write these directly instead of adding them to book.metadata: the
        # writer must not mutate the book, otherwise a second write would keep
        # the first timestamp and append duplicate provenance entries.
        if not self._has_meta_property(book, "dcterms:modified"):
            # The EPUB specification requires dcterms:modified to be a UTC timestamp.
            # astimezone() treats a naive datetime as local time before converting.
            mtime_utc = options["mtime"].astimezone(timezone.utc)
            el = etree.SubElement(metadata, QName(metadata, "meta"),
                                  {"property": "dcterms:modified"})
            el.text = mtime_utc.strftime("%Y-%m-%dT%H:%M:%SZ")

        if not self._has_meta_property(book, "dcterms:provenance"):
            version = ".".join([str(s) for s in VERSION])
            el = etree.SubElement(metadata, QName(metadata, "meta"),
                                  {"property": "dcterms:provenance"})
            el.text = f"Ebook-lib {version}"

        self.metadata = metadata

    def _dump_manifest(self, book: EpubBook, **options):
        manifest = SubElement(self.root, QName(self.root, "manifest"))

        # mathml, scripted, svg, remote-resources, and switch
        # nav
        # cover-image

        durations: list[str] = []

        for item in (x for x in book.get_items() if x.manifest):
            item_id = item.id or ""
            attrib = {"id": item_id,
                      "href": item.file_name,
                      "media-type": item.media_type}
            if isinstance(item, EpubNav):
                attrib["properties"] = "nav"
            elif isinstance(item, EpubNcx):
                self.ncx_id = item.id
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
                    # EPUB 3.2+ carries the duration on the manifest item.
                    attrib["duration"] = media_duration
                    if media_overlay is not None:
                        # EPUB 3.0-style metadata for media overlays.
                        opts = {"property": "media:duration",
                                "refines": f"#{media_overlay}"}
                        meta = SubElement(self.metadata,
                                          QName(self.metadata, 'meta'),
                                          attrib=opts)
                        meta.text = media_duration
                        durations.append(media_duration)
            SubElement(manifest, QName(self.root, "item"), attrib=attrib)
        if durations:
            try:
                total = sum(duration_to_seconds(x) for x in durations)
            except (ArithmeticError, ValueError):
                logging.warning("Could not parse media durations: %r", durations)
            else:
                opts = {"property": "media:duration"}
                meta = SubElement(self.metadata,
                                  QName(self.metadata, 'meta'),
                                  attrib=opts)
                meta.text = seconds_to_duration(total)
        self.manifest = manifest

    def _dump_spine(self, book: EpubBook, **options) -> None:
        attrib = {"toc": self.ncx_id or "ncx"}
        if book.direction and options["spine_direction"]:
            attrib["page-progression-direction"] = book.direction

        spine = SubElement(self.root, QName(self.root, "spine"), attrib=attrib)

        for _item in book.spine:
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

                itm = book.get_item_with_id(item)

                if itm is not None and (not itm.is_linear or not is_linear):
                    opts["linear"] = "no"

            SubElement(spine, QName(spine, "itemref"), attrib=opts)
        self.spine = spine

    def _dump_guide(self, book: EpubBook, **options) -> None:
        # - http://www.idpf.org/epub/20/spec/OPF_2.0.1_draft.htm#Section2.6

        if not book.guide or not options.get("epub2_guide"):
            return
        guide = SubElement(self.root, QName(self.root, "guide"))

        for ref in book.guide:
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
            SubElement(guide, QName(guide, "reference"), attrib=attrib)
        self.guide = guide

    def _dump_bindings(self, book: EpubBook, **options) -> None:  # pylint: disable=unused-argument
        if not book.bindings:
            return
        bindings = SubElement(self.root, QName(self.root, "bindings"))
        for attrib in book.bindings:
            SubElement(bindings, QName(bindings, "mediaType"), attrib=attrib)
        self.bindings = bindings

    def get_content(self, book: EpubBook, **options) -> bytes:
        """
        Returns the content of this file.
        """
        self._reset()
        # PACKAGE(root)
        self._dump_package(book, **options)
        # METADATA
        self._dump_metadata(book, **options)
        # MANIFEST
        self._dump_manifest(book, **options)
        # SPINE
        self._dump_spine(book, **options)
        # GUIDE
        self._dump_guide(book, **options)
        # BINDINGS
        self._dump_bindings(book, **options)
        return xml_tostring(self.root)

    def _read(self, reader: FileReader, *paths: str) -> bytes:
        return reader.read(join_path(*paths))

    def _load_package(self, reader: FileReader, book: EpubBook, **options) -> None:
        # get epub version
        version = self.root.get("version")
        if version is None:
            raise EpubException(-1, "Can not find package version")
        book.version = version

        # get unique-identifier
        identifier = self.root.get("unique-identifier")
        if identifier is None:
            raise EpubException(-1, "Can not find package unique-identifier")
        book.identifier_id = identifier

        # get xml:lang

    def _load_metadata(self, reader: FileReader, book: EpubBook, **options) -> None:
        # get metadata
        metadata = self.metadata
        if metadata is None:
            raise EpubException(-1, "Can not find metadata element")

        nsdict: dict[str | None, dict[str, list[Any]]]

        nsdict = {v: {} for v in metadata.nsmap.values()}

        def add_item(namespace, tag, value, extra):
            namespace = nsdict.setdefault(namespace, {})
            values = namespace.setdefault(tag, [])
            values.append((value, extra))

        for el in (x for x in metadata if isinstance(x.tag, str)):
            tag = QName(el.tag)
            add_item(tag.namespace, tag.localname, el.text, dict(el.items()))

        book.metadata = nsdict

        titles = book.get_metadata("DC", "title")
        if len(titles) > 0:
            book.title = titles[0][0]

        for value, others in book.get_metadata("DC", "identifier"):
            if others.get("id") == book.identifier_id:
                book.uid = value

    @staticmethod
    def _cover_image_name(content: bytes | str) -> str:
        """Return the image path referenced by a cover XHTML document."""
        try:
            tree = parse_xhtml(content)
        except (etree.ParserError, etree.XMLSyntaxError, TypeError, ValueError):
            return ""
        if (image := tree.find(f".//{get_qname('xhtml', 'img')}")) is None:
            return ""
        return image.get("src", "")

    def _load_manifest(self, reader: FileReader, book: EpubBook, **options) -> None:
        manifest = self.manifest
        if manifest is None:
            raise EpubException(-1, "Can not find manifest element")

        opf_dir = book.package_dir

        for el in manifest.findall(QName(manifest, 'item')):
            uid = el.get("id")
            href = unquote(el.get("href", ""))
            media_type = el.get("media-type") or ""
            properties = [x for x in el.get("properties", "").split(" ") if x]

            # people use wrong content types
            if media_type == "image/jpg":
                media_type = "image/jpeg"

            item: EpubItem

            if media_type == EpubNcx.MEDIA_TYPE:
                item = EpubNcx(uid=uid, file_name=href)
                item.content = self._read(reader, opf_dir, item.file_name)
            elif media_type == EpubSMIL.MEDIA_TYPE:
                item = EpubSMIL(uid=uid, file_name=href)
                item.content = self._read(reader, opf_dir, item.file_name)
            elif media_type == EpubHtml.MEDIA_TYPE:
                if "nav" in properties:
                    item = EpubNav(uid=uid, file_name=href)
                    item.content = self._read(reader, opf_dir, item.file_name)
                elif "cover" in properties:
                    item = EpubCoverHtml(uid=uid, file_name=href)
                    item.content = self._read(reader, opf_dir, item.file_name)
                    item.image_name = self._cover_image_name(item.content)
                else:
                    item = EpubHtml(uid=uid, file_name=href, media_type=media_type)
                    item.media_overlay = el.get("media-overlay", None)
                    item.media_duration = el.get("duration", None)
                    item.content = self._read(reader, opf_dir, item.file_name)
                    item.properties = properties
            elif media_type in IMAGE_MEDIA_TYPES:
                if "cover-image" in properties:
                    item = EpubCover(uid=uid, file_name=href, media_type=media_type)
                    item.content = self._read(reader, opf_dir, item.file_name)
                else:
                    item = EpubImage(uid=uid, file_name=href, media_type=media_type)
                    item.content = self._read(reader, opf_dir, item.file_name)
            elif media_type in FONT_MEDIA_TYPES:
                item = EpubFont(uid=uid, file_name=href, media_type=media_type)
                item.content = self._read(reader, opf_dir, item.file_name)
            else:
                item = EpubItem(uid=uid, file_name=href, media_type=media_type)
                item.content = self._read(reader, opf_dir, item.file_name)
            book.add_item(item)

        # Associate EPUB 3.0 media:duration metadata with the items it refines.
        for text, attrib in self._iter_metadata(book):
            if not text or not attrib or attrib.get("property") != "media:duration":
                continue
            refines = attrib.get("refines", "")
            if not refines:
                continue
            ref_id = refines.lstrip("#")
            for candidate in book.get_items():
                if candidate.id == ref_id or getattr(candidate, "media_overlay", None) == ref_id:
                    candidate.media_duration = text

    def _load_spine(self, reader: FileReader, book: EpubBook, **options) -> None:
        if self.spine is None:
            raise EpubException(-1, "Can not find spine element")
        spine = self.spine
        book.spine = [(t.get("idref"), t.get("linear", "yes")) for t in spine]
        book.set_direction(self.spine.get("page-progression-direction", None))

    def _load_guide(self, reader: FileReader, book: EpubBook, **options) -> None:
        if self.guide is None:
            return
        keys = ("href", "title", "type")
        book.guide = [{k: x.get(k) for k in keys} for x in self.guide]

    def set_content(self, content: bytes, reader: FileReader, book: EpubBook, **options) -> bytes:
        """
        Returns the content of this file.
        """
        self._reset()
        tree = parse_xml(content)
        self.root = tree.getroot()
        self.metadata = self.root.find(QName(self.root, 'metadata'))
        self.manifest = self.root.find(QName(self.root, 'manifest'))
        self.spine = self.root.find(QName(self.root, 'spine'))
        self.guide = self.root.find(QName(self.root, 'guide'))
        self._load_package(reader, book, **options)
        self._load_metadata(reader, book, **options)
        self._load_manifest(reader, book, **options)
        self._load_spine(reader, book, **options)
        self._load_guide(reader, book, **options)
