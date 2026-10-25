"""Create a product-local secret without displaying it or overwriting a file."""

import secrets
from pathlib import Path


def main() -> None:
    destination = Path(__file__).resolve().parents[1] / ".env"
    password = secrets.token_urlsafe(32)
    content = (
        f"DEPLOY_BUDDY_DB_PASSWORD={password}\n"
        f"DATABASE_URL=postgresql+psycopg://deploy_buddy:{password}"
        "@127.0.0.1:55432/deploy_buddy_local\n"
    )
    try:
        with destination.open("x", encoding="utf-8") as stream:
            stream.write(content)
    except FileExistsError:
        raise SystemExit("Local .env already exists; left unchanged.") from None
    print("Created ignored product/.env. No secret values were printed.")


if __name__ == "__main__":
    main()
