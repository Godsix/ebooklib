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

# pylint: disable=E0611, I1101
"""Items which can be part of an EPUB book."""
import os.path
import posixpath as zip_path
from collections.abc import Iterator
from functools import wraps
from typing import TYPE_CHECKING, Any

from lxml import etree
from lxml.etree import QName

from .base import FileObject
from .consts import (
    EXTENSIONS,
    ITEM_COVER,
    ITEM_DOCUMENT,
    ITEM_FONT,
    ITEM_IMAGE,
    ITEM_SCRIPT,
    ITEM_SMIL,
    ITEM_STYLE,
    ITEM_UNKNOWN,
    NAMESPACES,
    XHTML5_DOCTYPE
)
from .pytype import ElementTree, XmlElement
from .toc import Link, Section
from .utils import (
    format_newline,
    format_uri,
    get_pages_for_items,
    get_qname,
    parse_xhtml,
    parse_xml,
    xhtml_tostring,
    xml_tostring
)


if TYPE_CHECKING:
    from .book import EpubBook


def check_attach_book(func):
    """Decorator for checking if item is attached to a book."""
    @wraps(func)
    def wrapper(self, *args: Any, **kwargs: Any) -> None:
        if self.book is None:
            class_name = type(self).__name__
            raise ValueError(f"{class_name} item is not attached to a book. "
                             "Call book.add_item() first.")
        return func(self, *args, **kwargs)
    return wrapper


class EpubItem(FileObject):
    """
    Base class for the items in a book.
    """
    MEDIA_TYPE: str = ""
    ITEM_TYPE: int | None = None

    def __init__(
        self,
        uid: str | None = None,
        file_name: str = "",
        media_type: str = "",
        content: str | bytes | None = None,
        manifest: bool = True,
    ) -> None:
        """
        :Args:
          - uid: Unique identifier for this item (optional)
          - file_name: File name for this item (optional)
          - media_type: Media type for this item (optional)
          - content: Content for this item (optional)
          - manifest: Manifest for this item (optional)
        """
        super().__init__()
        self.id = uid
        self.file_name = file_name
        self.media_type = media_type or self.MEDIA_TYPE
        self.content: str | bytes = content or b""
        self.is_linear = True
        self.manifest = manifest

        self.book: EpubBook | None = None

    @property
    def file_name(self):
        """
        Returns file name for this item.

        :Returns:
          Returns file name as string.
        """
        return getattr(self, "_file_name", "")

    @file_name.setter
    def file_name(self, value):
        """
        Sets file name for this item.
        """
        self._file_name = format_uri(value or "")

    def get_id(self) -> str | None:
        """
        Returns unique identifier for this item.

        :Returns:
          Returns uid number as string.
        """
        return self.id

    def get_name(self) -> str:
        """
        Returns name for this item. By default it is always file name but it does not have to be.

        :Returns:
          Returns file name for this item.
        """
        return self.file_name

    def get_type(self) -> int:
        """
        Guess type according to the file extension. Might not be the best way how to do it, but it works for now.

        Items can be of type:
          - ITEM_UNKNOWN = 0
          - ITEM_IMAGE = 1
          - ITEM_STYLE = 2
          - ITEM_SCRIPT = 3
          - ITEM_NAVIGATION = 4
          - ITEM_VECTOR = 5
          - ITEM_FONT = 6
          - ITEM_VIDEO = 7
          - ITEM_AUDIO = 8
          - ITEM_DOCUMENT = 9
          - ITEM_COVER = 10

        We map type according to the extensions which are defined in EXTENSIONS.

        :Returns:
          Returns type of the item as number.
        """
        if self.ITEM_TYPE is not None:
            return self.ITEM_TYPE
        ext = zip_path.splitext(self.get_name())[-1].lower()
        return next((t for t, exts in EXTENSIONS.items() if ext in exts), ITEM_UNKNOWN)

    def get_content(self, default: str | bytes | None = None, **options) -> str | bytes:
        """
        Returns content of the item. Content is usually of type 'bytes' but
        API users assign 'str' as well.

        :Args:
          - default: Default value for the content if it is not already defined.

        :Returns:
          Returns content of the item.
        """
        return self.content or default or b""

    def set_content(self, content: str | bytes) -> None:
        """
        Sets content value for this item.

        :Args:
          - content: Content value
        """
        self.content = content

    def __str__(self) -> str:
        return repr(self)

    def __repr__(self) -> str:
        cls_name = self.__class__.__name__
        if self.file_name:
            return f"<{cls_name}:{self.id}:{self.file_name}>"
        return f"<{cls_name}:{self.id}>"


class EpubNcx(EpubItem):
    """Represents Navigation Control File (NCX) in the EPUB."""
    MEDIA_TYPE: str = "application/x-dtbncx+xml"

    def __init__(self, uid: str | None = "ncx", file_name: str = "toc.ncx") -> None:
        super().__init__(uid=uid, file_name=file_name, media_type=self.MEDIA_TYPE)

    @check_attach_book
    def get_content(self, default: str | bytes | None = None, **options) -> bytes:
        play_order = {"enabled": False, "start_from": 1}
        if _play_order := options.get("play_order"):
            play_order.update(_play_order)
        # we should be able to setup language for NCX as also
        tree = parse_xml(self.book.get_template("ncx", b""))
        root = tree.getroot()

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

        def _add_play_order(nav_point: XmlElement):
            nav_point.set("playOrder", str(play_order["start_from"]))
            play_order["start_from"] += 1

        def _create_section(node, items, uid):
            for item in items:
                if isinstance(item, tuple | list):
                    section, subsection = item[0], item[1]
                    if isinstance(section, EpubHtml):
                        _id = section.get_id() or ""
                    else:
                        _id = f"sep_{uid}"
                    np = etree.SubElement(node, "navPoint", {"id": _id})

                    if play_order["enabled"]:
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

                    if play_order["enabled"]:
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

                    if play_order["enabled"]:
                        _add_play_order(np)

                    nl = etree.SubElement(np, "navLabel")
                    nt = etree.SubElement(nl, "text")
                    nt.text = item.title

                    _nc = etree.SubElement(np, "content", {"src": item.file_name})

            return uid

        _create_section(nav_map, self.book.toc, 0)

        return xml_tostring(tree)


class EpubHtml(EpubItem):
    """
    Represents HTML document in the EPUB file.
    """
    MEDIA_TYPE: str = "application/xhtml+xml"
    ITEM_TYPE: int = ITEM_DOCUMENT
    TEMPLATE: str = "chapter"

    def __init__(
        self,
        uid: str | None = None,
        file_name: str = "",
        media_type: str = "",
        content: str | bytes | None = None,
        title: str = "",
        lang: str | None = None,
        direction: str | None = None,
        media_overlay: str | None = None,
        media_duration: str | None = None,
    ) -> None:
        super().__init__(uid, file_name, media_type, content)

        self.title = title
        self.lang = lang
        self.direction = direction

        self.media_overlay = media_overlay
        self.media_duration = media_duration

        self.metas: list[dict[str, Any]] = []
        self.links: list[dict[str, Any]] = []
        self.properties: list[str] = []
        self.pages: list[Any] = []
        self.tree: ElementTree | None = None
        self.body: str | None = None

    def is_chapter(self) -> bool:
        """
        Returns if this document is chapter or not.

        :Returns:
          Returns book value.
        """
        return True

    def set_language(self, lang: str | None) -> None:
        """
        Sets language for this book item. By default it will use language of the book but it
        can be overwritten with this call.
        """
        self.lang = lang

    def get_language(self) -> str | None:
        """
        Get language code for this book item. Language of the book item can be different from
        the language settings defined globaly for book.

        :Returns:
          As string returns language code.
        """
        return self.lang

    def add_meta(self, **kwgs: Any) -> None:
        """
        Add additional <meta> to the document.

        >>> add_meta(name='viewport', content='width=device-width, initial-scale=1')
        """
        self.metas.append(kwgs)

    def get_metas(self) -> Iterator[dict[str, Any]]:
        """
        Returns list of additional metas defined for this document.

        :Returns:
          As tuple return list of metas.
        """
        return (meta for meta in self.metas)

    def add_link(self, **kwgs: Any) -> None:
        """
        Add additional link to the document. Links will be embeded only inside of this document.

        >>> add_link(href='styles.css', rel='stylesheet', type='text/css')
        """
        self.links.append(kwgs)
        if kwgs.get("type") == "text/javascript":
            if "scripted" not in self.properties:
                self.properties.append("scripted")

    def get_links(self) -> Iterator[dict[str, Any]]:
        """
        Returns list of additional links defined for this document.

        :Returns:
          As tuple return list of links.
        """
        return (link for link in self.links)

    def get_links_of_type(self, link_type: str) -> Iterator[dict[str, Any]]:
        """
        Returns list of additional links of specific type.

        :Returns:
          As tuple returns list of links.
        """
        return (link for link in self.links if link.get("type", "") == link_type)

    def add_item(self, item: EpubItem) -> None:
        """
        Add other item to this document. It will create additional links according to the item type.

        :Args:
          - item: item we want to add defined as instance of EpubItem
        """
        if item.get_type() == ITEM_STYLE:
            self.add_link(href=item.get_name(),
                          rel="stylesheet",
                          type="text/css")

        if item.get_type() == ITEM_SCRIPT:
            self.add_link(src=item.get_name(),
                          type="text/javascript")

    def get_body_content(self) -> bytes:
        """
        Returns content of BODY element for this HTML document. Content will be of type 'bytes'.

        :Returns:
          Returns content of this document.
        """
        try:
            _tree = parse_xhtml(self.get_content())
        except Exception:    # pylint: disable=broad-except
            return b""
        _root = _tree.getroot()
        _body = _tree.find(QName(_root, "body"))

        if _body is not None and len(_body) != 0:
            tree_str = xml_tostring(_body, xml_declaration=False)

            # this is so stupid
            if tree_str.startswith(b"<body>"):
                n = tree_str.rindex(b"</body>")
                return tree_str[6:n]
            return tree_str

        return b""

    def _format_xthml5(self, tree: ElementTree) -> bytes:
        """
        Formats XHTML document to be valid EPUB3.

        :Args:
          - tree: lxml element which represents XHTML document
        """
        root = tree.getroot()
        format_newline(root)
        if self.title:
            tag = f'.//{QName(root, "head")}/{QName(root, "title")}'
            element = tree.find(tag)
            if element is not None:
                element.text = self.title
        root = tree.getroot()
        xml_lang_tag = get_qname("xml", "lang")
        _lang = self.lang or self.book.language
        lang = root.get(xml_lang_tag) or root.get("lang") or _lang
        if lang:
            root.set("lang", lang)
            root.set(get_qname("xml", "lang"), lang)

        svg_tag = get_qname("svg", "svg")
        math_tag = get_qname("math", "math")
        script_tag = get_qname("xhtml", "script")
        properties = {}
        for el in root.iter():
            if el.tag == svg_tag:
                properties["svg"] = None
            elif el.tag == math_tag:
                properties["mathml"] = None
            elif el.tag == script_tag:
                properties["scripted"] = None
        self.properties.extend(properties)
        return xhtml_tostring(tree, doctype=XHTML5_DOCTYPE)

    def format_xthml(self, tree: ElementTree) -> bytes:
        """
        Formats XHTML document to be valid EPUB3.

        :Args:
          - tree: lxml element which represents XHTML document
        """
        return self._format_xthml5(tree)

    def _create_xthml5(self) -> bytes:
        """
        Formats XHTML document to be valid EPUB3.
        """
        template = self.book.get_template(self.TEMPLATE)
        if template is None:
            raise ValueError("Book does not define "
                             f"template {self.TEMPLATE!r}.")

        tree = parse_xhtml(template)
        root = tree.getroot()

        lang = self.lang or self.book.language
        root.set("lang", lang)
        root.set(get_qname("xml", "lang"), lang)
        # create and populate head
        head = etree.SubElement(root, QName(root, "head"))

        for meta in self.metas:
            etree.SubElement(head, QName(head, "meta"), attrib=meta)

        if self.title:
            title = etree.SubElement(head, QName(head, "title"))
            title.text = self.title

        for attrib in self.links:
            if attrib.get("type") == "text/javascript":
                link = etree.SubElement(head,
                                        QName(head, "script"),
                                        attrib=attrib)
                # force <script></script>
                link.text = ""
            else:
                link = etree.SubElement(head,
                                        QName(head, "link"),
                                        attrib=attrib)

        # create and populate body

        body = etree.SubElement(root, QName(root, "body"))
        if self.direction:
            body.set("dir", self.direction)
            root.set("dir", self.direction)

        if self.body:
            try:
                _tree = parse_xhtml(self.body)
                _root = _tree.getroot()
                _body = _tree.find(QName(_root, "body"))
                if _body is not None:
                    body.extend(x for x in _body)
            except Exception:  # pylint: disable=broad-except
                pass
        return xhtml_tostring(tree)

    def create_xthml(self) -> bytes:
        """
        Formats XHTML document to be valid EPUB3.

        :Args:
          - tree: lxml element which represents XHTML document
        """
        return self._create_xthml5()

    @check_attach_book
    def get_content(self, default: str | bytes | None = None, **options) -> bytes:
        """
        Returns content for this document as HTML string. Content will be of type 'bytes'.

        :Args:
          - default: Default value for the content if it is not defined.

        :Returns:
          Returns content of this document.
        """
        if self.tree is not None:
            return self.format_xthml(self.tree)
        if self.content:
            return self.content
        return self.create_xthml()


class EpubCoverHtml(EpubHtml):
    """
    Represents Cover page in the EPUB file.
    """
    TEMPLATE: str = "cover"

    def __init__(
        self, uid: str = "cover", file_name: str = "cover.xhtml", image_name: str = "", title: str = "Cover"
    ) -> None:
        super().__init__(uid=uid, file_name=file_name, title=title)

        self.image_name = image_name
        self.is_linear = False

    def is_chapter(self) -> bool:
        """
        Returns if this document is chapter or not.

        :Returns:
          Returns book value.
        """

        return False

    def _create_xthml5(self) -> bytes:
        """
        Formats XHTML document to be valid EPUB3.
        """
        template = self.book.get_template("cover")
        if template is None:
            raise ValueError("Book does not define "
                             f"template {self.TEMPLATE!r}.")
        tree = parse_xhtml(template)
        root = tree.getroot()

        image = next(root.iter(get_qname("xhtml", "img")))
        image.set("src", self.image_name)
        image.set("alt", self.title)
        return xhtml_tostring(tree)

    def create_xthml(self) -> bytes:
        """
        Formats XHTML document to be valid EPUB3.

        :Args:
          - tree: lxml element which represents XHTML document
        """
        return self._create_xthml5()

    @check_attach_book
    def get_content(self, default: str | bytes | None = None, **options) -> bytes:
        """
        Returns content for cover page as HTML string. Content will be of type 'bytes'.

        :Returns:
          Returns content of this document.
        """
        if self.content:
            return self.content
        return self.create_xthml()


class EpubNav(EpubHtml):
    """
    Represents Navigation Document in the EPUB file.
    """

    def __init__(
        self,
        uid: str | None = "nav",
        file_name: str = "nav.xhtml",
        media_type: str = "",
        title: str = "",
        direction: str | None = None,
    ) -> None:
        super().__init__(uid=uid,
                         file_name=file_name,
                         media_type=media_type or self.MEDIA_TYPE,
                         title=title,
                         direction=direction)

    def is_chapter(self) -> bool:
        """
        Returns if this document is chapter or not.

        :Returns:
          Returns book value.
        """

        return False

    @classmethod
    def _create_ncx(cls) -> ElementTree:
        xmlns = NAMESPACES["XHTML"]
        ns_epub = NAMESPACES["EPUB"]
        root = etree.Element(QName(xmlns, "html"),
                             nsmap={None: xmlns,
                                    "epub": ns_epub})
        return etree.ElementTree(root)

    @check_attach_book
    def get_content(self, default: str | bytes | None = None, **options) -> bytes:
        """ Returns content of the item. Content is usually of type 'bytes'"""
        # just a basic navigation for now
        content = self.book.get_template("nav")
        if content:
            tree = parse_xhtml(content)
            root = tree.getroot()
        else:
            tree = self._create_ncx()
            root = tree.getroot()

        root.set("lang", self.book.language)
        root.attrib[get_qname("xml", "lang")] = self.book.language

        nav_dir_name = os.path.dirname(self.file_name)

        head = etree.SubElement(root, QName(root, "head"))
        title = etree.SubElement(head, QName(head, "title"))
        title.text = self.title or self.book.title

        # for now this just handles css files and ignores others
        for link in self.links:
            attrib = {"href": link.get("href", ""),
                      "rel": "stylesheet",
                      "type": "text/css"}
            etree.SubElement(head, QName(head, "link"), attrib)

        body = etree.SubElement(root, QName(root, "body"))
        if self.direction:
            body.set("dir", self.direction)
        epub_type = get_qname("epub", "type")
        nav = etree.SubElement(
            body,
            QName(body, "nav"),
            {
                epub_type: "toc",
                "id": "id",
                "role": "doc-toc",
            },
        )

        content_title = etree.SubElement(nav, QName(root, "h2"))
        content_title.text = self.title or self.book.title

        def _create_section(node, items):
            ol = etree.SubElement(node, QName(node, "ol"))
            for item in items:
                if isinstance(item, tuple | list):
                    parent, children, *_ = item
                    li = etree.SubElement(ol, QName(ol, "li"))
                    if isinstance(parent, EpubHtml):
                        href = zip_path.relpath(parent.file_name, nav_dir_name)
                        a = etree.SubElement(li, QName(li, "a"), {"href": href})
                    elif isinstance(parent, Section) and parent.href != "":
                        href = zip_path.relpath(parent.href, nav_dir_name)
                        a = etree.SubElement(li, QName(li, "a"), {"href": href})
                    elif isinstance(parent, Link):
                        href = zip_path.relpath(parent.href, nav_dir_name)
                        a = etree.SubElement(li, QName(li, "a"), {"href": href})
                    else:
                        a = etree.SubElement(li, QName(li, "span"))
                    a.text = parent.title
                    if children:
                        _create_section(li, children)

                elif isinstance(item, Link):
                    li = etree.SubElement(ol, QName(ol, "li"))
                    href = zip_path.relpath(item.href, nav_dir_name)
                    a = etree.SubElement(li, QName(li, "a"), {"href": href})
                    a.text = item.title
                elif isinstance(item, EpubHtml):
                    li = etree.SubElement(ol, QName(ol, "li"))
                    href = zip_path.relpath(item.file_name, nav_dir_name)
                    a = etree.SubElement(li, QName(li, "a"), {"href": href})
                    a.text = item.title

        _create_section(nav, self.book.toc)

        # LANDMARKS / GUIDE
        # - http://www.idpf.org/epub/30/spec/epub30-contentdocs.html#sec-xhtml-nav-def-types-landmarks

        if len(self.book.guide) > 0 and options.get("epub3_landmark"):
            # Epub2 guide types do not map completely to epub3 landmark types.
            guide_to_landscape_map = {"notes": "rearnotes", "text": "bodymatter"}

            guide_nav = etree.SubElement(body, QName(body, "nav"), {epub_type: "landmarks"})

            guide_content_title = etree.SubElement(guide_nav, QName(guide_nav, "h2"))
            guide_content_title.text = options.get("landmark_title", "Guide")

            guild_ol = etree.SubElement(guide_nav, QName(guide_nav, "ol"))

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

                li_item = etree.SubElement(guild_ol, QName(guild_ol, "li"))

                guide_type = elem.get("type") or ""
                a_item = etree.SubElement(
                    li_item,
                    QName(li_item, "a"),
                    {
                        epub_type: guide_to_landscape_map.get(guide_type, guide_type),
                        "href": zip_path.relpath(_href, nav_dir_name),
                    },
                )
                a_item.text = _title

        # PAGE-LIST
        if options.get("epub3_pages"):
            inserted_pages = get_pages_for_items(
                [item for item in self.book.get_items_of_type(ITEM_DOCUMENT) if not isinstance(item, EpubNav)]
            )

            if inserted_pages:
                pagelist_nav = etree.SubElement(
                    body,
                    QName(body, "nav"),
                    {
                        epub_type: "page-list",
                        "id": "pages",
                        "hidden": "hidden",
                    },
                )
                pagelist_content_title = etree.SubElement(pagelist_nav, QName(pagelist_nav, "h2"))
                pagelist_content_title.text = options.get("pages_title", "Pages")

                pages_ol = etree.SubElement(pagelist_nav, QName(pagelist_nav, "ol"))

                for filename, pageref, label in inserted_pages:
                    li_item = etree.SubElement(pages_ol, QName(pages_ol, "li"))

                    _href = f"{filename}#{pageref}"
                    _title = label

                    a_item = etree.SubElement(
                        li_item,
                        QName(body, "a"),
                        {
                            "href": zip_path.relpath(_href, nav_dir_name),
                        },
                    )
                    a_item.text = _title

        return xhtml_tostring(tree)


class EpubImage(EpubItem):
    """
    Represents Image in the EPUB file.
    """
    ITEM_TYPE: int = ITEM_IMAGE


class EpubCover(EpubImage):
    """
    Represents Cover image in the EPUB file.
    """
    ITEM_TYPE: int = ITEM_COVER

    def __init__(self, uid: str | None = "cover-img", file_name: str = "", media_type: str = "") -> None:
        super().__init__(uid=uid, file_name=file_name, media_type=media_type)


class EpubFont(EpubItem):
    """
    Represents Font in the EPUB file.
    """
    ITEM_TYPE: int = ITEM_FONT


class EpubSMIL(EpubItem):
    """
    Represents SMIL(Synchronized Multimedia Integration Language) in the EPUB file.
    """
    MEDIA_TYPE: str = "application/smil+xml"
    ITEM_TYPE: int = ITEM_SMIL

    def __init__(self,
                 uid: str | None = None,
                 file_name: str = "",
                 content: str | bytes | None = None) -> None:
        super().__init__(uid=uid,
                         file_name=file_name,
                         media_type=self.MEDIA_TYPE,
                         content=content)
