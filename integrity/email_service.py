import os
import smtplib
import mimetypes
import logging
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from email.mime.base import MIMEBase
from email import encoders
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Any, Optional

logger = logging.getLogger('civifix.email')

# Thread pool for asynchronous, non-blocking email dispatch
_email_executor = ThreadPoolExecutor(max_workers=2)

# In-memory dispatch audit log (useful for tests, inspection, and verification)
_SENT_EMAILS_LOG = []


def get_sent_emails():
    """Return a copy of all dispatched or recorded emails."""
    return list(_SENT_EMAILS_LOG)


def clear_sent_emails():
    """Clear recorded email logs (primarily for testing)."""
    _SENT_EMAILS_LOG.clear()


class EmailConfig:
    """SMTP & Email Configuration."""
    @classmethod
    def get_smtp_server(cls) -> str:
        return os.environ.get('SMTP_SERVER', 'smtp.gmail.com')

    @classmethod
    def get_smtp_port(cls) -> int:
        try:
            return int(os.environ.get('SMTP_PORT', '587'))
        except ValueError:
            return 587

    @classmethod
    def get_smtp_use_tls(cls) -> bool:
        return os.environ.get('SMTP_USE_TLS', 'True').strip().lower() in ('true', '1', 'yes')

    @classmethod
    def get_smtp_user(cls) -> Optional[str]:
        return (
            os.environ.get('SMTP_USERNAME')
            or os.environ.get('GMAIL_USER')
            or os.environ.get('MAIL_USERNAME')
        )

    @classmethod
    def get_smtp_password(cls) -> Optional[str]:
        return (
            os.environ.get('SMTP_PASSWORD')
            or os.environ.get('GMAIL_APP_PASSWORD')
            or os.environ.get('MAIL_PASSWORD')
        )

    @classmethod
    def get_default_sender(cls) -> str:
        return (
            os.environ.get('MAIL_DEFAULT_SENDER')
            or cls.get_smtp_user()
            or 'noreply.civifix@gmail.com'
        )


def build_complaint_email_content(
    recipient_email: str,
    recipient_name: str,
    complaint_data: Dict[str, Any],
    has_image: bool = False
) -> tuple[str, str, str]:
    """
    Builds subject, plain-text body, and responsive HTML body
    containing all grievance details.
    """
    complaint_id = complaint_data.get('id', 'N/A')
    ref_code = f"#CIVI-{complaint_id:05d}" if isinstance(complaint_id, int) else f"#{complaint_id}"
    title = complaint_data.get('title', 'Civic Grievance')
    category = complaint_data.get('category', 'General')
    location = complaint_data.get('location', 'Unspecified')
    description = complaint_data.get('description', '')
    status = complaint_data.get('status', 'Pending')
    ai_category = complaint_data.get('ai_category') or 'Pending Classification'
    ai_priority = complaint_data.get('ai_priority') or 'Normal'
    created_at = complaint_data.get('created_at') or datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    lat = complaint_data.get('latitude')
    lng = complaint_data.get('longitude')
    
    maps_url = ""
    coords_text = "Not provided"
    if lat is not None and lng is not None:
        coords_text = f"{lat:.5f}, {lng:.5f}"
        maps_url = f"https://www.google.com/maps?q={lat},{lng}"

    subject = f"[{ref_code}] Complaint Confirmation - {title}"

    # Plain text version
    text_body = f"""Hello {recipient_name},

Thank you for submitting your grievance to CiviFix – Community Complaint Management System.
Your complaint has been successfully registered and queued for verification and resolution.

--------------------------------------------------
COMPLAINT DETAILS:
--------------------------------------------------
Reference Code : {ref_code}
Title          : {title}
Category       : {category}
Status         : {status}
Submission Time: {created_at}
Location       : {location}
GPS Coordinates: {coords_text}
AI Priority    : {ai_priority}
AI Category    : {ai_category}
Evidence Photo : {"Attached to this email" if has_image else "No photo attached"}

DESCRIPTION:
{description}

--------------------------------------------------
You can monitor progress on your Citizen Dashboard.
Thank you for helping improve our community!

--
CiviFix Community Complaint System
Support & Civic Action Desk
"""

    # Rich responsive HTML template
    maps_button_html = ""
    if maps_url:
        maps_button_html = f"""
        <div style="margin-top: 6px;">
            <a href="{maps_url}" target="_blank" style="display: inline-block; padding: 4px 10px; background: #e0e7ff; color: #4338ca; text-decoration: none; border-radius: 6px; font-size: 12px; font-weight: 600;">
                📍 View on Google Maps
            </a>
        </div>
        """

    image_card_html = ""
    if has_image:
        image_card_html = """
        <div style="margin-top: 24px; padding: 16px; background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 12px; text-align: center;">
            <div style="font-size: 13px; font-weight: 700; color: #334155; margin-bottom: 12px; text-transform: uppercase; letter-spacing: 0.5px;">
                📸 Uploaded Photographic Evidence
            </div>
            <div style="display: inline-block; max-width: 100%; border-radius: 8px; overflow: hidden; box-shadow: 0 4px 12px rgba(0,0,0,0.08); border: 1px solid #cbd5e1;">
                <img src="cid:evidence_image" alt="Complaint Evidence Photo" style="max-width: 100%; height: auto; max-height: 400px; display: block; object-fit: cover;" />
            </div>
            <div style="margin-top: 8px; font-size: 11px; color: #64748b;">
                Original high-resolution file is also attached to this email and archived in municipal records.
            </div>
        </div>
        """
    else:
        image_card_html = """
        <div style="margin-top: 20px; padding: 12px; background: #f1f5f9; border-radius: 8px; text-align: center; color: #64748b; font-size: 12px;">
            No photographic evidence was attached with this submission.
        </div>
        """

    html_body = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{subject}</title>
</head>
<body style="margin: 0; padding: 0; background-color: #f1f5f9; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #1e293b;">
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background-color: #f1f5f9; padding: 30px 10px;">
        <tr>
            <td align="center">
                <table role="presentation" width="100%" max-width="600" style="max-width: 600px; background-color: #ffffff; border-radius: 16px; overflow: hidden; box-shadow: 0 10px 25px rgba(0,0,0,0.05); border: 1px solid #e2e8f0;">
                    <!-- Header -->
                    <tr>
                        <td style="background: linear-gradient(135deg, #4f46e5 0%, #06b6d4 100%); padding: 28px 24px; text-align: center; color: #ffffff;">
                            <div style="display: inline-block; width: 44px; height: 44px; line-height: 44px; background: rgba(255,255,255,0.2); border-radius: 12px; font-weight: 800; font-size: 22px; margin-bottom: 8px;">
                                C
                            </div>
                            <h1 style="margin: 0; font-size: 22px; font-weight: 800; letter-spacing: -0.5px;">CiviFix Grievance System</h1>
                            <p style="margin: 4px 0 0; font-size: 13px; opacity: 0.9;">Official Citizen Submission Confirmation</p>
                        </td>
                    </tr>

                    <!-- Body Content -->
                    <tr>
                        <td style="padding: 24px;">
                            <p style="margin: 0 0 16px; font-size: 15px; color: #334155;">
                                Dear <strong>{recipient_name}</strong>,
                            </p>
                            <p style="margin: 0 0 20px; font-size: 14px; color: #475569; line-height: 1.5;">
                                Thank you for your civic contribution. Your complaint has been formally registered in our management system. A detailed record is provided below for your reference.
                            </p>

                            <!-- Reference Badge -->
                            <div style="margin-bottom: 20px; padding: 14px; background-color: #f8fafc; border-left: 4px solid #4f46e5; border-radius: 0 8px 8px 0;">
                                <div style="font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px; color: #64748b; font-weight: 600;">Reference Code</div>
                                <div style="font-size: 18px; font-weight: 800; color: #1e293b; margin-top: 2px;">{ref_code}</div>
                            </div>

                            <!-- Details Table -->
                            <table role="presentation" width="100%" cellspacing="0" cellpadding="8" border="0" style="border-collapse: collapse; font-size: 13px; color: #334155;">
                                <tr style="border-bottom: 1px solid #f1f5f9;">
                                    <td width="35%" style="font-weight: 600; color: #64748b;">Title</td>
                                    <td width="65%" style="font-weight: 600; color: #0f172a;">{title}</td>
                                </tr>
                                <tr style="border-bottom: 1px solid #f1f5f9;">
                                    <td style="font-weight: 600; color: #64748b;">Category</td>
                                    <td><span style="display: inline-block; padding: 3px 8px; background: #f1f5f9; border-radius: 6px; font-weight: 600;">{category}</span></td>
                                </tr>
                                <tr style="border-bottom: 1px solid #f1f5f9;">
                                    <td style="font-weight: 600; color: #64748b;">Status</td>
                                    <td><span style="display: inline-block; padding: 3px 10px; background: #fef3c7; color: #92400e; border-radius: 9999px; font-size: 12px; font-weight: 700;">{status}</span></td>
                                </tr>
                                <tr style="border-bottom: 1px solid #f1f5f9;">
                                    <td style="font-weight: 600; color: #64748b;">AI Priority Assessment</td>
                                    <td><span style="display: inline-block; padding: 3px 8px; background: #ecfdf5; color: #065f46; border-radius: 6px; font-weight: 600;">{ai_priority}</span></td>
                                </tr>
                                <tr style="border-bottom: 1px solid #f1f5f9;">
                                    <td style="font-weight: 600; color: #64748b;">Submission Time</td>
                                    <td>{created_at}</td>
                                </tr>
                                <tr style="border-bottom: 1px solid #f1f5f9;">
                                    <td style="font-weight: 600; color: #64748b;">Exact Location</td>
                                    <td>
                                        <div>{location}</div>
                                        {maps_button_html}
                                    </td>
                                </tr>
                                <tr style="border-bottom: 1px solid #f1f5f9;">
                                    <td style="font-weight: 600; color: #64748b;">GPS Coordinates</td>
                                    <td><code style="font-family: monospace; font-size: 12px; background: #f1f5f9; padding: 2px 6px; border-radius: 4px;">{coords_text}</code></td>
                                </tr>
                            </table>

                            <!-- Description Block -->
                            <div style="margin-top: 18px; padding: 14px; background: #f8fafc; border-radius: 8px; border: 1px solid #e2e8f0;">
                                <div style="font-size: 12px; font-weight: 700; color: #475569; margin-bottom: 6px; text-transform: uppercase;">Full Description:</div>
                                <div style="font-size: 13px; color: #1e293b; line-height: 1.6; white-space: pre-wrap;">{description}</div>
                            </div>

                            <!-- Photographic Evidence Display -->
                            {image_card_html}

                            <div style="margin-top: 24px; padding-top: 16px; border-top: 1px solid #e2e8f0; text-align: center;">
                                <p style="font-size: 12px; color: #94a3b8; margin: 0;">
                                    This is an automated notification. To check the live progress of this grievance, log in to your account dashboard.
                                </p>
                            </div>
                        </td>
                    </tr>

                    <!-- Footer -->
                    <tr>
                        <td style="background-color: #0f172a; color: #94a3b8; padding: 16px 24px; text-align: center; font-size: 11px;">
                            © 2026 CiviFix Community Grievance Management System • Built with Civic Pride
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>
</body>
</html>
"""
    return subject, text_body, html_body


def send_complaint_confirmation_email(
    recipient_email: str,
    recipient_name: str,
    complaint_data: Dict[str, Any],
    upload_folder: Optional[str] = None
) -> Dict[str, Any]:
    """
    Constructs and sends an email notification to the user's Gmail/email address.
    Includes all complaint details and attaches/embeds the photographic evidence.
    """
    if not recipient_email or '@' not in recipient_email:
        logger.warning(f"Invalid recipient email '{recipient_email}'. Skipping email dispatch.")
        return {'success': False, 'error': 'Invalid recipient email'}

    image_path = complaint_data.get('image_path')
    image_bytes = None
    image_mime = "image/jpeg"
    image_filename = None
    has_image = False

    if image_path and upload_folder:
        full_image_path = os.path.join(upload_folder, image_path)
        if os.path.exists(full_image_path):
            try:
                with open(full_image_path, 'rb') as f:
                    image_bytes = f.read()
                guessed_mime, _ = mimetypes.guess_type(full_image_path)
                if guessed_mime and guessed_mime.startswith('image/'):
                    image_mime = guessed_mime
                image_filename = os.path.basename(full_image_path)
                has_image = True
            except Exception as e:
                logger.error(f"Failed to read image for complaint confirmation: {e}")

    subject, text_body, html_body = build_complaint_email_content(
        recipient_email=recipient_email,
        recipient_name=recipient_name,
        complaint_data=complaint_data,
        has_image=has_image
    )

    sender = EmailConfig.get_default_sender()

    # Create root MIME container
    msg = MIMEMultipart('related')
    msg['Subject'] = subject
    msg['From'] = f"CiviFix System <{sender}>"
    msg['To'] = recipient_email
    msg['Date'] = datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S +0000")

    # Alternative container for text and html
    msg_alt = MIMEMultipart('alternative')
    msg.attach(msg_alt)

    # Attach plain text and HTML versions
    part_text = MIMEText(text_body, 'plain', 'utf-8')
    part_html = MIMEText(html_body, 'html', 'utf-8')
    msg_alt.attach(part_text)
    msg_alt.attach(part_html)

    # Embed and attach image if present
    if has_image and image_bytes:
        try:
            # Inline embedded image for HTML cid:evidence_image
            maintype, subtype = image_mime.split('/', 1)
            img_part = MIMEImage(image_bytes, _subtype=subtype)
            img_part.add_header('Content-ID', '<evidence_image>')
            img_part.add_header('Content-Disposition', 'inline', filename=image_filename)
            msg.attach(img_part)

            # Also add file attachment header so users can download it directly from Gmail
            attach_part = MIMEBase(maintype, subtype)
            attach_part.set_payload(image_bytes)
            encoders.encode_base64(attach_part)
            attach_part.add_header('Content-Disposition', 'attachment', filename=f"evidence_{image_filename}")
            msg.attach(attach_part)
        except Exception as e:
            logger.error(f"Failed to attach image to email: {e}")

    # Record dispatch attempt in audit store
    record = {
        'to': recipient_email,
        'name': recipient_name,
        'subject': subject,
        'complaint_id': complaint_data.get('id'),
        'has_image': has_image,
        'image_filename': image_filename,
        'timestamp': datetime.utcnow().isoformat(),
        'status': 'RECORDED'
    }

    # Attempt live SMTP delivery if credentials are provided
    smtp_user = EmailConfig.get_smtp_user()
    smtp_password = EmailConfig.get_smtp_password()
    smtp_server = EmailConfig.get_smtp_server()
    smtp_port = EmailConfig.get_smtp_port()
    use_tls = EmailConfig.get_smtp_use_tls()

    if smtp_user and smtp_password:
        try:
            logger.info(f"Connecting to SMTP server {smtp_server}:{smtp_port} to deliver email to {recipient_email}...")
            with smtplib.SMTP(smtp_server, smtp_port, timeout=12) as server:
                if use_tls:
                    server.starttls()
                server.login(smtp_user, smtp_password)
                server.send_message(msg)
            record['status'] = 'SENT'
            logger.info(f"Successfully delivered complaint confirmation email to {recipient_email}")
        except Exception as smtp_err:
            record['status'] = 'SMTP_FAILED'
            record['error'] = str(smtp_err)
            logger.warning(f"SMTP delivery to {recipient_email} failed: {smtp_err}. Email record archived.")
    else:
        # Fallback in local/testing environment where live Gmail credentials are not set
        record['status'] = 'MOCKED_LOCAL'
        logger.info(
            f"[EMAIL SERVICE] Complaint confirmation email prepared for {recipient_email} (ID: {complaint_data.get('id')}). "
            f"Set SMTP_USERNAME/SMTP_PASSWORD in environment for live Gmail delivery."
        )

    _SENT_EMAILS_LOG.append(record)
    return {'success': True, 'record': record}


def queue_complaint_confirmation_email(
    recipient_email: str,
    recipient_name: str,
    complaint_data: Dict[str, Any],
    upload_folder: Optional[str] = None
):
    """
    Submits email creation and dispatch to background thread pool.
    Ensures zero blocking latency on the user's web submission request.
    """
    _email_executor.submit(
        send_complaint_confirmation_email,
        recipient_email,
        recipient_name,
        complaint_data,
        upload_folder
    )
