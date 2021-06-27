## Befehle

| Befehl | Description |
|----------|----------|
| ```/start``` | Zeigt Wilkommensnachricht an
| ```/plz POSTLEITZAHL``` | Legt Postleitzahl fest
| ```/birthdate DD.MM.YYYY``` | Legt Geburtsdatum fest
| ```/exclude IMPFSTOFF``` | Fügt Impfstoff der Auschlussliste hinzu
| ```/include IMPFSTOFF``` | Entfernt Impfstoff von der Auschlussliste
| ```/vaccines``` | Zeit abhängig vom Alter verfügbare Impfstoffe an
| ```/status``` | Zeigt den Namen des Impfzentrums, den dort aktuell verwendeten Impfstoff und ob es freie Impftermine an

## Benötigte Software:
* Python 3.8 oder höher
* beautifulsoup4
* python-telegram-bot
* PyYAML
* requests
