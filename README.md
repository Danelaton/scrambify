# Scrambify

`scrambify` is a Python command-line transfer tool for short-code peer transfers. It sends short text messages and files between two peers using a human-shareable code and a rendezvous relay.

The project includes end-to-end CLI tests, packaging metadata, standalone binary installers, and release automation.

## Features

- send text or files with a short scrambify code
- run against the built-in HTTP rendezvous relay
- keep CLI, application wiring, protocol logic, and domain models separated
- install as a console script via `scrambify`
- run automated tests for protocol and end-to-end CLI flows

## Installation

### macOS / Linux

```bash
curl -fsSL https://raw.githubusercontent.com/Danelaton/scrambify/main/installs/install.sh | bash
```

### Windows

```powershell
irm https://raw.githubusercontent.com/Danelaton/scrambify/main/installs/install.ps1 | iex
```

### From source (Python 3.10+)

```bash
pip install scrambify
```

For local development:

```bash
python -m pip install -e .[dev]
```

## Quick Start

Start the relay in one terminal:

```text
scrambify relay-server
```

Send text from another terminal:

```text
scrambify send --text "hello"
```

Or send a file:

```text
scrambify send --file .\example.txt
```

Receive from a third terminal using the printed code:

```text
scrambify receive 7-sunrise-meadow
```

Write received output to a chosen path:

```text
scrambify receive 7-sunrise-meadow --output .\downloads\
scrambify receive 7-sunrise-meadow --output .\received-message.txt
```

## Configuration

The CLI reads configuration from environment variables:

- `SCRAMBIFY_RENDEZVOUS_URL`: relay base URL, defaults to `http://127.0.0.1:4000/v1`
- `SCRAMBIFY_TRANSIT_URL`: reserved for future transit transport wiring
- `SCRAMBIFY_CODE_WORD_COUNT`: number of words in generated codes, defaults to `2`

## Development

Run the test suite:

```bash
python -m pytest -q
```

Build a source distribution and wheel:

```bash
python -m build
```

Build standalone binaries:

```bash
python -m pip install -e .[build]
pyinstaller --onefile --name scrambify src/scrambify/cli.py
```

## Repository Layout

- `pyproject.toml`: packaging metadata, extras, pytest configuration, and console entrypoint
- `docs/architecture.md`: current system architecture and delivery status
- `installs/`: shell and PowerShell installers for release binaries
- `.github/workflows/`: release and auto-tag automation
- `src/scrambify/`: application, protocol, and service code
- `src/scrambify/tests/`: unit and end-to-end test coverage