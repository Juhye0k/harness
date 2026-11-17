"""Offline tester approval. Never approves users through the public API."""

import argparse
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth_models import User
from app.db import get_engine


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["pending", "approve"])
    parser.add_argument("--user-id", type=UUID)
    args = parser.parse_args()
    with Session(get_engine()) as s, s.begin():
        if args.command == "pending":
            for user in s.scalars(select(User).where(User.state == "pending")):
                print(user.id)
        else:
            user = s.scalar(select(User).where(User.id == args.user_id).with_for_update())
            if not user or user.state != "pending":
                parser.error("A pending user ID is required")
            user.state = "active"
            print("Approved", user.id)


if __name__ == "__main__":
    main()
