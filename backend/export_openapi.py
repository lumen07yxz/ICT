"""Export the current FastAPI contract for frontend and AgentArts review."""

import json
from pathlib import Path
import sys


BACKEND_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BACKEND_DIR))

from app.main import app  # noqa: E402


def main() -> None:
    output_file = BACKEND_DIR / "openapi.json"
    output_file.write_text(
        json.dumps(app.openapi(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"OpenAPI schema written to {output_file}")


if __name__ == "__main__":
    main()
