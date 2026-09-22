import os
import io
import pytest
from PIL import Image
from integrity.email_service import (
    build_complaint_email_content,
    send_complaint_confirmation_email,
    get_sent_emails,
    clear_sent_emails,
    EmailConfig
)

def test_build_complaint_email_content():
    complaint_data = {
        'id': 42,
        'title': 'Severe Water Pipe Leakage',
        'category': 'Water Supply & Sewage',
        'description': 'Main water line burst causing flooding on street.',
        'location': 'Ward 12, MG Road',
        'latitude': 17.3850,
        'longitude': 78.4867,
        'status': 'Under Review',
        'ai_category': 'Water Supply',
        'ai_priority': 'High',
        'created_at': '2026-09-22 18:00:00 UTC'
    }
    
    subject, text_body, html_body = build_complaint_email_content(
        recipient_email='citizen@gmail.com',
        recipient_name='John Citizen',
        complaint_data=complaint_data,
        has_image=True
    )
    
    assert '#CIVI-00042' in subject
    assert 'Severe Water Pipe Leakage' in subject
    assert 'John Citizen' in text_body
    assert '17.38500, 78.48670' in text_body
    assert 'Water Supply & Sewage' in text_body
    assert 'High' in text_body
    
    # HTML template assertions
    assert 'cid:evidence_image' in html_body
    assert 'google.com/maps?q=17.385,78.4867' in html_body
    assert 'Severe Water Pipe Leakage' in html_body
    assert 'Under Review' in html_body

def test_send_complaint_confirmation_email_with_image(tmp_path):
    clear_sent_emails()
    
    # Create test image file in temp directory
    img_dir = tmp_path / "uploads"
    img_dir.mkdir()
    img_file = img_dir / "pothole.jpg"
    
    img = Image.new('RGB', (80, 80), color=(255, 0, 0))
    img.save(str(img_file), format='JPEG')
    
    complaint_data = {
        'id': 101,
        'title': 'Dangerous Open Manhole',
        'category': 'Sanitation',
        'description': 'Uncovered manhole near school zone.',
        'location': 'Sector 4',
        'latitude': 12.9,
        'longitude': 77.6,
        'image_path': 'pothole.jpg',
        'status': 'Pending',
        'ai_category': 'Sanitation',
        'ai_priority': 'Critical'
    }
    
    result = send_complaint_confirmation_email(
        recipient_email='user@gmail.com',
        recipient_name='Jane Citizen',
        complaint_data=complaint_data,
        upload_folder=str(img_dir)
    )
    
    assert result['success'] is True
    sent = get_sent_emails()
    assert len(sent) == 1
    assert sent[0]['to'] == 'user@gmail.com'
    assert sent[0]['has_image'] is True
    assert sent[0]['image_filename'] == 'pothole.jpg'
    assert sent[0]['complaint_id'] == 101

def test_send_complaint_confirmation_email_invalid_recipient():
    result = send_complaint_confirmation_email(
        recipient_email='invalid-email-address',
        recipient_name='Test',
        complaint_data={'id': 1}
    )
    assert result['success'] is False
    assert 'Invalid recipient' in result['error']
