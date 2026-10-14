# Publishing PyPDFPresenter

Repository: https://github.com/Hartwich/PyPDFPresenter

## Prepare a release

Review the source, English examples and screenshots. Check both notes layouts,
note editing, dual-display output and embedded video playback.
Run `python software/Build_exe.py` from the project directory.
Keep the entire `dist/PyPDFPresenter` folder together when distributing it.

Commit reviewed changes, push `main`, and create a version tag matching
the application version. Attach the Windows ZIP and matching source ZIP
to a GitHub release. Preserve the AGPL-3.0-only license and dependency notices.

The GitHub Actions workflow builds a Windows artifact after a push.
It does not publish releases automatically.
