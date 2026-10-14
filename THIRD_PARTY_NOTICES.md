# Third-party software

PyPDFPresenter is original application code licensed under AGPL-3.0-only.
The demo and screenshots were created for this repository and are distributed under the same license.

- **PyMuPDF / MuPDF**: Artifex Software, AGPL or a separate commercial license.
  This project uses the open-source distribution.
  [License information](https://pymupdf.readthedocs.io/en/latest/about.html#license-and-copyright).
- **PySide6 / Qt**: The Qt Company and contributors, LGPL/GPL or a separate
  commercial license, depending on the component.
  [Qt for Python licensing](https://doc.qt.io/qtforpython-6/licenses.html).
  The bundled `qtbase_de.qm` contains Qt's German translations.
- **FFmpeg**: Qt Multimedia's playback backend may bundle FFmpeg libraries.
  Their license depends on the selected build.
  [FFmpeg licensing](https://ffmpeg.org/legal.html).
- **ReportLab and Pillow**: development tools for the demo and screenshot
  generation. They are not required to run the application.
  [ReportLab](https://www.reportlab.com/), [Pillow](https://python-pillow.org/).

Keep the applicable dependency notices with distributed binaries. The
PyInstaller build includes this notice and the application license; upstream
libraries retain their own copyrights and licenses.
