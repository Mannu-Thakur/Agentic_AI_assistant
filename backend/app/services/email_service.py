import logging
import asyncio
import smtplib
from email.message import EmailMessage
from typing import Optional

from app.core.config import settings

logger = logging.getLogger("app.services.email")


class EmailService:
    @staticmethod
    async def send_password_reset_email(to_email: str, reset_url: str) -> bool:
        """
        Sends a password reset email using aiosmtplib (or smtplib thread fallback).
        Falls back to printing/logging the reset URL to the console in development mode.
        """
        subject = f"[{settings.PROJECT_NAME}] Reset Your Password"

        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #0b0f19; color: #e2e8f0; margin: 0; padding: 40px 20px; }}
                .card {{ max-width: 520px; margin: 0 auto; background: #161b26; border: 1px solid #2d3748; border-radius: 16px; padding: 32px; box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.5); }}
                .logo {{ font-size: 20px; font-weight: bold; color: #8b5cf6; margin-bottom: 24px; text-align: center; }}
                h2 {{ color: #ffffff; font-size: 22px; margin-top: 0; margin-bottom: 12px; }}
                p {{ color: #94a3b8; font-size: 14px; line-height: 1.6; margin-bottom: 24px; }}
                .btn {{ display: block; width: fit-content; margin: 28px auto; padding: 14px 28px; background-color: #7c3aed; color: #ffffff !important; text-decoration: none; font-weight: 600; font-size: 14px; border-radius: 10px; text-align: center; box-shadow: 0 4px 14px rgba(124, 58, 237, 0.4); }}
                .footer {{ margin-top: 32px; font-size: 12px; color: #64748b; text-align: center; border-top: 1px solid #2d3748; padding-top: 20px; }}
                .link {{ word-break: break-all; color: #a78bfa; font-size: 12px; }}
            </style>
        </head>
        <body>
            <div class="card">
                <div class="logo">⚡ {settings.PROJECT_NAME}</div>
                <h2>Password Reset Requested</h2>
                <p>We received a request to reset the password for your account (<strong>{to_email}</strong>). Click the button below to choose a new password. This link will expire in <strong>{settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES} minutes</strong>.</p>
                <a href="{reset_url}" class="btn">Reset Password</a>
                <p>If you didn't request a password reset, you can safely ignore this email. Your password will remain unchanged.</p>
                <p>Or copy and paste this link into your browser:<br><span class="link">{reset_url}</span></p>
                <div class="footer">
                    &copy; {settings.PROJECT_NAME}. Secure Password Reset Dispatcher.
                </div>
            </div>
        </body>
        </html>
        """

        text_content = f"""
Reset Your Password — {settings.PROJECT_NAME}

We received a request to reset your password for {to_email}.
Please visit the link below to set a new password (expires in {settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES} minutes):

{reset_url}

If you did not request this, please ignore this message.
        """

        # Dynamically load fresh .env values in case .env was updated after server start
        from dotenv import load_dotenv
        import os
        env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".env"))
        if os.path.isfile(env_path):
            load_dotenv(env_path, override=True)

        smtp_user = os.getenv("SMTP_USER") or settings.SMTP_USER
        smtp_password = os.getenv("SMTP_PASSWORD") or settings.SMTP_PASSWORD
        smtp_host = os.getenv("SMTP_HOST") or settings.SMTP_HOST
        smtp_port = int(os.getenv("SMTP_PORT") or settings.SMTP_PORT)
        smtp_from_email = os.getenv("SMTP_FROM_EMAIL") or settings.SMTP_FROM_EMAIL or smtp_user
        smtp_from_name = os.getenv("SMTP_FROM_NAME") or settings.SMTP_FROM_NAME

        # Check if SMTP credentials are provided
        if not smtp_user or not smtp_password:
            logger.info("================================================================================")
            logger.info(f"[DEV EMAIL FALLBACK] Password Reset Link for {to_email}:")
            logger.info(f"===> RESET URL: {reset_url}")
            logger.info("================================================================================")
            print(f"\n[DEV EMAIL FALLBACK] Reset Link for {to_email}:\n{reset_url}\n", flush=True)
            return True

        from_display = f"{smtp_from_name} <{smtp_from_email}>"

        message = EmailMessage()
        message["From"] = from_display
        message["To"] = to_email
        message["Subject"] = subject
        message.set_content(text_content)
        message.add_alternative(html_content, subtype="html")

        try:
            # Prefer aiosmtplib if installed, otherwise fallback to smtplib in thread
            try:
                import aiosmtplib
                await aiosmtplib.send(
                    message,
                    hostname=smtp_host,
                    port=smtp_port,
                    username=smtp_user,
                    password=smtp_password,
                    start_tls=True if smtp_port == 587 else False,
                    use_tls=True if smtp_port == 465 else False,
                    timeout=10.0,
                )
            except ImportError:
                def _send_sync():
                    if smtp_port == 465:
                        with smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=10.0) as server:
                            server.login(smtp_user, smtp_password)
                            server.send_message(message)
                    else:
                        with smtplib.SMTP(smtp_host, smtp_port, timeout=10.0) as server:
                            if smtp_port == 587:
                                server.starttls()
                            server.login(smtp_user, smtp_password)
                            server.send_message(message)
                await asyncio.to_thread(_send_sync)


            logger.info(f"Password reset email sent successfully to {to_email}")
            return True
        except Exception as e:
            logger.error(f"Failed to send password reset email via SMTP to {to_email}: {e}")
            print(f"\n[SMTP FAILED FALLBACK] Reset Link for {to_email}:\n{reset_url}\n", flush=True)
            return False
