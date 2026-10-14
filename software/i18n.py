"""Small UI catalog: German for German locales, English everywhere else."""
from PySide6.QtCore import QLocale

LANGUAGE = 'en'
EN = {
    'PDF öffnen': 'Open PDF', 'Automatisch': 'Automatic', 'Notizen rechts': 'Notes on the right',
    'Notizen links': 'Notes on the left', 'Keine Notizen': 'No PDF notes',
    'Präsentation starten · F5': 'Start presentation · F5', 'Präsentation stoppen · F5': 'Stop presentation · F5',
    'Schwarz · B': 'Black screen · B', 'Folie zeigen · B': 'Show slide · B', 'JSON laden': 'Load JSON',
    'PDF-Notizen': 'PDF notes', 'Text / JSON': 'Text / JSON', 'Unter den Notizen': 'Below the notes',
    'Unter der aktuellen Folie': 'Below the current slide', 'Unten: nächste Folie und ihre Notizen': 'Bottom: next slide and notes',
    'Keine PDF geladen': 'No PDF loaded', 'Laserpointer · L': 'Laser pointer · L',
    'Automatisch Abspielen': 'Auto-play videos', 'Präsentation über „PDF öffnen“ laden': 'Load a presentation with "Open PDF"',
    'AKTUELLE FOLIE': 'CURRENT SLIDE', 'NOTIZEN': 'SPEAKER NOTES',
    'NÄCHSTE PDF-SEITE / EINBLENDUNG': 'NEXT PDF PAGE / BUILD',
    'NOTIZEN DER NÄCHSTEN PDF-SEITE': 'NOTES FOR THE NEXT PDF PAGE',
    '← Zurück': '← Previous', 'Weiter →': 'Next →', 'Timer starten': 'Start timer',
    'Timer pausieren': 'Pause timer', 'Timer fortsetzen': 'Resume timer', 'Zurücksetzen': 'Reset',
    'PDF-Seite:': 'PDF page:', 'Video abspielen · V': 'Play video · V', 'Video pausieren · V': 'Pause video · V',
    'Video zurücksetzen': 'Reset video', 'Vorschau:': 'Preview:', 'Schrift:': 'Font size:',
    'Keine JSON geladen': 'No JSON loaded', 'Notizen bearbeiten': 'Edit notes', 'Notizen anlegen': 'Create notes',
    'Bearbeitung beenden': 'Finish editing', 'Keine Textnotizen für die nächste PDF-Seite.': 'No text notes for the next PDF page.',
    'Eine JSON über „JSON laden“ öffnen.\nZum Ändern „Notizen bearbeiten“ wählen.': 'Open JSON with "Load JSON".\nChoose "Edit notes" to make changes.',
    'Zum Ändern „Notizen bearbeiten“ wählen.': 'Choose "Edit notes" to make changes.',
    'Über „Notizen anlegen“ eine JSON erstellen oder oben „JSON laden“ wählen.': 'Use "Create notes" to create JSON, or choose "Load JSON" above.',
    'Notizdatei anlegen': 'Create notes file', 'Sprechtexte laden': 'Load speaker notes',
    'Präsentation öffnen': 'Open presentation', 'Externe Sprechtexte laden': 'Load external speaker notes',
    '--speaker-notes benötigt eine PDF-Datei.': '--speaker-notes requires a PDF file.',
    'Die PDF enthält keine Seiten.': 'The PDF contains no pages.',
    'Passwortgeschützte PDFs werden noch nicht unterstützt.': 'Password-protected PDFs are not supported yet.',
    'PDF kann nicht geöffnet werden': 'Cannot open PDF', 'Rendering fehlgeschlagen': 'Rendering failed',
    'Videofehler': 'Video error', 'Diese Seite enthält kein unterstütztes Video.': 'This page contains no supported video.',
    'JSON kann nicht geladen werden': 'Cannot load JSON', 'Notizen können nicht gespeichert werden': 'Cannot save notes',
    'Erwartet wird ein JSON-Objekt mit version: 1.': 'Expected a JSON object with version: 1.',
    'Das Feld notes muss PDF-Seitennummern auf Sprechtexte abbilden, z. B. {"1": "Einleitung"}.': 'The notes field must map PDF page numbers to text, e.g. {"1": "Introduction"}.',
    'Jeder Notizeintrag braucht eine positive Seitennummer und einen Text.': 'Each note requires a positive page number and a string.',
    'Doppelte Seitennummern, z. B. 1 und 01, sind nicht zulässig.': 'Duplicate page numbers, such as 1 and 01, are not allowed.',
    'font_size muss eine ganze Zahl zwischen 10 und 64 sein.': 'font_size must be an integer between 10 and 64.',
    'Seite {page} / {total}': 'Page {page} / {total}', 'Bildschirm {number}: {name}': 'Display {number}: {name}',
    ' · Speichern ausstehend': ' · Saving pending', ' · {count} Einträge außerhalb dieser PDF': ' · {count} entries outside this PDF',
    'PyPDFPresenter - Publikum': 'PyPDFPresenter - Audience',
    'PyPDFPresenter - Referentenansicht': 'PyPDFPresenter - Presenter view',
}

def select_language(requested='auto', locale_name=None):
    global LANGUAGE
    locale_name = locale_name or QLocale.system().name()
    LANGUAGE = ('de' if locale_name.lower().startswith('de') else 'en') if requested == 'auto' else requested
    if LANGUAGE not in ('de', 'en'):
        raise ValueError('Supported languages: auto, de, en')
    return LANGUAGE

def tr(text):
    return text if LANGUAGE == 'de' else EN.get(text, text)

select_language()
