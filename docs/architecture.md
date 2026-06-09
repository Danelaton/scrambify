# Scrambify Architecture

## Purpose

This project provides a modern Python implementation of a short-code-based transfer workflow. The codebase supports relay-backed end-to-end transfers, automated tests, packaging metadata, standalone binary installers, and release automation without changing the layered structure.

## Design Principles

- prefer small, composable modules over a monolithic client
- separate control-plane coordination from data-plane transfer
- keep domain models independent of network and CLI concerns
- make default configuration explicit and overridable
- preserve a simple synchronous CLI while keeping protocol internals evolvable

## Current Runtime Model

The tool currently coordinates one active transport path:

1. sender creates a session and receives a human-readable code
2. receiver enters the code to join the same rendezvous scope
3. both peers derive shared session material from the code exchange
4. sender publishes an encrypted transfer offer
5. receiver accepts the offer
6. sender publishes encrypted payload chunks through the relay mailbox
7. receiver reconstructs and verifies the payload

A future transit channel is still planned for bulk payload transport, but the current implementation intentionally keeps everything relay-backed so the end-to-end flow remains easy to test and reason about.

## Package Layout

### `scrambify.cli`

Owns argument parsing, help text, and command dispatch. It remains thin and delegates behavior to the application layer.

### `scrambify.application`

Builds the application object, centralizes dependency wiring, manages polling and timeout behavior, and exposes send/receive use cases for the CLI.

### `scrambify.config`

Stores typed configuration such as relay URLs and code generation settings. Environment-variable support already flows through this module.

### `scrambify.domain`

Contains protocol-neutral types such as:

- `ScrambifyCode`
- `TransferOffer`
- `TransferKind`
- `SessionRole`

### `scrambify.services`

Coordinates session lifecycle behavior, including offer publication, acceptance, payload transmission, and payload reconstruction.

### `scrambify.protocol`

Holds concrete protocol primitives and transport adapters:

- scrambify-code generation helpers
- PAKE-style key derivation helpers
- mailbox message models and helpers
- relay-backed rendezvous transport over HTTP

## Key Decisions

### Layered package over a single script

Chosen to keep transport, protocol, and CLI concerns isolated as the tool grows.

### `src/` layout over top-level imports

Chosen to align with modern packaging expectations and avoid accidental imports from the working tree.

### Real relay integration before packaging polish

Chosen so Step 6 could validate the user-facing workflow through true cross-process tests rather than mocks alone.

### Packaging via `pyproject.toml`

Chosen to keep installation, console entrypoints, dev extras, and test configuration in one standard location.

## Relay Shape

The current rendezvous relay uses the Python standard library:

- `scrambify relay-server` runs a threaded HTTP server on `http://127.0.0.1:4000/v1`
- `POST /v1/nameplates/{nameplate}/open` creates or reuses the mailbox for a nameplate
- `POST /v1/mailboxes/{mailbox_id}/messages` appends an envelope with optimistic sequence checking
- `GET /v1/mailboxes/{mailbox_id}/messages?after_sequence=N` reads new envelopes

This makes the transport adapter replaceable while still allowing separate CLI processes to coordinate through a real relay.

## Testing Strategy

Step 6 adds coverage across three levels:

1. protocol and session orchestration tests
2. relay integration tests against the threaded HTTP server
3. CLI end-to-end tests that spawn independent Python processes

The project is configured so `python -m pytest -q` discovers tests from `src/scrambify/tests`.

## Packaging and Release Readiness

The project now includes:

- console entrypoint metadata for `scrambify`
- development extras for `pytest`, `build`, and `pyinstaller`
- wheel-compatible build requirements
- richer package metadata and classifiers
- standalone release installers and workflows
- ignore rules for generated Python and build artifacts

## Planned Next Steps

- move bulk payloads onto a dedicated transit transport
- add retry and resumable transfer behavior
- tighten peer confirmation semantics before payload transmission
- broaden coverage for timeout and interrupted-peer failure cases