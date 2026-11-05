"""Development-only demo user provisioning.

The platform ships with no registration route by design. For a local demo we seed
a requester and a reviewer so the human-review gate can be demonstrated without
weakening authentication. Seeding is disabled in production by config validation.
a requester, a reviewer and an admin so the governance gates can be demonstrated
without weakening authentication. Seeding is disabled in production by config validation.
from __future__ import annotations

import logging
import uuid

from sqlalchemy import select

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.user import User
from app.security.auth import hash_password

logger = logging.getLogger(__name__)

DEMO_USERS = (
    ("demo", "DEMO_USER_PASSWORD", "viewer", "starter"),
    ("reviewer", "DEMO_REVIEWER_PASSWORD", "reviewer", "starter"),
    ("admin", "DEMO_ADMIN_PASSWORD", "admin", "enterprise"),
)


async def seed_demo_users() -> None:
    """Create the demo requester and reviewer if they do not exist."""
    if not settings.SEED_DEMO_USERS:
        return
    if settings.is_production:
        logger.error("Refusing to seed demo users in production")
        return

    async with SessionLocal() as session:
        for username, password_field, role, tier in DEMO_USERS:
            existing = await session.scalar(select(User).where(User.username == username))
            if existing is not None:
                continue
            session.add(
                User(
                    id=str(uuid.uuid4()),
                    username=username,
                    hashed_password=hash_password(str(getattr(settings, password_field))),
                    role=role,
                    tier=tier,
                )
            )
            logger.info("Seeded demo user %s (%s)", username, role)
        await session.commit()
