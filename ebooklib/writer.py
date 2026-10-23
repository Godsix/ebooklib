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
from datetime import datetime, timezone
from pathlib import Path
from typing import IO, Any, Protocol, TypeAlias
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile, ZipInfo

from .book import EpubBook
from .consts import (
    COMPRESSED,
    CONTAINER_PATH,
)
from .items import EpubHtml
from .ocf import OCFContainer
from .utils import join_path

logger = logging.getLogger(__name__)


class _WritableFile(Protocol):
    """Minimal structural interface required by zipfile.ZipFile for writing."""

    def write(self, data: bytes, /) -> object: ...

    def seek(self, offset: int, whence: int = ..., /) -> object: ...

    def tell(self) -> int: ...


# Anything accepted by zipfile.ZipFile: a path or a writable binary file-like object.
EpubTarget: TypeAlias = str | os.PathLike[str] | _WritableFile


def datetime_to_date_time(dt: datetime) -> tuple[int, int, int, int, int, int]:
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

    def zipinfo(self, name: str) -> ZipInfo:
        info = ZipInfo(name, self.options["date_time"])
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

        self.options: dict = self.get_default_options()
        self.options.update(options or {})
        self.options["date_time"] = datetime_to_date_time(
            self.options["mtime"]
        )

    def process(self) -> None:
        # should cache this html parsing so we don't do it for every plugin
        plugins = self.options.get("plugins", [])
        if not plugins:
            return
        name = "before_write"
        funcs = [y for x in plugins if (y := getattr(x, name, None))]
        if funcs:
            for func in funcs:
                func(self.book)
        name = "html_before_write"
        funcs = [y for x in plugins if (y := getattr(x, name, None))]
        if funcs:
            items = self.book.get_items()
            for item in (x for x in items if isinstance(x, EpubHtml)):
                for func in funcs:
                    func(self.book, item)

    def write(self) -> None:
        # zipfile stubs expect IO[bytes], but any object with write/seek/tell works
        with ZipFile(self.file_name,
                     "w",
                     ZIP_DEFLATED,
                     compresslevel=self.options["compresslevel"]) as self.out:  # pylint: disable=W0201
            self.out.writestr("mimetype",
                              "application/epub+zip",
                              compress_type=ZIP_STORED)
            opf = self.book.opf
            opf_path = join_path(self.book.package_dir, opf.file_name)
            self.out.writestr(self.zipinfo(CONTAINER_PATH),
                              OCFContainer.get_content(opf_path))
            self.out.writestr(self.zipinfo(opf_path),
                              opf.get_content(self.book, **self.options))
            for item in self.book.get_items():
                if item.manifest:
                    filename = join_path(self.book.package_dir, item.file_name)
                else:
                    filename = item.file_name
                self.out.writestr(self.zipinfo(filename),
                                  item.get_content(**self.options))


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
        if epub.options.get("raise_exceptions"):
            raise e
        return False

    return True
