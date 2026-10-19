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

"""
Constants, XML namespaces and templates shared by the EPUB reader and writer.
"""

# Version of EPUB library
VERSION: tuple[int, int, int] = (0, 21, 0)

# LIST OF POSSIBLE ITEMS
ITEM_UNKNOWN = 0
ITEM_IMAGE = 1
ITEM_STYLE = 2
ITEM_SCRIPT = 3
ITEM_NAVIGATION = 4
ITEM_VECTOR = 5
ITEM_FONT = 6
ITEM_VIDEO = 7
ITEM_AUDIO = 8
ITEM_DOCUMENT = 9
ITEM_COVER = 10
ITEM_SMIL = 11

# EXTENSION MAPPER
EXTENSIONS: dict[int, list[str]] = {
    ITEM_IMAGE: [".jpg", ".jpeg", ".gif", ".tiff", ".tif", ".png"],
    ITEM_STYLE: [".css"],
    ITEM_VECTOR: [".svg"],
    ITEM_FONT: [".otf", ".woff", ".woff2", ".ttf"],
    ITEM_SCRIPT: [".js"],
    ITEM_NAVIGATION: [".ncx"],
    ITEM_VIDEO: [".mov", ".mp4", ".avi", ".webm"],
    ITEM_AUDIO: [".mp3", ".ogg"],
    ITEM_COVER: [".jpg", ".jpeg", ".png"],
    ITEM_SMIL: [".smil"],
}

# Formats that are already compressed. They are stored in the ZIP container
# without deflating them again.
COMPRESSED = frozenset({
    # image
    ".jpg", ".jpeg", ".jpe", ".jfif",
    ".png", ".gif", ".webp", ".avif",
    ".heic", ".heif", ".jp2", ".j2k", ".jxl",

    # font
    ".woff", ".woff2",

    # audio
    ".mp3", ".m4a", ".aac",
    ".ogg", ".oga", ".opus", ".flac",

    # video
    ".mp4", ".m4v", ".mov", ".avi",
    ".webm", ".mkv",
})

NAMESPACES: dict[str, str] = {
    "XML": "http://www.w3.org/XML/1998/namespace",
    "EPUB": "http://www.idpf.org/2007/ops",
    "DAISY": "http://www.daisy.org/z3986/2005/ncx/",
    "OPF": "http://www.idpf.org/2007/opf",
    "CONTAINERNS": "urn:oasis:names:tc:opendocument:xmlns:container",
    "DC": "http://purl.org/dc/elements/1.1/",
    "XHTML": "http://www.w3.org/1999/xhtml",
}

# XML Templates

CONTAINER_PATH = "META-INF/container.xml"

CONTAINER_XML = """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="%(folder_name)s/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
"""

NCX_XML = (
    b'<?xml version="1.0" encoding="UTF-8"?>\n'
    b'<!DOCTYPE ncx PUBLIC "-//NISO//DTD ncx 2005-1//EN" "http://www.daisy.org/z3986/2005/ncx-2005-1.dtd">\n'
    b'<ncx version="2005-1" xmlns="http://www.daisy.org/z3986/2005/ncx/" />'
)

NAV_XML = (
    b'<?xml version="1.0" encoding="UTF-8"?>\n'
    b'<!DOCTYPE html>\n'
    b'<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops"/>'
)

CHAPTER_XML = (
    b'<?xml version="1.0" encoding="UTF-8"?>\n'
    b'<!DOCTYPE html>\n'
    b'<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops"></html>'
)

COVER_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" lang="en" xml:lang="en">
  <head>
    <style>
      body { margin: 0em; padding: 0em; }
      img { max-width: 100%; max-height: 100%; }
    </style>
  </head>
  <body>
    <img src="" alt="" />
  </body>
</html>"""


IMAGE_MEDIA_TYPES: list[str] = [
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/svg+xml",
]

FONT_MEDIA_TYPES: list[str] = [
    "application/vnd.ms-opentype",
    "application/x-font-opentype",
    "application/x-font-ttf",
    "application/font-woff",
    "application/font-sfnt",
    "font/collection",
    "font/otf",
    "font/ttf",
    "font/woff",
    "font/woff2",
]
