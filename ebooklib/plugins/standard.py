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
from lxml import etree

from ..epub import EpubImage
from ..utils import parse_html, xml_tostring
from .base import BasePlugin

# TODO:
#   - should also look for the _required_ elements
# http://www.w3.org/html/wg/drafts/html/master/tabular-data.html#the-table-element

ATTRIBUTES_GLOBAL = [
    "accesskey",
    "class",
    "contenteditable",
    "contextmenu",
    "dir",
    "draggable",
    "dropzone",
    "hidden",
    "id",
    "inert",
    "itemid",
    "itemprop",
    "itemref",
    "itemscope",
    "itemtype",
    "lang",
    "spellcheck",
    "style",
    "tabindex",
    "title",
    "translate",
    "epub:type",
]

# Remove <u> for now from here
DEPRECATED_TAGS = [
    "acronym",
    "applet",
    "basefont",
    "big",
    "center",
    "dir",
    "font",
    "frame",
    "frameset",
    "isindex",
    "noframes",
    "s",
    "strike",
    "tt",
]


def leave_only(item, *tags: str):
    # Accept both the historical ``leave_only(item, ["href"])`` form and the
    # newer ``leave_only(item, "href")`` form.
    if len(tags) == 1 and isinstance(tags[0], (list, tuple, set, frozenset)):
        tags = set(tags[0])
    else:
        tags = set(tags)
    for key in list(item.attrib):
        if key not in tags:
            del item.attrib[key]

def leave_except(item, *tags):
    for key in tags:
        item.attrib.pop(key, None)


HEAD_ATTRIBUTES = {
    "base": ["href", "target"],
    "link": ["href", "crossorigin", "rel", "media", "hreflang", "type", "sizes"],
    "meta": ["name", "http-equiv", "content", "charset"],
    "script": ["src", "type", "charset", "async", "defer", "crossorigin"],
    "source": ["src", "type", "media"],
    "style": ["media", "type", "scoped"],
}

BODY_ATTRIBUTES = {
    "a": ["href", "target", "download", "rel", "hreflang", "type"],
    "area": ["alt", "coords", "shape", "href", "target", "download", "rel", "hreflang", "type"],
    "audio": [
        "src",
        "crossorigin",
        "preload",
        "autoplay",
        "mediagroup",
        "loop",
        "muted",
        "controls",
    ],
    "blockquote": ["cite"],
    "button": [
        "autofocus",
        "disabled",
        "form",
        "formaction",
        "formenctype",
        "formmethod",
        "formnovalidate",
        "formtarget",
        "name",
        "type",
        "value",
        "menu",
    ],
    "canvas": ["width", "height"],
    "del": ["cite", "datetime"],
    "details": ["open"],
    "embed": ["src", "type", "width", "height"],
    "fieldset": ["disabled", "form", "name"],
    "form": [
        "accept-charset",
        "action",
        "autocomplete",
        "enctype",
        "method",
        "name",
        "novalidate",
        "target",
    ],
    "iframe": [
        "src",
        "srcdoc",
        "name",
        "sandbox",
        "seamless",
        "allowfullscreen",
        "width",
        "height"
    ],
    "img": [
        "alt",
        "src",
        "crossorigin",
        "usemap",
        "ismap",
        "width",
        "height",
    ],
    "input": [
        "accept",
        "alt",
        "autocomplete",
        "autofocus",
        "checked",
        "dirname",
        "disabled",
        "form",
        "formaction",
        "formenctype",
        "formmethod",
        "formnovalidate",
        "formtarget",
        "height",
        "inputmode",
        "list",
        "max",
        "maxlength",
        "min",
        "multiple",
        "name",
        "pattern",
        "placeholder",
        "readonly",
        "required",
        "size",
        "src",
        "steptype",
        "value",
        "width",
    ],
    "ins": ["cite", "datetime"],
    "keygen": [
        "autofocus",
        "challenge",
        "disabled",
        "form",
        "keytype",
        "name",
    ],
    "label": ["for", "form"],
    "map": ["name"],
    "menu": ["type", "label"],
    "object": [
        "data",
        "type",
        "typemustmatch",
        "name",
        "usemap",
        "form",
        "width",
        "height",
    ],
    "ol": ["reversed", "start", "type"],
    "optgroup": ["disabled", "label"],
    "option": ["disabled", "selected", "label", "value"],
    "output": ["for", "form", "name"],
    "param": ["name", "value"],
    "progress": ["value", "max"],
    "q": ["cite"],
    "select": [
        "autofocus",
        "disabled",
        "form",
        "multiple",
        "name",
        "required",
        "size",
    ],
    "table": ["border", "sortable"],
    "td": ["colspan", "rowspan", "headers"],
    "textarea": [
        "autocomplete",
        "autofocus",
        "cols",
        "dirname",
        "disabled",
        "form",
        "inputmode",
        "maxlength",
        "name",
        "placeholder",
        "readonly",
        "required",
        "rows",
        "wrap",
    ],
    "col": ["span"],
    "colgroup": ["span"],
    "th": ["colspan", "rowspan", "headers", "scope", "abbr", "sorted"],

    "time": ["datetime"],
    "track": ["kind", "src", "srclang", "label", "default"],
    "video": [
        "src",
        "crossorigin",
        "poster",
        "preload",
        "autoplay",
        "mediagroup",
        "loop",
        "muted",
        "controls",
        "width",
        "height",
    ],
}


class SyntaxPlugin(BasePlugin):
    NAME = "Check HTML syntax"

    def html_before_write(self, book, chapter):
        try:
            tree = parse_html(chapter.content)
        except Exception:  # pylint: disable=broad-exception-caught
            return

        # delete deprecated tags
        # i should really have a list of allowed tags
        for tag in DEPRECATED_TAGS:
            etree.strip_tags(tree.getroottree(), tag)

        head = tree.find("head")

        if head is not None:
            for child in head:
                match child.tag:
                    case "base" | "link" | "script" | "source" | "style":
                        leave_only(child,
                                   *ATTRIBUTES_GLOBAL,
                                   *HEAD_ATTRIBUTES[child.tag])
                    case "title":
                        if not child.text:
                            head.remove(child)
                    case "meta":
                        leave_only(child,
                                   *ATTRIBUTES_GLOBAL,
                                   *HEAD_ATTRIBUTES[child.tag])
                        # just remove for now, but really should not be like this
                        head.remove(child)
                    case _:
                        leave_only(child, *ATTRIBUTES_GLOBAL)

        body = tree.find("body")

        if body is not None and len(body) != 0:
            for child in body.iter():
                # it is not
                # <a class="indexterm" href="ch05.html#ix_epub:trigger_element">

                match child.tag:
                    case ("a" | "area" | "audio" | "blockquote" | "button"
                          | "canvas" | "del" | "details" | "embed" | "fieldset"
                          | "form" | "iframe" | "input" | "ins" | "keygen"
                          | "label" | "map" | "menu" | "object" | "ol"
                          | "optgroup" | "option" | "output" | "param"
                          | "progress" | "q" | "select" | "td" | "textarea"
                          | "col" | "colgroup" | "th"
                          | "time" | "track" | "video"):
                        leave_only(child,
                                   *ATTRIBUTES_GLOBAL,
                                   *BODY_ATTRIBUTES[child.tag])
                    case "img":
                        _src = child.get("src", "")
                        if _src.lower().startswith(("http://", "https://")):
                            if "remote-resources" not in chapter.properties:
                                chapter.properties.append("remote-resources")
                                # THIS DOES NOT WORK, ONLY VIDEO AND AUDIO FILES CAN BE REMOTE RESOURCES
                                # THAT MEANS I SHOULD ALSO CATCH <SOURCE TAG
                                book.add_item(EpubImage(file_name=_src))
                        leave_only(child,
                                   *ATTRIBUTES_GLOBAL,
                                   *BODY_ATTRIBUTES[child.tag])
                    case "table":
                        if child.get("border", None):
                            if child.get("border") == "0":
                                child.set("border", "")

                        if child.get("summary", None):
                            _caption = etree.Element("caption")
                            _caption.text = child.get("summary")
                            child.insert(0, _caption)

                            # add it as caption
                            del child.attrib["summary"]
                        leave_only(child,
                                   *ATTRIBUTES_GLOBAL,
                                   *BODY_ATTRIBUTES[child.tag])
                    case "dl":
                        _d = child.find("dd")
                        if _d is not None and len(_d) == 0:
                            pass

                            # http://html5doctor.com/the-dl-element/
                            # should be like this really
                            # some of the elements can be missing
                            # dl
                            #   dt
                            #   dd
                            #   dt
                            #   dd
                    case "svg":
                        # We need to add property "svg" in case we have embeded svg file
                        if "svg" not in chapter.properties:
                            chapter.properties.append("svg")
                        leave_except(child, "viewbox", "preserveaspectratio")
                    case _:
                        leave_only(child, *ATTRIBUTES_GLOBAL)

        chapter.content = xml_tostring(tree)
        return chapter.content
