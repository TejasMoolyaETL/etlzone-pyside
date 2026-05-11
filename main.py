"""Project entry point."""

import sys

from app.login_window import run_app


def main() -> None:
    try:
        run_app()
    except KeyboardInterrupt:
        sys.exit(0)


if __name__ == "__main__":
    main()
