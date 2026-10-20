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

"""EPUB Open Container Format (OCF)."""

from lxml.etree import QName  # pylint: disable=E0611

from .base import FileObject
from .consts import CONTAINER_PATH, CONTAINER_XML, NAMESPACES
from .utils import join_path, parse_xml


class OCFContainer(FileObject):
    """The ``META-INF/container.xml`` file of an EPUB book."""
    TEMPLATE = CONTAINER_XML
    MEDIA_TYPE = "application/oebps-package+xml"
    NAMESPACE = NAMESPACES["CONTAINERNS"]

    def __init__(self) -> None:
        super().__init__(CONTAINER_PATH)
        self.content: str | None = None

    @classmethod
    def get_full_path(cls, content: str | bytes) -> str:
        """Return full path from the container."""
        tree = parse_xml(content)
        tag = QName(cls.NAMESPACE, "rootfile")
        path = f".//{tag}[@media-type='{cls.MEDIA_TYPE}']"
        for rootfile in tree.findall(path):
            if opf_path := rootfile.get("full-path"):
                return opf_path
        return ""

    @classmethod
    def get_content(cls, *path: str) -> str:
        """Return the content of the container."""
        return cls.TEMPLATE % {"opf_path": join_path(*path)}
