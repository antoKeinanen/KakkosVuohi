from __future__ import annotations

import asyncio
import sys

from pydantic import ValidationError

from .app import configure_logging, run
from .config import Settings
from .db import WrongSecretKey


def main() -> None:
    try:
        settings = Settings()  # type: ignore[call-arg]  # read from the environment
    except ValidationError as exc:
        print("Invalid configuration:", file=sys.stderr)
        for error in exc.errors():
            name = ".".join(str(part) for part in error["loc"]) or "settings"
            print(f"  {name.upper()}: {error['msg']}", file=sys.stderr)
        sys.exit(2)

    configure_logging(settings.log_level)
    try:
        asyncio.run(run(settings))
    except WrongSecretKey as exc:
        print(exc, file=sys.stderr)
        sys.exit(3)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
