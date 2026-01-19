# Trakt-to-Serializd

Migrate Trakt watch history to Serializd with original watch dates preserved.

## Install

```bash
pip install git+https://github.com/VanillaChief/trakt-to-serializd@feature/diary-with-dates
```

## Usage

```bash
trakt_to_serializd migrate
```

Follow the prompts to log into both services. The tool fetches your Trakt history (including rewatches) and logs each episode to Serializd's diary with the original date.

Other commands:
- `refresh-cache` — update local cache from Serializd
- `cleanup-duplicates` — remove duplicate diary entries  
- `clean` — delete stored credentials

## Credentials

Tokens are stored locally (not passwords):
- Linux: `~/.local/share/trakt_to_serializd/`
- Windows: `%localappdata%\trakt_to_serializd\`

## Development

```bash
poetry install --with=dev
poetry run trakt_to_serializd migrate
```

---

AI-assisted development (Claude, Anthropic). See commit trailers.
