"""Load the demo's example content into the CONFIGURED database (normally your Supabase development database), owned by
an account that already exists there:

    python -m app.tools.example_data --email you@example.com

It creates two workspaces, "Riverside Campus Green Cover (example)" and "Green Valley Farm (example)", with the same
plants, places, observations, issues, work records, recurring inspection and harvests as the local demo, all built
through the real API as YOU (you are the owner; the field work is recorded under your name too). It creates no other
accounts and stores no passwords: the tool signs in as you on the server side.

Safety: it refuses when ENV is production, when the account does not exist, or when that account already owns example
workspaces (run it once); it shows the target database host and asks before writing unless --yes is given. Remove the
example data by archiving the two workspaces' content, or ask for a removal tool (nothing here deletes data).
"""

from __future__ import annotations

import argparse
import sys
from urllib.parse import urlsplit

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.core.config import get_settings
from app.core.db import get_sessionmaker
from app.core.security import create_access_token
from app.main import create_app
from app.models import Membership, User, Workspace
from app.tools.demo_seed import Person, populate

SUFFIX = " (example)"


def _host(url: str) -> str:
    """Where the data will go, without credentials."""
    parts = urlsplit(url.replace("+psycopg", "").replace("+pysqlite", ""))
    return parts.hostname or parts.path or "(unknown)"


def main(argv: list[str] | None = None, *, confirm=input, settings=None, sessions=None, client=None) -> int:
    """`settings`, `sessions` and `client` are injected by tests; by default the configured database is used."""
    ap = argparse.ArgumentParser(description="Load example workspaces under an existing account.")
    ap.add_argument("--email", required=True, help="the email of an account that already exists (register it first)")
    ap.add_argument("--yes", action="store_true", help="do not ask for confirmation")
    args = ap.parse_args(argv)

    settings = settings or get_settings()
    sessions = sessions or get_sessionmaker()
    if settings.env == "production":
        print("refusing: ENV is production; example data is for development databases only")
        return 2
    with sessions() as db:
        user = db.scalar(select(User).where(func.lower(User.email) == args.email.strip().lower()))
        if user is None:
            print(f"no account with the email {args.email}: register it on the sign-in page first, then run this again")
            return 2
        already = db.scalar(
            select(func.count())
            .select_from(Workspace)
            .join(Membership, Membership.workspace_id == Workspace.id)
            .where(Membership.user_id == user.id, Membership.role == "owner", Workspace.name.like(f"%{SUFFIX}"))
        )
        if already:
            print("this account already owns example workspaces; nothing was added (run it only once)")
            return 2
        name, email, user_id = user.name, user.email, user.id

    target = _host(settings.database_url)
    print(f"About to add two example workspaces owned by {email} to the database at {target}.")
    if not args.yes and confirm("Type yes to continue: ").strip().lower() != "yes":
        print("cancelled; nothing was written")
        return 1

    token, _ = create_access_token(user_id, settings)
    client = client or TestClient(create_app(settings))
    me = Person(client, email, name, token=token)
    campus, farm = populate(me, me, None, suffix=SUFFIX)
    print(f"Done. Workspaces: Riverside Campus Green Cover{SUFFIX} ({campus}), Green Valley Farm{SUFFIX} ({farm}).")
    print("Sign in as yourself and open them from 'Your workspaces'.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
