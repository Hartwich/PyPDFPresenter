# PyInstaller build: run from the repository root.
from pathlib import Path
import sys
sys.path.insert(0, str(Path('.deps').resolve()))
import pymupdf

native = Path(pymupdf.__file__).parent / 'mupdfcpp64.dll'
extra_binaries = [(str(native), 'pymupdf')] if native.exists() else []
a = Analysis(['software/presenter.py'], pathex=['software', '.deps'], binaries=extra_binaries,
             datas=[('software/ui-assets', 'ui-assets'), ('examples', 'examples'), ('LICENSE', '.'), ('THIRD_PARTY_NOTICES.md', '.')],
             hiddenimports=[], hookspath=[], hooksconfig={}, runtime_hooks=[],
             excludes=['pandas', 'scipy', 'matplotlib', 'numpy', 'cv2', 'tkinter', 'IPython'],
             noarchive=False, optimize=0)
# Qt uses the Windows system ICU API. Do not bundle an unrelated MSYS2 DLL.
a.binaries = [entry for entry in a.binaries if entry[0].replace('\\', '/').split('/')[-1].lower() != 'icuuc.dll']
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='PyPDFPresenter', debug=False,
          bootloader_ignore_signals=False, strip=False, upx=False, console=False,
          disable_windowed_traceback=False, argv_emulation=False, target_arch=None,
          codesign_identity=None, entitlements_file=None)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, upx_exclude=[], name='PyPDFPresenter')
