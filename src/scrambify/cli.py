from __future__ import annotations

import argparse

from scrambify.application import build_app
from scrambify.protocol.relay import run_relay_server


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="scrambify", description="Transfer files and short messages using shared codes.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    send_parser = subparsers.add_parser("send", help="Prepare a transfer offer.")
    send_group = send_parser.add_mutually_exclusive_group(required=True)
    send_group.add_argument("--text", help="Short text payload to send.")
    send_group.add_argument("--file", help="File payload to send.")
    send_parser.add_argument("--timeout", type=float, default=60.0, help="Maximum seconds to wait for the peer.")
    send_parser.add_argument("--poll-interval", type=float, default=0.25, help="Seconds between relay polls.")

    receive_parser = subparsers.add_parser("receive", help="Prepare to receive a transfer.")
    receive_parser.add_argument("code", help="Shared scrambify code.")
    receive_parser.add_argument(
        "--output-dir",
        "--output",
        dest="output_dir",
        help="Directory to save received files or text messages to. Defaults to the current working directory.",
    )
    receive_parser.add_argument("--timeout", type=float, default=60.0, help="Maximum seconds to wait for the peer.")
    receive_parser.add_argument("--poll-interval", type=float, default=0.25, help="Seconds between relay polls.")

    relay_parser = subparsers.add_parser("relay-server", help="Run the rendezvous relay server.")
    relay_parser.add_argument("--host", default="127.0.0.1", help="Interface to bind the relay server to.")
    relay_parser.add_argument("--port", type=int, default=4000, help="Port to bind the relay server to.")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    def report(message: str) -> None:
        print(message, flush=True)

    if args.command == "relay-server":
        run_relay_server(host=args.host, port=args.port)
        return 0

    app = build_app()

    if args.command == "send":
        if args.text is not None:
            print(
                app.send_text(
                    args.text,
                    reporter=report,
                    timeout_seconds=args.timeout,
                    poll_interval_seconds=args.poll_interval,
                )
            )
            return 0
        print(
            app.send_file(
                args.file,
                reporter=report,
                timeout_seconds=args.timeout,
                poll_interval_seconds=args.poll_interval,
            )
        )
        return 0

    if args.command == "receive":
        print(
            app.receive(
                args.code,
                output_dir=args.output_dir,
                reporter=report,
                timeout_seconds=args.timeout,
                poll_interval_seconds=args.poll_interval,
            )
        )
        return 0

    parser.error(f"unsupported command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())