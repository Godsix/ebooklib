"""
Created on Tue Jun 18 11:24:12 2024

@author: David
"""

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
