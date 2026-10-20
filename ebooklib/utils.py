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
# pylint: disable=I1101
import mimetypes
import posixpath
import re
from io import BytesIO
from os import PathLike
from pathlib import Path

from lxml import etree
from lxml.etree import QName, XMLParser, XMLSyntaxError  # pylint: disable=E0611
from lxml.html import HTMLParser, XHTMLParser, document_fromstring, html_to_xhtml, xhtml_to_html

from .consts import NAMESPACES
from .pytype import ElementTree, HtmlElement, XmlElement

LXML_DECLARATION = re.compile(b"<\\?xml[^>]+?\\?>")
PATTERN_NEWLINE = re.compile('[\r\n]+')


# Parsers are stateful and not thread-safe, so create a fresh one per parse
# instead of sharing module-level instances between threads.
def _xml_parser() -> XMLParser:
    return XMLParser(recover=True, resolve_entities=False)


def _html_parser() -> HTMLParser:
    return HTMLParser(encoding="utf-8")


def _xhtml_parser() -> XHTMLParser:
    return XHTMLParser(encoding="utf-8")


mimetypes.add_type("application/xhtml+xml", ".xhtml")
mimetypes.add_type("font/ttf", ".ttf")
mimetypes.add_type("font/otf", ".otf")
mimetypes.add_type("font/collection", ".ttc")
mimetypes.add_type("font/woff", ".woff")
mimetypes.add_type("font/woff2", ".woff2")


def _xml_decl_sub(m: re.Match[bytes]):
    return m[0].replace(b"'", b'"')


def format_xml_declaration(content: bytes) -> bytes:
    '''Fix XML declaration.'''
    return LXML_DECLARATION.sub(_xml_decl_sub, content, 1)


def get_qname(text: str | QName | XmlElement | None,
              tag: str | None = None,
              namespaces: dict[str, str] | None = None) -> str:
    '''Resolve tag name or attr name to QName.

    ``text`` can be a prefix (``"opf"``), a prefixed name (``"opf:item"``),
    an existing namespace URI (``"http://..."``), a Clark name
    (``"{uri}local"``), or an element used as the namespace source.
    '''
    if isinstance(text, str):
        if not text:
            return str(QName(None, tag))
        if not namespaces:
            namespaces = NAMESPACES
        if (pos := text.find(":")) >= 0:
            prefix = text[:pos]
            localname = text[pos + 1:]
            if ns := namespaces.get(prefix.upper()):
                return str(QName(QName(ns, localname), tag))
        elif namespace := namespaces.get(text.upper()):
            return str(QName(namespace, tag))
    return str(QName(text, tag))


def debug(obj: object) -> None:
    import pprint

    pp = pprint.PrettyPrinter(indent=4)
    pp.pprint(obj)


def format_uri(s: str) -> str:
    '''Fix URI'''
    return s.replace('\\', '/')


def join_path(*paths: str) -> str:
    '''Join paths and fix slashes.'''
    ipath = (format_uri(x) for x in paths)
    return posixpath.normpath(posixpath.join(*ipath))


def format_newline(node: ElementTree | XmlElement) -> None:
    '''Fix newlines in text and tail.'''
    for child in node.iter():
        if child.tail:
            child.tail = PATTERN_NEWLINE.sub('\n', child.tail)
        if child.text:
            child.text = PATTERN_NEWLINE.sub('\n', child.text)


def _etree_parse(value: PathLike | str | bytes, parser=None) -> ElementTree:
    '''Parse XML file.'''
    if isinstance(value, PathLike):
        obj = value
    elif isinstance(value, bytes):
        obj = BytesIO(value)
    elif isinstance(value, str):
        obj = BytesIO(value.encode("utf-8"))
    else:
        raise TypeError(f"Invalid type for path: {type(value).__name__}")
    tree = etree.parse(obj, parser=parser)
    return tree


def parse_xml(value: PathLike | str | bytes) -> ElementTree:
    '''Parse XML file.'''
    return _etree_parse(value, parser=_xml_parser())


def parse_xhtml(value: PathLike | str | bytes) -> ElementTree:
    '''Parse XHTML file or Parse HTML file and convert it to XHTML.'''
    try:
        tree = _etree_parse(value, parser=_xhtml_parser())
    except XMLSyntaxError:
        tree = _etree_parse(value, parser=_html_parser())
    html_to_xhtml(tree)
    return tree


def parse_xhtml_to_html(value: PathLike | str | bytes) -> ElementTree:
    '''Parse HTML file or content.'''
    tree = parse_xhtml(value)
    xhtml_to_html(tree)
    return tree


def parse_html(value: PathLike | str | bytes) -> HtmlElement:
    '''Parse HTML file or content.'''
    parser = _html_parser()
    if isinstance(value, PathLike):
        tree = etree.parse(value, parser=parser)
        root = tree.getroot()
    else:
        root = document_fromstring(value, parser=parser)
    return root


# Backwards-compatible aliases for the pre-0.22 public helpers.
parse_string = parse_xml
parse_html_string = parse_html


def xml_tostring(node, **kwargs) -> bytes:
    '''Convert XML node to string.'''
    kwargs.setdefault('pretty_print', True)
    kwargs.setdefault('encoding', 'UTF-8')
    kwargs.setdefault('xml_declaration', True)
    text = etree.tostring(node, **kwargs)
    return format_xml_declaration(text)


def xhtml_tostring(node, **kwargs) -> bytes:
    '''Convert XHTML node to string.'''
    kwargs.setdefault('pretty_print', True)
    kwargs.setdefault('encoding', 'UTF-8')
    kwargs.setdefault('xml_declaration', True)
    if hasattr(node, 'docinfo') and node.docinfo.doctype:
        kwargs.setdefault('doctype', node.docinfo.doctype)
    else:
        kwargs.setdefault('doctype', '<!DOCTYPE html>')
    html_to_xhtml(node)
    text = etree.tostring(node, **kwargs)
    return format_xml_declaration(text)


def guess_type(extenstion: str) -> tuple[str | None, str | None]:
    '''Guess MIME type for file extension.'''
    return mimetypes.guess_type(extenstion)


def create_pagebreak(pageref: str,
                     label: str | None = None,
                     html: bool = True) -> XmlElement | str:
    """Create a pagebreak element."""
    ns = NAMESPACES["EPUB"]
    attrib = {
        QName(ns, "type"): "pagebreak",
        "title": pageref,
        "id": pageref,
    }

    pageref_elem = etree.Element("span", attrib=attrib, nsmap={"epub": ns})

    if label:
        pageref_elem.text = label

    if html:
        return etree.tostring(pageref_elem, encoding="unicode")

    return pageref_elem


def get_headers(element: XmlElement) -> str | None:
    """Get the text of the first header element in an XHTML document."""
    for n in range(1, 7):
        header = element.find(QName(NAMESPACES["XHTML"], f"h{n}"))
        if header is not None:
            text = header.text_content().strip()
            if text:
                return text
    return None


def get_pages(item) -> list[tuple[str, str, str]]:
    """Get the pages from an item."""
    body = parse_xhtml(item.get_body_content())
    pages = []

    keys = [QName(NAMESPACES["EPUB"], "type"), "epub:type"]

    for elem in (x for x in body.iter() if any(k in x.attrib for k in keys)):
        if (uid := elem.get("id")) is not None:
            _text = uid

            if elem.text is not None and (text := elem.text.strip()):
                _text = text
            elif label := elem.get("aria-label"):
                _text = label
            elif headers := get_headers(elem):
                _text = headers

            pages.append((item.get_name(), uid, _text))
    return pages


def get_pages_for_items(items) -> list[tuple[str, str, str]]:
    """Get the pages from a list of items."""
    pages_from_docs = [get_pages(item) for item in items]
    return [item for pages in pages_from_docs for item in pages]


# pylint: disable=unnecessary-pass
class Directory:
    """Reads files from an unpacked EPUB directory, using the same interface as ZipFile."""

    def __init__(self, directory: str | PathLike) -> None:
        self.directory: Path = Path(directory).resolve()

    def _path(self, name: str) -> Path:
        path = (self.directory / name).resolve()
        if not path.is_relative_to(self.directory):
            e = f"Invalid path, escapes the source directory: {name!r}"
            raise OSError(e)
        return path

    def read(self, name: str) -> bytes:
        """Read the file ``name`` relative to the EPUB directory and return its bytes.

        ``name`` typically comes from OPF manifest ``href`` attributes, which are
        attacker-controlled and URL-decoded, so the resolved path must stay inside the
        EPUB directory.

        :param name: Path of the file, relative to the EPUB directory.
        :returns: Raw content of the file.
        :raises OSError: If ``name`` escapes the EPUB directory (path traversal,
            e.g. ``"../../secret"``), or if the file cannot be read.
        """
        # Guard against path traversal (e.g. "../../secret") escaping the EPUB directory.
        return self._path(name).read_bytes()

    def open(self, name: str, mode="r"):
        '''
        Open the file ``name`` relative to the EPUB directory and return a file-like object.
        '''
        return self._path(name).open(mode)

    def close(self) -> None:
        """
        No-op: Directory is always open.
        """
        pass

    def __enter__(self) -> "Directory":
        ''' Enter context '''
        return self

    def __exit__(self, type, value, traceback):
        ''' Exit context '''
        self.close()
