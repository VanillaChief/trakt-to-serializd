# Trakt-to-Serializd

Migrate your watched shows from Trakt to Serializd!

## Features

- One-command migration - just run `migrate` and follow the prompts
- Preserves original watch dates in Serializd diary
- Handles rewatches (creates multiple diary entries)
- Prevents duplicates with smart caching
- Support for private Trakt accounts

## Usage

```bash
trakt_to_serializd migrate
```

That's it! The tool will:

1. Log you into Trakt and Serializd
2. Fetch your existing Serializd diary to prevent duplicates
3. Migrate all episodes with their original watch dates
4. Handle rewatches automatically

### Other Commands

```bash
# Refresh cache from Serializd (if you added entries manually)
trakt_to_serializd refresh-cache

# Find and remove duplicate diary entries
trakt_to_serializd cleanup-duplicates

# Remove saved credentials
trakt_to_serializd clean
```

## Stored Credentials

**Paths:**
- Windows: `%localappdata%\trakt_to_serializd\credentials.json`
- Linux: `~/.local/share/trakt_to_serializd/credentials.json`

Your credentials (access tokens, not passwords) are saved locally.
Run `trakt_to_serializd clean` to remove them.

## Installation

```bash
# Recommended: use pipx for isolated install
pipx install git+https://github.com/VanillaChief/trakt-to-serializd@feature/diary-with-dates

# Or with pip
pip install git+https://github.com/VanillaChief/trakt-to-serializd@feature/diary-with-dates
```

Then just run `trakt_to_serializd migrate`.

## Development

```bash
git clone https://github.com/VanillaChief/trakt-to-serializd
cd trakt-to-serializd
poetry install --with=dev
pre-commit install

# Run during development:
poetry run trakt_to_serializd migrate
```

## AI Attribution

This tool was developed with AI assistance (Claude Opus 4.5, Anthropic).
AI-assisted commits include the `Co-authored-by: Claude <noreply@anthropic.com>` trailer.
