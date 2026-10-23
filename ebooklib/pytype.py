# pylint: disable=protected-access, c-extension-no-member, missing-module-docstring
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

from typing import BinaryIO, Iterable, Protocol, TypeAlias

from lxml import etree, html

ElementTree: TypeAlias = etree._ElementTree
XmlElement: TypeAlias = etree._Element
XmlElements: TypeAlias = list[etree._Element]
HtmlElement: TypeAlias = html.HtmlElement
HtmlElements: TypeAlias = list[html.HtmlElement]


class Prefix(dict[str, str]):
    ''' A dictionary that can be used to store prefixes '''

    def append(self, data: str) -> None:
        ''' data is a string in the form "name: uri" '''
        name, uri = data.split(":", 1)
        self[name.strip()] = uri.strip()

    def extend(self, iterable: Iterable[str]) -> None:
        ''' data is a string in the form "name: uri" '''
        for data in iterable:
            self.append(data)

    def __iadd__(self, values: Iterable[str]):
        ''' data is a string in the form "name: uri" '''
        self.extend(values)
        return self


# pylint: disable=unnecessary-ellipsis
class FileReader(Protocol):
    ''' Represents a file reader '''

    def read(self, name: str) -> bytes:
        ''' Read file content '''
        ...

    def open(self, name: str) -> BinaryIO:
        ''' Open file '''
        ...

    def close(self) -> None:
        ''' Close file '''
        ...

    def __enter__(self) -> "FileReader":
        ''' Enter context '''
        ...

    def __exit__(self, type_, value, traceback):
        ''' Exit context '''
        ...
