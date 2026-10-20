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

"""EpubBook - in-memory representation of an EPUB book."""

import uuid
from collections import OrderedDict
from collections.abc import Iterator
from typing import Any

from .consts import CHAPTER_XML, COVER_XML, NAMESPACES, NAV_XML, NCX_XML
from .items import EpubCover, EpubCoverHtml, EpubHtml, EpubImage, EpubItem
from .pytype import Prefix
from .opf import OPF
from .utils import guess_type


def set_optional_attr(obj: Any, name: str, value: str | None):
    """Set an attribute if value is not None, otherwise remove it."""
    if value:
        setattr(obj, name, value)
    elif hasattr(obj, name):
        delattr(obj, name)


class EpubBook:
    '''Represents an EPUB book in memory.'''
    EPUB_VERSION: str = "3.0"
    IDENTIFIER_ID: str = "id"
    FOLDER_NAME: str = "EPUB"

    def __init__(self) -> None:
        self.reset()

        # we should have options here
    @property
    def version(self) -> str:
        """Returns the EPUB version of this book."""
        return getattr(self, "_version", self.EPUB_VERSION)

    @version.setter
    def version(self, value: str | None):
        """Sets the EPUB version of this book."""
        set_optional_attr(self, "_version", value)

    @property
    def identifier_id(self) -> str:
        """Returns the identifier id of this book."""
        return getattr(self, "_identifier_id", self.IDENTIFIER_ID)

    @identifier_id.setter
    def identifier_id(self, value: str | None):
        """Sets the identifier id of this book."""
        set_optional_attr(self, "_identifier_id", value)

    @property
    def package_dir(self) -> str:
        """Returns the package directory of this book. """
        return getattr(self, "_package_dir", self.FOLDER_NAME)

    @package_dir.setter
    def package_dir(self, value: str | None):
        """Sets the package directory of this book."""
        set_optional_attr(self, "_package_dir", value)

    def reset(self) -> None:
        """Initialises all needed variables to default values"""
        self.opf: OPF = OPF()
        # EPUB version as read from the package document (e.g. "3.0").
        # Set by EpubReader when loading an existing book.
        self.version: str | None = None
        self.identifier_id: str | None = None
        self.package_dir: str | None = None

        self.metadata: dict[str | None, dict[str, list[Any]]] = {}
        self.items: list[EpubItem] = []
        self.spine: list[Any] = []
        self.guide: list[dict[str, Any]] = []
        self.pages: list[Any] = []
        self.toc: Any = []
        self.bindings: list[dict[str, Any]] = []

        self._id_html = 0
        self._id_image = 0
        self._id_static = 0
        self._id_creator = 0

        self.title = ""
        self.language = "en"
        self.direction: str | None = None

        self.templates: dict[str, bytes] = {
            "ncx": NCX_XML,
            "nav": NAV_XML,
            "chapter": CHAPTER_XML,
            "cover": COVER_XML,
        }

        # default to using a randomly-unique identifier if one is not specified manually
        self.set_identifier(str(uuid.uuid4()))

        # custom prefixes and namespaces to be set to the content.opf doc
        self.prefixes: Prefix = Prefix()
        self.namespaces: dict[str, str] = {}

    @property
    def prefixes(self) -> Prefix:
        """
        :Returns:
          - prefixes: Custom prefixes and namespaces to be set to the content.opf doc
        """
        return self._prefixes

    @prefixes.setter
    def prefixes(self, value: Prefix | list) -> None:
        """
        :Args:
          - value: Custom prefixes and namespaces to be set to the content.opf doc
        """
        if isinstance(value, list):
            _prefixes = Prefix()
            _prefixes.extend(value)
            self._prefixes = _prefixes
        else:
            self._prefixes = value

    def set_identifier(self, uid: str) -> None:
        """
        Sets unique id for this epub

        :Args:
          - uid: Value of unique identifier for this book
        """

        self.uid = uid

        self.set_unique_metadata("DC", "identifier", self.uid, {"id": self.IDENTIFIER_ID})

    def set_title(self, title: str) -> None:
        """
        Set title. You can set multiple titles.

        :Args:
          - title: Title value
        """

        self.title = title

        self.add_metadata("DC", "title", self.title)

    def set_language(self, lang: str) -> None:
        """
        Set language for this epub. You can set multiple languages. Specific items in the book can have
        different language settings.

        :Args:
          - lang: Language code
        """

        self.language = lang

        self.add_metadata("DC", "language", lang)

    def set_direction(self, direction: str | None) -> None:
        """
        :Args:
          - direction: Options are "ltr", "rtl" and "default"
        """

        self.direction = direction

    def set_cover(self, file_name: str, content: bytes, create_page: bool = True) -> None:
        """
        Set cover and create cover document if needed.

        :Args:
          - file_name: file name of the cover page
          - content: Content for the cover image
          - create_page: Should cover page be defined. Defined as bool value (optional). Default value is True.
        """

        # as it is now, it can only be called once
        cover = EpubCover(file_name=file_name)
        cover.content = content
        self.add_item(cover)

        if create_page:
            cover_page = EpubCoverHtml(image_name=file_name)
            self.add_item(cover_page)

        self.add_metadata("OPF", "meta", "", OrderedDict([("name", "cover"), ("content", cover.get_id())]))

    def add_author(
        self, author: str, file_as: str | None = None, role: str | None = None, uid: str | None = None
    ) -> None:
        """Add author for this document"""

        if uid is None:
            # ids must be unique within the document, so only the first author can use
            # the plain "creator" id; subsequent ones get a counter suffix
            uid = "creator" if self._id_creator == 0 else f"creator_{self._id_creator}"
            self._id_creator += 1

        self.add_metadata("DC", "creator", author, {"id": uid})

        if file_as:
            self.add_metadata("OPF", "meta", file_as,
                              {"refines": f"#{uid}",
                               "property": "file-as",
                               "scheme": "marc:relators"})
        if role:
            self.add_metadata("OPF", "meta", role,
                              {"refines": f"#{uid}",
                               "property": "role",
                               "scheme": "marc:relators"})

    def _get_metadata(self, namespace: str | None) -> dict:
        """Add metadata"""
        ns = NAMESPACES.get(namespace.upper() if namespace else namespace, namespace)
        ns_map = self.metadata.setdefault(ns, {})
        return ns_map

    def add_metadata(self, namespace: str | None, name: str, value: str, others: dict | None = None) -> None:
        """Add metadata"""
        ns_map = self._get_metadata(namespace)
        ns_map.setdefault(name, []).append((value, others))

    def get_metadata(self, namespace: str | None, name: str) -> list:
        """Retrieve metadata"""
        ns_map = self._get_metadata(namespace)
        return ns_map.get(name, [])

    def set_unique_metadata(self, namespace: str | None, name: str, value: str, others: dict | None = None) -> None:
        """Add metadata if metadata with this identifier does not already exist, otherwise update existing metadata."""
        ns_map = self._get_metadata(namespace)
        ns_map[name] = [(value, others)]

    def add_item(self, item: EpubItem) -> EpubItem:
        """
        Add additional item to the book. If not defined, media type and chapter id will be defined
        for the item.

        :Args:
          - item: Item instance
        """
        if item.media_type == "":
            # guess_type returns (type, encoding). The encoding ("gzip" for a
            # ".svgz" file, say) is not a media type and must not be used as one.
            media_type = guess_type(item.get_name().lower())[0]
            item.media_type = media_type or "application/octet-stream"

        if not item.get_id():
            # make chapter_, image_ and static_ configurable
            if isinstance(item, EpubHtml):
                item.id = f"chapter_{self._id_html}"
                self._id_html += 1
                # If there's a page list, append it to the book's page list
                self.pages += item.pages
            elif isinstance(item, EpubImage):
                item.id = f"image_{self._id_image}"
                self._id_image += 1
            else:
                item.id = f"static_{self._id_static}"
                self._id_static += 1

        item.book = self
        self.items.append(item)

        return item

    def get_item_with_id(self, uid: str) -> EpubItem | None:
        """
        Returns item for defined UID.

        >>> book.get_item_with_id('image_001')

        :Args:
          - uid: UID for the item

        :Returns:
          Returns item object. Returns None if nothing was found.
        """
        for item in self.get_items():
            if item.id == uid:
                return item

        return None

    def get_item_with_href(self, href: str) -> EpubItem | None:
        """
        Returns item for defined HREF.

        >>> book.get_item_with_href('EPUB/document.xhtml')

        :Args:
          - href: HREF for the item we are searching for

        :Returns:
          Returns item object. Returns None if nothing was found.
        """
        for item in self.get_items():
            if item.get_name() == href:
                return item

        return None

    def get_items(self) -> Iterator[EpubItem]:
        """
        Returns all items attached to this book.

        :Returns:
          Returns all items as tuple.
        """
        return (item for item in self.items)

    def get_items_of_type(self, item_type: int) -> Iterator[EpubItem]:
        """
        Returns all items of specified type.

        >>> book.get_items_of_type(epub.ITEM_IMAGE)

        :Args:
          - item_type: Type for items we are searching for

        :Returns:
          Returns found items as tuple.
        """
        return (item for item in self.items if item.get_type() == item_type)

    def get_items_of_media_type(self, media_type: str) -> Iterator[EpubItem]:
        """
        Returns all items of specified media type.

        :Args:
          - media_type: Media type for items we are searching for

        :Returns:
          Returns found items as tuple.
        """
        return (item for item in self.items if item.media_type == media_type)

    def set_template(self, name: str, value: bytes) -> None:
        """
        Defines templates which are used to generate certain types of pages. When defining new value for the template
        we have to use content of type 'bytes'.

        At the moment we use these templates:
          - ncx
          - nav
          - chapter
          - cover

        :Args:
          - name: Name for the template
          - value: Content for the template
        """

        self.templates[name] = value

    def get_template(self, name: str) -> bytes | None:
        """
        Returns value for the template.

        :Args:
          - name: template name

        :Returns:
          Value of the template.
        """
        return self.templates.get(name)

    def add_prefix(self, name: str, uri: str) -> None:
        """
        Appends custom prefix to be added to the content.opf document

        >>> epub_book.add_prefix('bkterms', 'http://booktype.org/')

        :Args:
          - name: namespave name
          - uri: URI for the namespace
        """

        self.prefixes[name] = uri
