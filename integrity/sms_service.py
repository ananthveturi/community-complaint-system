import os
import re
import logging
from datetime import datetime
from typing import Dict, Any, Optional

logger = logging.getLogger('civifix.sms')

# In-memory SMS dispatch audit log for tests, inspection, and verification
_SENT_SMS_LOG = []


def get_sent_sms():
    """Return a copy of all dispatched or recorded SMS messages."""
    return list(_SENT_SMS_LOG)


def clear_sent_sms():
    """Clear recorded SMS logs."""
    _SENT_SMS_LOG.clear()


class SMSConfig:
    """SMS Gateway Configuration."""
    @classmethod
    def get_twilio_account_sid(cls) -> Optional[str]:
        return os.environ.get('TWILIO_ACCOUNT_SID')

    @classmethod
    def get_twilio_auth_token(cls) -> Optional[str]:
        return os.environ.get('TWILIO_AUTH_TOKEN')

    @classmethod
    def get_twilio_from_number(cls) -> Optional[str]:
        return os.environ.get('TWILIO_PHONE_NUMBER') or os.environ.get('SMS_FROM_NUMBER')

    @classmethod
    def is_configured(cls) -> bool:
        return bool(cls.get_twilio_account_sid() and cls.get_twilio_auth_token() and cls.get_twilio_from_number())


def clean_phone_number(phone: str) -> str:
    """Normalize phone number string."""
    if not phone:
        return ""
    # Keep digits and leading +
    cleaned = phone.strip()
    has_plus = cleaned.startswith('+')
    digits = re.sub(r'\D', '', cleaned)
    return ('+' + digits) if has_plus else digits


def send_otp_sms(
    recipient_phone: str,
    otp_code: str,
    purpose: str = 'complaint_submission'
) -> Dict[str, Any]:
    """
    Sends a 6-digit verification code to the citizen's phone number.
    Supports Twilio live delivery if configured, with resilient local dev logging fallback.
    """
    cleaned_phone = clean_phone_number(recipient_phone)
    if not cleaned_phone or len(cleaned_phone) < 7:
        return {'success': False, 'error': 'Invalid phone number format'}

    message_body = (
        f"[CiviFix Verification] Your 6-digit security code is {otp_code}. "
        f"Valid for 10 minutes to verify your complaint submission. Never share this code."
    )

    record = {
        'to': cleaned_phone,
        'otp_code': otp_code,
        'message': message_body,
        'purpose': purpose,
        'timestamp': datetime.utcnow().isoformat(),
        'status': 'RECORDED'
    }

    if SMSConfig.is_configured():
        try:
            # Twilio REST API dispatch without external dependency using urllib
            import urllib.request
            import urllib.parse
            import base64

            sid = SMSConfig.get_twilio_account_sid()
            token = SMSConfig.get_twilio_auth_token()
            from_num = SMSConfig.get_twilio_from_number()

            url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"
            data = urllib.parse.urlencode({
                'To': cleaned_phone,
                'From': from_num,
                'Body': message_body
            }).encode('utf-8')

            req = urllib.request.Request(url, data=data, method='POST')
            auth_header = base64.b64encode(f"{sid}:{token}".encode('utf-8')).decode('ascii')
            req.add_header("Authorization", f"Basic {auth_header}")

            with urllib.request.urlopen(req, timeout=10) as response:
                if 200 <= response.getcode() < 300:
                    record['status'] = 'SENT'
                    logger.info(f"Successfully sent live SMS OTP to {cleaned_phone}")
                else:
                    record['status'] = f'HTTP_{response.getcode()}'
        except Exception as e:
            record['status'] = 'GATEWAY_ERROR'
            record['error'] = str(e)
            logger.warning(f"Failed to dispatch live SMS to {cleaned_phone}: {e}")
    else:
        record['status'] = 'MOCKED_LOCAL'
        logger.info(
            f"[SMS SERVICE] OTP {otp_code} generated for phone {cleaned_phone} (Local/Dev mode). "
            f"Set TWILIO_ACCOUNT_SID/TWILIO_AUTH_TOKEN/TWILIO_PHONE_NUMBER in .env for live SMS."
        )

    _SENT_SMS_LOG.append(record)
    return {'success': True, 'record': record, 'live_sent': record['status'] == 'SENT'}
