# Example presentation

All files are original, English examples covered by the repository's AGPL-3.0-only license.

- `demo.pdf`: six slides, with an embedded video on page 5.
- `demo.notes.json`: editable speaker notes for the same six pages.
- `demo-presenter.pdf`: the same slides with PDF speaker notes on the right.
- `demo.tex`: Beamer source for both layouts and the JSON note text.
- `embed-video.tex`: pdfLaTeX helper that embeds an MP4 using a Screen/Rendition annotation.
- `assets/demo-video.mp4`: original six-second animation; also embedded inside both PDFs.
- `assets/video-poster.png`: the image displayed before playback starts.

Run `python software/presenter.py --demo` from the repository root to try JSON notes.
Run `python software/presenter.py examples/demo-presenter.pdf` to try PDF notes.
On page 5, press **V** or click the video area. Enable **Auto-play videos** to
start playback when entering this page. Playback works in PyPDFPresenter;
other PDF viewers may show only the poster, depending on their media support.
The MP4 file is included for rebuilding; playback uses the copy inside the PDF.

## Rebuild by hand

Install a TeX distribution with pdfLaTeX, Beamer and Latin Modern.
Open `demo.tex` and choose the setting near the top:

```tex
\presenternotesfalse % Slides only
```

For slides with speaker notes on the right, change that line to:

```tex
\presenternotestrue % Include PDF speaker notes
```

Keep only one of these setting lines active. In your TeX editor, select
pdfLaTeX and compile twice, or use a terminal in the `examples` directory:

```sh
pdflatex -interaction=nonstopmode -halt-on-error -no-shell-escape demo.tex
pdflatex -interaction=nonstopmode -halt-on-error -no-shell-escape demo.tex
```

Both settings write `demo.pdf`. To keep both layouts, rename the PDF made
with `\presenternotestrue` to `demo-presenter.pdf`, then switch back to
`\presenternotesfalse` and compile again.

Keep `embed-video.tex` and the `assets` directory beside `demo.tex` when
compiling. The video is embedded automatically in both layouts.
PDF notes come from the `\note{...}` blocks in `demo.tex`.
The JSON notes are a separate editable file: update `demo.notes.json`
by hand or use **Edit notes** in PyPDFPresenter when you change their text.
