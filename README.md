# Scrambify

> Get things from one computer to another, safely.

## What does it do?

Scrambify helps you move a file, a folder, or a short message from one computer to another.

In plain English:

1. On computer A, you run one command.
2. Scrambify gives you a short code like `42-ocean-breeze`.
3. On computer B, you type that code.
4. The transfer happens securely.

No accounts needed. No cloud storage needed. No copy-pasting giant links. No complicated setup.

If you can open a terminal and type one command, you can use Scrambify.

## Why people use it

- send a photo from your laptop to your desktop
- move a PDF from your work machine to your home machine
- send a small project folder to another computer nearby
- share a short secret note or password without email or chat

## How it works

Think of Scrambify like a secure one-time meeting point for two computers.

- the sender creates a one-time code
- the receiver types that code
- both computers use the same code to set up encryption
- the relay server helps them find each other
- the file or message is transferred end-to-end encrypted

The relay helps with the handshake, but it does not get your plaintext file contents.

### Visual example

Computer A:

```text
$ scrambify send --file photo.jpg
Scrambify code is: 42-ocean-breeze
On the other computer, run: scrambify receive 42-ocean-breeze
Waiting for receiver...
```

Computer B:

```text
$ scrambify receive 42-ocean-breeze
Receiving file: photo.jpg (2.4 MB)
Saved to: ./photo.jpg
```

That is the whole idea:

- one short code
- one sender
- one receiver
- one secure transfer

## Installation

Choose the option that matches your computer.

### macOS / Linux

```bash
curl -fsSL https://raw.githubusercontent.com/Danelaton/scrambify/main/installs/install.sh | bash
```

After that finishes, open a new terminal and run:

```bash
scrambify --help
```

### Windows (PowerShell)

Open **PowerShell** and run:

```powershell
irm https://raw.githubusercontent.com/Danelaton/scrambify/main/installs/install.ps1 | iex
```

Then open a new PowerShell window and run:

```powershell
scrambify --help
```

### From source (requires Python 3.10+)

If you already use Python:

```bash
pip install scrambify
```

Then verify it:

```bash
scrambify --help
```

## Two-minute quick start

This is the fastest way to try Scrambify.

### Step 1: Start a relay server

In one terminal, run:

```text
$ scrambify relay-server --port 4000
```

Leave that terminal open.

### Step 2: Send from computer A

On the computer that has the file:

```text
$ scrambify send --file ./document.pdf
Scrambify code is: 7-sunrise-meadow
On the other computer, run: scrambify receive 7-sunrise-meadow
Waiting for receiver...
Connected! Sending 2.4 MB...
File sent successfully.
```

### Step 3: Receive on computer B

Open a terminal in the folder where you want the file to land, then run:

```text
$ scrambify receive 7-sunrise-meadow
Connecting...
Receiving file: document.pdf (2.4 MB)
Saved to: ./document.pdf
```

Important: by default, Scrambify saves received files into your **current directory**.

So if you are inside `C:\Users\You\Downloads` when you run `scrambify receive ...`, the file is saved there.

## Usage

## Send a file

```text
$ scrambify send --file ./document.pdf
Scrambify code is: 7-sunrise-meadow
On the other computer, run: scrambify receive 7-sunrise-meadow
Waiting for receiver...
Connected! Sending 2.4 MB...
File sent successfully.
```

Use this for normal files such as:

- PDFs
- photos
- ZIP files
- videos
- text files

## Send a folder

If you want to send a folder today, zip it first, then send the ZIP file:

```text
$ zip -r my-project.zip ./my-project
$ scrambify send --file ./my-project.zip
Scrambify code is: 15-crystal-harbor
```

That keeps the workflow simple and works everywhere the current CLI is available.

## Send text

```text
$ scrambify send --text "the wifi password is hunter2"
Scrambify code is: 88-velvet-canyon
```

This is handy for:

- short notes
- passwords
- temporary secrets
- one-off messages between your own devices

## Receive

```text
$ scrambify receive 7-sunrise-meadow
Connecting...
Receiving file: document.pdf (2.4 MB)
Saved to: ./document.pdf
```

By default, the received file is saved into the directory where you ran the command.

### Change the destination folder

If you want to save into a different folder, use `--output-dir`:

```text
$ scrambify receive 7-sunrise-meadow --output-dir ./downloads
Connecting...
Receiving file: document.pdf (2.4 MB)
Saved to: ./downloads/document.pdf
```

You can also use the older `--output` flag as an alias if you already have scripts that use it.

## Start your own relay server

```text
$ scrambify relay-server --port 4000
```

The relay server helps both computers find each other.

By default, Scrambify uses:

```text
http://127.0.0.1:4000/v1
```

That works great for local testing on one machine or on a network where both computers can reach the same relay.

If your two computers are on different networks, run the relay on a server both can reach, then point Scrambify at it.

## Configuration

Scrambify can be configured with environment variables.

### `SCRAMBIFY_RENDEZVOUS_URL`

The relay server address.

Default:

```text
http://127.0.0.1:4000/v1
```

### `SCRAMBIFY_CODE_WORDS`

How many words appear in the short transfer code.

Default:

```text
2
```

Depending on your version or environment, you may also see `SCRAMBIFY_CODE_WORD_COUNT` used for the same idea.

## Security

- the code is used to derive shared cryptographic material between the two computers
- all transferred data is encrypted end-to-end
- the relay helps the peers meet, but should not see plaintext payloads
- codes are one-time-use and meant for a single transfer session
- the project uses modern cryptographic building blocks from the NaCl family

In simple terms: the relay is the meeting place, not the vault.

## Using as a Python library

You can also use Scrambify from Python:

```python
from scrambify.application import ScrambifyApp, AppConfig

app = ScrambifyApp(AppConfig.default())

# Send text
result = app.send_text("hello world")
print(result)

# Receive
result = app.receive("42-ocean-breeze")
print(result)
```

This is useful if you want to build your own automation around the transfer flow.

## Development

Clone the project:

```bash
git clone https://github.com/Danelaton/scrambify
cd scrambify
```

Install development dependencies:

```bash
pip install -e ".[dev]"
```

Run the test suite:

```bash
python -m pytest
```

Project layout:

- `src/scrambify/` - application and protocol code
- `src/scrambify/tests/` - unit and end-to-end tests
- `installs/` - install scripts
- `docs/` - project documentation

## Troubleshooting

### “Command not found”

Close and reopen your terminal after installing, then try:

```text
scrambify --help
```

### The receiver is waiting forever

Check these things:

- both computers are using the exact same code
- both computers can reach the same relay server
- any firewall is not blocking the relay port

### The file saved in the wrong place

Scrambify saves into your current working directory unless you set `--output-dir`.

Before running `scrambify receive ...`, open a terminal in the folder where you want the file saved.

## License

MIT