"""
Manual Resend smoke test — sends one of each template to a recipient.

    python test_email.py you@example.com
"""

import asyncio
import sys

from app.config import settings
from app.services.email_service import (
    low_balance_email,
    new_contacts_email,
    send_email,
    verification_email,
    weekly_summary_email,
)

FRONTEND_URL = settings.frontend_url


async def main() -> None:
    if len(sys.argv) < 2:
        print("usage: python test_email.py you@example.com")
        raise SystemExit(1)
    to = sys.argv[1]

    results = {
        "verification": await send_email(
            to,
            "Verify your Sparrow account",
            verification_email(f"{FRONTEND_URL}/login?verified=true"),
        ),
        "new_contacts": await send_email(
            to,
            "3 new contacts",
            new_contacts_email(
                "Series B fintech — platform teams",
                [
                    {"name": "Priya Raghavan", "title": "VP of Engineering", "company": "Ramp"},
                    {"name": "Marcus Webb", "title": "Head of Platform", "company": "Mercury"},
                    {"name": "Dani Okonjo", "title": "Director of Data", "company": "Brex"},
                ],
                FRONTEND_URL,
            ),
        ),
        "low_balance": await send_email(
            to, "Your Sparrow credits are running low", low_balance_email(32, FRONTEND_URL)
        ),
        "weekly_summary": await send_email(
            to,
            "Your Sparrow week",
            weekly_summary_email(
                name="Jordan Blake",
                contacts_found=14,
                drafts_written=11,
                credits_spent=36,
                balance=465,
                agent_runs=3,
                frontend_url=FRONTEND_URL,
            ),
        ),
    }

    for name, ok in results.items():
        print(f"{'OK  ' if ok else 'FAIL'} {name}")


if __name__ == "__main__":
    asyncio.run(main())
