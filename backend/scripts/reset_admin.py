#!/usr/bin/env python3
"""Reset or create a superadmin account.

Usage (inside backend container):
    python scripts/reset_admin.py --username admin --password NewPass123!
"""
import argparse
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select

from app.database import DATABASE_URL, Base
from app.models.user import User, Role
from app.auth import hash_password


async def reset(username: str, password: str):
    engine = create_async_engine(DATABASE_URL)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        result = await session.execute(select(User).where(User.username == username))
        user = result.scalar_one_or_none()

        if user:
            user.hashed_password = hash_password(password)
            user.role = Role.superadmin
            user.is_active = True
            await session.commit()
            print(f"Password reset for user '{username}' (role set to superadmin).")
        else:
            user = User(
                username=username,
                email=f"{username}@localhost",
                hashed_password=hash_password(password),
                role=Role.superadmin,
                is_active=True,
            )
            session.add(user)
            await session.commit()
            print(f"Created superadmin user '{username}'.")

    await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Reset or create a GnuKontrolR superadmin account.")
    parser.add_argument("--username", required=True, help="Username to reset or create")
    parser.add_argument("--password", required=True, help="New password")
    args = parser.parse_args()
    asyncio.run(reset(args.username, args.password))
