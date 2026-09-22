import secrets
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

import database
from integrity.email_service import send_otp_email, EmailConfig
from integrity.sms_service import send_otp_sms, SMSConfig, clean_phone_number

logger = logging.getLogger('civifix.otp')

OTP_EXPIRY_MINUTES = 10
MAX_VERIFICATION_ATTEMPTS = 5


def generate_numeric_otp(digits: int = 6) -> str:
    """Generate a cryptographically secure random numeric OTP."""
    return ''.join(secrets.choice('0123456789') for _ in range(digits))


def send_single_otp(
    target: str,
    target_type: str = 'email',
    purpose: str = 'registration',
    user_name: str = 'Citizen'
) -> Dict[str, Any]:
    """
    Generates and dispatches a single 6-digit OTP to either email or phone.
    Stores record in database with 10-minute expiry.
    """
    if not target:
        return {'success': False, 'error': f'A valid {target_type} is required.'}

    now = datetime.utcnow()
    expires_at = (now + timedelta(minutes=OTP_EXPIRY_MINUTES)).strftime("%Y-%m-%d %H:%M:%S")
    otp_code = generate_numeric_otp(6)

    if target_type == 'email':
        cleaned = target.strip().lower()
        if '@' not in cleaned:
            return {'success': False, 'error': 'Invalid email address format.'}
        database.save_otp_record(
            target=cleaned,
            otp_code=otp_code,
            purpose=purpose,
            target_type='email',
            expires_at=expires_at
        )
        send_otp_email(
            recipient_email=cleaned,
            recipient_name=user_name,
            otp_code=otp_code,
            purpose=purpose
        )
        live_configured = EmailConfig.is_configured()
        return {
            'success': True,
            'message': f'Verification code dispatched to {cleaned}',
            'target': cleaned,
            'target_type': 'email',
            'live_sent': live_configured,
            'dev_otp': otp_code if not live_configured else None,
            'expires_in_seconds': OTP_EXPIRY_MINUTES * 60
        }
    elif target_type == 'phone':
        cleaned = clean_phone_number(target)
        if len(cleaned) < 7:
            return {'success': False, 'error': 'Invalid mobile phone number format.'}
        database.save_otp_record(
            target=cleaned,
            otp_code=otp_code,
            purpose=purpose,
            target_type='phone',
            expires_at=expires_at
        )
        send_otp_sms(
            recipient_phone=cleaned,
            otp_code=otp_code,
            purpose=purpose
        )
        live_configured = SMSConfig.is_configured()
        return {
            'success': True,
            'message': f'Verification code dispatched to {cleaned}',
            'target': cleaned,
            'target_type': 'phone',
            'live_sent': live_configured,
            'dev_otp': otp_code if not live_configured else None,
            'expires_in_seconds': OTP_EXPIRY_MINUTES * 60
        }
    else:
        return {'success': False, 'error': f'Unsupported target type: {target_type}'}


def send_dual_otp(
    user_id: Optional[int] = None,
    email: Optional[str] = None,
    phone: Optional[str] = None,
    user_name: str = 'Citizen',
    purpose: str = 'complaint_submission'
) -> Dict[str, Any]:
    """
    Generates and dispatches separate 6-digit OTPs for both email and phone.
    Stores records in the database with 10-minute expiry.
    """
    # If user_id provided, fetch registered details if not passed explicitly
    if user_id and (not email or not phone):
        user = database.get_user_by_id(user_id)
        if user:
            if not email and user.get('email'):
                email = user.get('email')
            if not phone and user.get('phone'):
                phone = user.get('phone')
            if not user_name and user.get('full_name'):
                user_name = user.get('full_name')

    if not email or '@' not in email:
        return {'success': False, 'error': 'A valid email address is required for OTP verification.'}
    if not phone or len(clean_phone_number(phone)) < 7:
        return {'success': False, 'error': 'A valid mobile phone number is required for OTP verification.'}

    cleaned_email = email.strip().lower()
    cleaned_phone = clean_phone_number(phone)

    now = datetime.utcnow()
    expires_at = (now + timedelta(minutes=OTP_EXPIRY_MINUTES)).strftime("%Y-%m-%d %H:%M:%S")

    email_otp = generate_numeric_otp(6)
    phone_otp = generate_numeric_otp(6)

    # Persist in database
    database.save_otp_record(
        target=cleaned_email,
        otp_code=email_otp,
        purpose=purpose,
        target_type='email',
        expires_at=expires_at
    )
    database.save_otp_record(
        target=cleaned_phone,
        otp_code=phone_otp,
        purpose=purpose,
        target_type='phone',
        expires_at=expires_at
    )

    # Dispatch email
    email_res = send_otp_email(
        recipient_email=cleaned_email,
        recipient_name=user_name,
        otp_code=email_otp,
        purpose=purpose
    )

    # Dispatch SMS
    sms_res = send_otp_sms(
        recipient_phone=cleaned_phone,
        otp_code=phone_otp,
        purpose=purpose
    )

    live_smtp = EmailConfig.is_configured()
    live_sms = SMSConfig.is_configured()

    return {
        'success': True,
        'message': f'Verification codes sent to {cleaned_email} and {cleaned_phone}.',
        'email': cleaned_email,
        'phone': cleaned_phone,
        'expires_in_seconds': OTP_EXPIRY_MINUTES * 60,
        'live_smtp': live_smtp,
        'live_sms': live_sms,
        # For seamless local development and automated testing when live gateways are not configured:
        'dev_email_otp': email_otp if not live_smtp else None,
        'dev_phone_otp': phone_otp if not live_sms else None,
    }


def verify_target_otp(
    target: str,
    otp_code: str,
    purpose: str = 'complaint_submission',
    target_type: str = 'email'
) -> Dict[str, Any]:
    """
    Verifies an individual OTP for a given target (email or phone).
    """
    if not target or not otp_code:
        return {'success': False, 'error': f'Please provide the {target_type} OTP code.'}

    cleaned_target = clean_phone_number(target) if target_type == 'phone' else target.strip().lower()
    cleaned_code = str(otp_code).strip()

    record = database.get_active_otp(
        target=cleaned_target,
        purpose=purpose,
        target_type=target_type
    )

    if not record:
        return {
            'success': False,
            'error': f'No active {target_type} verification code found or it has expired. Please request a new code.'
        }

    attempts = record.get('attempts', 0)
    if attempts >= MAX_VERIFICATION_ATTEMPTS:
        database.consume_otp_record(record['id'])
        return {
            'success': False,
            'error': f'Too many failed attempts on {target_type} verification. Please request a fresh OTP.'
        }

    # Compare code
    if record['otp_code'] != cleaned_code:
        database.increment_otp_attempt_record(record['id'])
        remaining = MAX_VERIFICATION_ATTEMPTS - (attempts + 1)
        return {
            'success': False,
            'error': f'Incorrect {target_type} verification code. ({remaining} attempts remaining)'
        }

    # Code matched - consume it
    database.consume_otp_record(record['id'])
    return {'success': True, 'message': f'{target_type.capitalize()} verified successfully.'}


def verify_dual_otp(
    email: str,
    email_otp: str,
    phone: str,
    phone_otp: str,
    purpose: str = 'complaint_submission',
    user_id: Optional[int] = None
) -> Dict[str, Any]:
    """
    Verifies BOTH email and phone OTPs simultaneously.
    If valid, marks the user as verified in database.
    """
    # 1. Verify Email OTP
    res_email = verify_target_otp(email, email_otp, purpose=purpose, target_type='email')
    if not res_email.get('success'):
        return {
            'success': False,
            'error': res_email.get('error', 'Email verification failed.'),
            'failed_channel': 'email'
        }

    # 2. Verify Phone OTP
    res_phone = verify_target_otp(phone, phone_otp, purpose=purpose, target_type='phone')
    if not res_phone.get('success'):
        return {
            'success': False,
            'error': res_phone.get('error', 'Phone verification failed.'),
            'failed_channel': 'phone'
        }

    # 3. Mark user verified in DB if user_id is provided
    if user_id:
        database.mark_user_verified(user_id, email_verified=True, phone_verified=True)

    return {
        'success': True,
        'message': 'Both email and mobile number verified successfully. Identity confirmed!'
    }
