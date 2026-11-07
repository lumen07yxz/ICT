"""PyInstaller entrypoint for the Windows desktop application."""

from ict_desktop.__main__ import main


if __name__ == "__main__":
    raise SystemExit(main())
