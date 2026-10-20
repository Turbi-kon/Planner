> **100% vibe-coded.** This project was written entirely with AI: a human brought the ideas and feature requests, and a neural network turned them into Python.

[Русский](README.md) | [English](README_EN.md)

# List — a planner with a better memory than mine

Because “I thought your birthday was tomorrow” is a terrible birthday algorithm.

**Python + PySide6 + SQLite. Always-on-top reminders, Telegram, and a small birthday greeting factory.**

## What this responsible little sheet can do

- Keep your entries: add, edit, search, and filter. Your plans finally have a table, though that hasn't made them any easier.
- Remind you in a separate window above everything else. Yes, even that “just one more video.”
- Send messages to Telegram. A real `sendMessage` this time, not a philosophical placeholder.
- Repeat birthdays every year and calculate ages with correct Russian word endings: **21 год, 23 года, 25 лет**. Even turning 111 won't break the grammar.
- Announce adulthood at 18. The “Adult Life” DLC installs without our involvement.
- Add a festive touch to milestone birthdays. Every five years from twenty onward gets a small ceremonial release.
- Delete old regular entries every six months. Birthdays survive the cleanup: cake is a long-term investment.
- Switch themes: gray by default, white for daylight enthusiasts, and dark for late-night commits.

## Automatic birthday greeter

Mark an entry as a birthday, enter a name and an optional birth year, then choose a style: warm, funny, or programmer.
Automation takes it from there: **the greeting is assembled from phrase lists right when the Telegram message is sent**.
No need to write it in advance or keep it in a separate field.


Five blocks with four options each give you **1,024 combinations per style**. No online neural networks: just local phrase lists and the desire to wish someone well without another copy-pasted “happiness and good health.”

A regular entry in Telegram:

```text
Buy milk
20.10.2026 18:30
Two cartons. And bread, since I'm already out.
```

A birthday in Telegram:

```text
Alexey
20.10.2026 10:00
25 years old — milestone birthday
On behalf of the Department of Good Commits, congratulations on your new version release!

May your coffee be delicious, your coworkers kind, and your meetings short.
```

If the birth year is unknown, the age line disappears. The person keeps their mystery; the program keeps its dignity.
Birthday notes remain a reminder for you and are not included in the festive Telegram message.

**On your PC, you get a regular reminder with the title, date, and notes. No birthday greeting mixed in.**
Let the bot handle the toasts and the desktop window do its job.

The examples above are translated for this README; the application interface and its built-in greeting phrases are in Russian.

## Running from source

Requires Python 3.10+; the build was tested with Python 3.12 x64. On Windows, you can open **run.bat**.


Linux/macOS: use `.venv/bin/python`. The Windows EXE is built on Windows; other operating systems need their own build.

## Where the database lives

Usually at `%LOCALAPPDATA%\ListPlanner\ListPlanner\planner.sqlite3`.
SQLite comes with Python; this modest calendar doesn't need a separate database server.

The bot token is stored in the local database without encryption. **Don't commit the database or any tokens**: `.gitignore` already excludes SQLite files, `.env`, the virtual environment, and build output.
To move your entries, close the app and copy the database to the other PC. Copying just the EXE gives the new PC a fresh, empty database.

The app must be running to send reminders. Closing its window minimizes it to the tray when a tray is available; use the tray icon's menu to quit completely. Powered-off computers are still allowed some peace.

## Sanity check

```powershell
python -m unittest discover -s tests -v
```

Tests cover the database and migrations, Russian word endings, milestone birthdays, year transitions, Telegram, recurring reminders, and greeting assembly.
HTTP is mocked in tests: real people don't receive “test test test” just so we can earn a green check mark.

For detailed reminder behavior, data storage, migrations, and building, see the [guide](docs/USAGE.md) (in Russian).

## What's inside

| Part | Job description |
| --- | --- |
| Python | Executes our good intentions |
| PySide6 | Windows, themes, the tray, and a convincing “time to remember” |
| SQLite | Remembers your entries after the app closes |
| PyInstaller | Lets you hand your friends a single EXE |
| `birthdays.py` | Makes sure 21 gets “год” and 25 gets “лет” |
| `greetings.py` | Mixes greetings without producing random word salad |
