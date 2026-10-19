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

# Version of ebook library

from .consts import (
    EXTENSIONS,
    ITEM_AUDIO,
    ITEM_COVER,
    ITEM_DOCUMENT,
    ITEM_FONT,
    ITEM_IMAGE,
    ITEM_NAVIGATION,
    ITEM_SCRIPT,
    ITEM_SMIL,
    ITEM_STYLE,
    ITEM_UNKNOWN,
    ITEM_VECTOR,
    ITEM_VIDEO,
    VERSION,
)

__all__ = [
    'VERSION',
    'EXTENSIONS',
    'ITEM_UNKNOWN',
    'ITEM_IMAGE',
    'ITEM_STYLE',
    'ITEM_SCRIPT',
    'ITEM_NAVIGATION',
    'ITEM_VECTOR',
    'ITEM_FONT',
    'ITEM_VIDEO',
    'ITEM_AUDIO',
    'ITEM_DOCUMENT',
    'ITEM_COVER',
    'ITEM_SMIL'
]
