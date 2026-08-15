from __future__ import annotations

import argparse

from bifrostnms.tasks.email import send_email


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Queue a BifrostNMS test email.")
    parser.add_argument("recipient", help="Recipient email address")
    parser.add_argument(
        "--subject",
        default="BifrostNMS test email",
        help="Email subject",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    result = send_email.delay(
        to=[args.recipient],
        subject=args.subject,
        text="This is a test email from BifrostNMS.",
        html="<p>This is a test email from <strong>BifrostNMS</strong>.</p>",
    )
    print(f"Queued test email task {result.id} for {args.recipient}")


if __name__ == "__main__":
    main()
