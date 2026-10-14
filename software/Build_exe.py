"""Build PyPDFPresenter with the current Python environment.

Install requirements.txt first. Run: python software/Build_exe.py
"""
import importlib.util
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]

def main():
    if importlib.util.find_spec('PyInstaller') is None:
        print('PyInstaller is missing. Run: python -m pip install -r requirements.txt', file=sys.stderr)
        return 1
    result = subprocess.run([sys.executable, '-m', 'PyInstaller', '--noconfirm', str(ROOT / 'PyPDFPresenter.spec')], cwd=ROOT)
    if result.returncode:
        return result.returncode
    print(f'Built application: {ROOT / "dist" / "PyPDFPresenter"}')
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
