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

import posixpath

from lxml.etree import QName  # pylint: disable=E0611

from .base import FileObject
from .consts import CONTAINER_PATH, CONTAINER_XML, NAMESPACES
from .utils import parse_xml


class OCFContainer(FileObject):
    """The ``META-INF/container.xml`` file of an EPUB book."""

    def __init__(self) -> None:
        super().__init__(CONTAINER_PATH)
        self.content: str = CONTAINER_XML

    def get_full_path(self) -> str:
        """Return full path from the container."""
        tree = parse_xml(self.content)
        tag = QName(NAMESPACES["CONTAINERNS"], "rootfile")
        media_type = "application/oebps-package+xml"
        for rootfile in tree.findall(f".//{tag}[@media-type='{media_type}']"):
            opf_path = rootfile.get("full-path") or ""
            return posixpath.dirname(opf_path)
