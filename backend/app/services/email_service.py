import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

RESEND_API_URL = "https://api.resend.com/emails"

# Light palette, matching the app. Email clients ignore CSS variables, so these
# are duplicated literals by necessity — keep them in sync with globals.css.
INK = "#18181b"
MUTED = "#52525b"
SUBTLE = "#a1a1aa"
SURFACE = "#ffffff"
SURFACE_SUNK = "#f7f7f8"
BORDER = "#e4e4e7"
ACCENT = "#2f8f5b"


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


def _button(href: str, label: str) -> str:
    return (
        f'<a href="{href}" style="background: {INK}; color: #ffffff; padding: 12px 24px; '
        f'border-radius: 8px; text-decoration: none; font-weight: 600; font-size: 15px; '
        f'display: inline-block;">{label}</a>'
    )


def _base_wrapper(badge_color: str, badge_text: str, title: str, body_html: str) -> str:
    settings_url = f"{settings.frontend_url}/settings"
    return f"""
    <div style="font-family: system-ui, -apple-system, sans-serif; max-width: 600px; margin: 0 auto; background: {SURFACE}; color: {INK}; padding: 32px; border-radius: 12px; border: 1px solid {BORDER};">
      <div style="margin-bottom: 24px;">
        <span style="background: {badge_color}1a; color: {badge_color}; padding: 4px 12px; border-radius: 999px; font-size: 13px; font-weight: 600;">{badge_text}</span>
      </div>
      <h1 style="font-size: 22px; font-weight: 700; margin: 0 0 20px; color: {INK};">{title}</h1>
      {body_html}
      <p style="color: {SUBTLE}; font-size: 11px; margin-top: 32px; padding-top: 16px; border-top: 1px solid {BORDER};">
        You're receiving this because you have a Sparrow account.
        <a href="{settings_url}" style="color: {MUTED}; text-decoration: underline;">Manage notification preferences</a>
      </p>
    </div>
    """


def verification_email(verify_url: str) -> str:
    body = f"""
      <p style="color: {MUTED}; font-size: 14px; line-height: 1.6; margin: 0 0 24px;">
        Thanks for signing up. Click the button below to verify your email address and
        activate your account. This link expires in 24 hours.
      </p>
      {_button(verify_url, "Verify email →")}
      <p style="color: {SUBTLE}; font-size: 12px; margin-top: 24px;">
        If you didn't create an account, you can safely ignore this email.
      </p>
    """
    return _base_wrapper(ACCENT, "Verify your email", "Confirm your Sparrow account", body)


def new_contacts_email(campaign_name: str, contacts: list[dict], frontend_url: str) -> str:
    rows = "".join(
        f"""
        <div style="background: {SURFACE_SUNK}; border: 1px solid {BORDER}; border-radius: 10px; padding: 14px 16px; margin-bottom: 10px;">
          <div style="font-weight: 600; font-size: 15px; color: {INK};">{c.get('name', '')}</div>
          <div style="color: {MUTED}; font-size: 13px; margin-top: 2px;">{c.get('title', '')} · {c.get('company', '')}</div>
        </div>
        """
        for c in contacts[:5]
    )
    more = (
        f'<p style="color: {MUTED}; font-size: 13px;">…and {len(contacts) - 5} more.</p>'
        if len(contacts) > 5
        else ""
    )
    body = f"""
      <p style="color: {MUTED}; font-size: 14px; line-height: 1.6; margin: 0 0 20px;">
        Sparrow found {len(contacts)} new {'person' if len(contacts) == 1 else 'people'} for
        <strong style="color: {INK};">{campaign_name}</strong>, with a first message drafted for each.
      </p>
      {rows}
      {more}
      <div style="margin-top: 20px;">{_button(f"{frontend_url}/contacts", "Review and send →")}</div>
    """
    return _base_wrapper(ACCENT, "New contacts", f"{len(contacts)} new contacts", body)


def low_balance_email(balance: int, frontend_url: str) -> str:
    body = f"""
      <p style="color: {MUTED}; font-size: 14px; line-height: 1.6; margin: 0 0 20px;">
        You have <strong style="color: {INK};">{balance} credits</strong> left. Your autopilot
        campaigns will pause when the balance reaches zero — no surprise charges, they just stop.
      </p>
      {_button(f"{frontend_url}/settings?tab=billing", "Top up credits →")}
    """
    return _base_wrapper("#d97706", "Low balance", "Your credits are running low", body)


def finish_setup_email(frontend_url: str) -> str:
    body = f"""
      <p style="color: {MUTED}; font-size: 14px; line-height: 1.6; margin: 0 0 20px;">
        You signed up for Sparrow but haven't created a campaign yet. A campaign takes about a
        minute to set up: tell Sparrow who you want to reach and why, and it starts finding them.
      </p>
      {_button(f"{frontend_url}/campaigns/new", "Create your first campaign →")}
    """
    return _base_wrapper("#d97706", "Action needed", "Finish setting up Sparrow", body)


def first_outreach_ready_email(frontend_url: str) -> str:
    body = f"""
      <p style="color: {MUTED}; font-size: 14px; line-height: 1.6; margin: 0 0 20px;">
        Your campaign is set up and Sparrow is ready to find the right people and draft your
        first messages. One run is all it takes to see what it comes back with.
      </p>
      {_button(f"{frontend_url}/campaigns", "Run your campaign →")}
    """
    return _base_wrapper(ACCENT, "Ready to run", "Your first outreach is ready", body)


def weekly_summary_email(
    name: str | None,
    contacts_found: int,
    drafts_written: int,
    credits_spent: int,
    balance: int,
    agent_runs: int,
    frontend_url: str,
) -> str:
    display_name = (name or "").split()[0] if name else "there"

    def stat(value: int, label: str) -> str:
        return f"""
          <td style="padding: 12px 8px; text-align: center;">
            <div style="font-size: 26px; font-weight: 700; color: {INK};">{value}</div>
            <div style="color: {MUTED}; font-size: 12px; margin-top: 2px;">{label}</div>
          </td>
        """

    body = f"""
      <p style="color: {MUTED}; font-size: 14px; line-height: 1.6; margin: 0 0 20px;">
        Hey {display_name}, here's what Sparrow did this week.
      </p>
      <table style="width: 100%; background: {SURFACE_SUNK}; border: 1px solid {BORDER}; border-radius: 10px; border-collapse: separate;">
        <tr>
          {stat(contacts_found, "contacts found")}
          {stat(drafts_written, "messages drafted")}
          {stat(agent_runs, "runs")}
        </tr>
      </table>
      <p style="color: {MUTED}; font-size: 13px; margin: 16px 0 20px;">
        {credits_spent} credits spent · {balance} remaining
      </p>
      {_button(f"{frontend_url}/contacts", "Review your contacts →")}
    """
    return _base_wrapper("#7c3aed", "Weekly summary", "Your Sparrow week", body)
