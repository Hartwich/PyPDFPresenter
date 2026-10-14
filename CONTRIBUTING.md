# Contributing

Small, focused pull requests are welcome. Include the problem, intended
behavior and the checks you ran. For UI changes, attach a screenshot made
from the included demo rather than a personal presentation.

1. Install `requirements.txt` in a virtual environment.
2. Make a branch for the change.
3. Run the app with the included demo in both PDF and JSON notes modes.
4. Check navigation, note editing and saving, both UI languages, and video playback.
5. For UI changes, attach screenshots with the included example presentation.

Visible strings belong in `software/i18n.py`; German is selected for German system
locales and English is the fallback. Keep JSON page numbering and automatic
saving backward-compatible. New features should preserve a predictable
presentation workflow and leave audience content separate from notes.

By contributing, you agree that your contribution is licensed under AGPL-3.0-only.
