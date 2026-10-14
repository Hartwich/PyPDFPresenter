@echo off
cd /d "%~dp0"
if exist "dist\PyPDFPresenter\PyPDFPresenter.exe" (
  start "" "dist\PyPDFPresenter\PyPDFPresenter.exe"
) else (
  python software/presenter.py
)
