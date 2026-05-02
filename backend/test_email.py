"""Run with: RESEND_API_KEY=re_xxx python test_email.py"""
import asyncio
import os
import sys

sys.path.insert(0, ".")
os.environ.setdefault("RESEND_API_KEY", os.environ.get("RESEND_API_KEY", ""))

from app.services.email_service import send_email, verification_email, new_jobs_digest_email, weekly_summary_email

TO = "tdmorrison03@gmail.com"
FRONTEND_URL = "http://localhost:3000"


async def main():
    print("Sending verification email...")
    ok = await send_email(TO, "Verify your ApplyNow account", verification_email(f"{FRONTEND_URL}/login?verified=true"))
    print("  ✓ sent" if ok else "  ✗ failed")

    print("Sending job digest email...")
    jobs = [
        {"id": "abc123", "title": "Senior Software Engineer", "company": "Stripe", "location": "Remote", "url": "https://stripe.com/jobs", "match_score": 0.92, "match_reasoning": "Strong TypeScript and distributed systems background."},
        {"id": "def456", "title": "Backend Engineer", "company": "Linear", "location": "San Francisco, CA", "url": "https://linear.app/jobs", "match_score": 0.78, "match_reasoning": "Matches target role and company size preference."},
    ]
    ok = await send_email(TO, "2 new jobs found — apply early", new_jobs_digest_email(jobs, FRONTEND_URL))
    print("  ✓ sent" if ok else "  ✗ failed")

    print("Sending weekly summary email...")
    ok = await send_email(TO, "Your ApplyNow weekly summary", weekly_summary_email(
        name="Tyler", jobs_found=8, contacts_found=5, applications_created=3, agent_runs=12, frontend_url=FRONTEND_URL
    ))
    print("  ✓ sent" if ok else "  ✗ failed")


asyncio.run(main())
