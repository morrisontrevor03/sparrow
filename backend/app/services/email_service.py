import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

RESEND_API_URL = "https://api.resend.com/emails"


async def send_email(to: str, subject: str, html: str) -> bool:
    if not settings.resend_api_key:
        logger.warning("RESEND_API_KEY not set — skipping email to %s", to)
        return False

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            RESEND_API_URL,
            headers={
                "Authorization": f"Bearer {settings.resend_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "from": settings.resend_from_email,
                "to": [to],
                "subject": subject,
                "html": html,
            },
            timeout=10,
        )

    if resp.status_code not in (200, 201):
        logger.error("Resend error %s: %s", resp.status_code, resp.text)
        return False

    logger.info("Email sent to %s: %s", to, subject)
    return True


def _base_wrapper(badge_color: str, badge_text: str, title: str, body_html: str) -> str:
    settings_url = f"{settings.frontend_url}/settings"
    return f"""
    <div style="font-family: system-ui, sans-serif; max-width: 600px; margin: 0 auto; background: #09090b; color: #fafafa; padding: 32px; border-radius: 12px;">
      <div style="margin-bottom: 24px;">
        <span style="background: {badge_color}20; color: {badge_color}; padding: 4px 12px; border-radius: 999px; font-size: 13px; font-weight: 600;">{badge_text}</span>
      </div>
      <h1 style="font-size: 22px; font-weight: 700; margin: 0 0 20px;">{title}</h1>
      {body_html}
      <p style="color: #52525b; font-size: 11px; margin-top: 32px; padding-top: 16px; border-top: 1px solid #27272a;">
        You're receiving this because you have an ApplyNow account.
        <a href="{settings_url}" style="color: #71717a; text-decoration: underline;">Manage notification preferences</a>
      </p>
    </div>
    """


def verification_email(verify_url: str) -> str:
    body = f"""
      <p style="color: #d4d4d8; font-size: 14px; line-height: 1.6; margin: 0 0 24px;">
        Thanks for signing up! Click the button below to verify your email address and activate your account.
        This link expires in 24 hours.
      </p>
      <a href="{verify_url}" style="background: #fff; color: #09090b; padding: 12px 24px; border-radius: 8px; text-decoration: none; font-weight: 600; font-size: 15px;">Verify Email →</a>
      <p style="color: #52525b; font-size: 12px; margin-top: 24px;">
        If you didn't create an account, you can safely ignore this email.
      </p>
    """
    return _base_wrapper("#22c55e", "Verify your email", "Confirm your ApplyNow account", body)


def job_alert_email(job_title: str, company: str, job_url: str, match_score: float, match_reasoning: str, app_url: str) -> str:
    score_pct = int(match_score * 100)
    return f"""
    <div style="font-family: system-ui, sans-serif; max-width: 600px; margin: 0 auto; background: #09090b; color: #fafafa; padding: 32px; border-radius: 12px;">
      <div style="margin-bottom: 24px;">
        <span style="background: #22c55e20; color: #22c55e; padding: 4px 12px; border-radius: 999px; font-size: 13px; font-weight: 600;">{score_pct}% match</span>
      </div>
      <h1 style="font-size: 22px; font-weight: 700; margin: 0 0 8px;">{job_title}</h1>
      <p style="color: #a1a1aa; margin: 0 0 20px; font-size: 15px;">{company}</p>
      <p style="color: #d4d4d8; font-size: 14px; line-height: 1.6; margin: 0 0 24px;">{match_reasoning}</p>
      <div style="display: flex; gap: 12px;">
        <a href="{app_url}" style="background: #fff; color: #09090b; padding: 10px 20px; border-radius: 8px; text-decoration: none; font-weight: 600; font-size: 14px;">View Draft</a>
        <a href="{job_url}" style="background: transparent; color: #fafafa; padding: 10px 20px; border-radius: 8px; text-decoration: none; font-weight: 600; font-size: 14px; border: 1px solid #27272a;">View Posting</a>
      </div>
    </div>
    """


def draft_ready_email(job_title: str, company: str, application_id: str, frontend_url: str) -> str:
    review_url = f"{frontend_url}/applications/{application_id}"
    return f"""
    <div style="font-family: system-ui, sans-serif; max-width: 600px; margin: 0 auto; background: #09090b; color: #fafafa; padding: 32px; border-radius: 12px;">
      <div style="margin-bottom: 24px;">
        <span style="background: #3b82f620; color: #3b82f6; padding: 4px 12px; border-radius: 999px; font-size: 13px; font-weight: 600;">Draft Ready</span>
      </div>
      <h1 style="font-size: 22px; font-weight: 700; margin: 0 0 8px;">Your application is drafted</h1>
      <p style="color: #a1a1aa; margin: 0 0 20px; font-size: 15px;">{job_title} · {company}</p>
      <p style="color: #d4d4d8; font-size: 14px; line-height: 1.6; margin: 0 0 24px;">
        ApplyNow has tailored your resume and written a cover letter for this role.
        Review the draft and apply before other candidates even see the posting.
      </p>
      <a href="{review_url}" style="background: #fff; color: #09090b; padding: 12px 24px; border-radius: 8px; text-decoration: none; font-weight: 600; font-size: 15px;">Review &amp; Apply →</a>
    </div>
    """


def new_jobs_digest_email(jobs: list[dict], frontend_url: str) -> str:
    """
    jobs: list of dicts with keys: id, title, company, location, url, match_score, match_reasoning
    """
    count = len(jobs)
    jobs_html = ""
    for job in jobs:
        score_pct = int(float(job.get("match_score", 0)) * 100)
        score_color = "#22c55e" if score_pct >= 85 else "#f59e0b" if score_pct >= 70 else "#a1a1aa"
        location = job.get("location") or "Remote"
        jobs_html += f"""
        <div style="border: 1px solid #27272a; border-radius: 8px; padding: 16px; margin-bottom: 12px;">
          <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 6px;">
            <div>
              <p style="font-weight: 600; font-size: 15px; margin: 0 0 2px; color: #fafafa;">{job["title"]}</p>
              <p style="color: #a1a1aa; font-size: 13px; margin: 0;">{job["company"]} · {location}</p>
            </div>
            <span style="color: {score_color}; font-size: 13px; font-weight: 600; white-space: nowrap; margin-left: 12px;">{score_pct}% match</span>
          </div>
          <div style="display: flex; gap: 8px; margin-top: 12px;">
            <a href="{frontend_url}/jobs/{job['id']}" style="background: #fff; color: #09090b; padding: 6px 14px; border-radius: 6px; text-decoration: none; font-weight: 600; font-size: 13px;">View in App</a>
            <a href="{job['url']}" style="background: transparent; color: #d4d4d8; padding: 6px 14px; border-radius: 6px; text-decoration: none; font-size: 13px; border: 1px solid #27272a;">Job Posting ↗</a>
          </div>
        </div>
        """

    heading = f"{count} new job{'s' if count != 1 else ''} found for you"
    body = f"""
      <p style="color: #a1a1aa; font-size: 14px; margin: 0 0 20px;">
        ApplyNow just discovered these openings. Apply early — early applicants are up to 4× more likely to get a response.
      </p>
      {jobs_html}
      <a href="{frontend_url}/jobs" style="display: inline-block; margin-top: 8px; background: #27272a; color: #fafafa; padding: 10px 20px; border-radius: 8px; text-decoration: none; font-size: 14px; font-weight: 600;">View all jobs →</a>
    """
    return _base_wrapper("#22c55e", "New jobs found", heading, body)


def finish_setup_email(frontend_url: str) -> str:
    onboarding_url = f"{frontend_url}/onboarding"
    body = f"""
      <p style="color: #d4d4d8; font-size: 14px; line-height: 1.6; margin: 0 0 20px;">
        You signed up for ApplyNow but haven't uploaded your resume yet.
        That's the one thing your agents need to start finding jobs and contacts for you.
      </p>
      <p style="color: #d4d4d8; font-size: 14px; line-height: 1.6; margin: 0 0 24px;">
        It takes 2 minutes to finish setup — upload your resume, set your target role and location,
        and we'll run your first search right away.
      </p>
      <a href="{onboarding_url}" style="background: #fff; color: #09090b; padding: 12px 24px; border-radius: 8px; text-decoration: none; font-weight: 600; font-size: 15px;">Finish setup →</a>
    """
    return _base_wrapper("#f59e0b", "Action needed", "Finish your ApplyNow setup", body)


def first_outreach_ready_email(frontend_url: str) -> str:
    networking_url = f"{frontend_url}/networking"
    body = f"""
      <p style="color: #d4d4d8; font-size: 14px; line-height: 1.6; margin: 0 0 20px;">
        Your resume is set up and your preferences are saved.
        ApplyNow is ready to find warm contacts at your target companies and draft your first outreach messages.
      </p>
      <p style="color: #d4d4d8; font-size: 14px; line-height: 1.6; margin: 0 0 24px;">
        Run the Networking Agent to get your first list of people to connect with — complete with
        personalized message drafts you can send directly from the app.
      </p>
      <a href="{networking_url}" style="background: #fff; color: #09090b; padding: 12px 24px; border-radius: 8px; text-decoration: none; font-weight: 600; font-size: 15px;">View your first outreach →</a>
      <p style="color: #71717a; font-size: 12px; margin-top: 20px;">
        Nothing goes out automatically — you review and send every message yourself.
      </p>
    """
    return _base_wrapper("#3b82f6", "Your network is ready", "Your first outreach is ready to send", body)


def weekly_summary_email(
    name: str | None,
    jobs_found: int,
    contacts_found: int,
    applications_created: int,
    agent_runs: int,
    frontend_url: str,
) -> str:
    display_name = name.split()[0] if name else "there"

    def stat_block(value: int, label: str, color: str) -> str:
        return f"""
        <div style="flex: 1; background: #18181b; border-radius: 8px; padding: 16px; text-align: center; min-width: 120px;">
          <p style="font-size: 28px; font-weight: 700; margin: 0 0 4px; color: {color};">{value}</p>
          <p style="color: #71717a; font-size: 12px; margin: 0; text-transform: uppercase; letter-spacing: 0.05em;">{label}</p>
        </div>
        """

    stats_html = f"""
    <div style="display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 28px;">
      {stat_block(jobs_found, "Jobs Found", "#22c55e")}
      {stat_block(contacts_found, "Contacts Found", "#3b82f6")}
      {stat_block(applications_created, "Drafts Created", "#a855f7")}
      {stat_block(agent_runs, "Agent Runs", "#f59e0b")}
    </div>
    """

    body = f"""
      <p style="color: #a1a1aa; font-size: 14px; margin: 0 0 24px;">
        Hey {display_name}, here's what your ApplyNow agents accomplished this week.
      </p>
      {stats_html}
      <a href="{frontend_url}/dashboard" style="background: #fff; color: #09090b; padding: 12px 24px; border-radius: 8px; text-decoration: none; font-weight: 600; font-size: 15px;">Open Dashboard →</a>
    """
    return _base_wrapper("#a855f7", "Weekly Summary", "Your week with ApplyNow", body)
