from app.ingestion.webhook import extract_message, extract_status_update, verify_webhook_challenge


def _envelope(message: dict, contacts: list | None = None) -> dict:
    return {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "contacts": contacts or [{"profile": {"name": "Jane Doe"}}],
                            "messages": [message],
                        }
                    }
                ]
            }
        ]
    }


def test_extract_plain_text_message():
    body = _envelope({"from": "919876543210", "id": "wamid.1", "timestamp": "1700000000", "type": "text", "text": {"body": "hello"}})
    result = extract_message(body)
    assert result.phone_number == "919876543210"
    assert result.sender_name == "Jane Doe"
    assert result.text == "hello"
    assert result.message_type == "text"
    assert result.is_valid()


def test_extract_button_reply_id():
    body = _envelope(
        {
            "from": "919876543210", "id": "wamid.2", "timestamp": "1700000001", "type": "interactive",
            "interactive": {"type": "button_reply", "button_reply": {"id": "accept_session:42", "title": "Accept"}},
        }
    )
    result = extract_message(body)
    assert result.button_reply_id == "accept_session:42"
    assert result.button_reply_title == "Accept"


def test_extract_list_reply_id_falls_back_correctly():
    body = _envelope(
        {
            "from": "919876543210", "id": "wamid.3", "timestamp": "1700000002", "type": "interactive",
            "interactive": {"type": "list_reply", "list_reply": {"id": "choose_doctor|7|918888888888", "title": "Dr. X"}},
        }
    )
    result = extract_message(body)
    assert result.button_reply_id == "choose_doctor|7|918888888888"


def test_extract_image_with_caption():
    body = _envelope(
        {"from": "919876543210", "id": "wamid.4", "timestamp": "1700000003", "type": "image",
         "image": {"id": "media123", "caption": "vaccination card"}}
    )
    result = extract_message(body)
    assert result.image_media_id == "media123"
    assert result.text == "vaccination card"


def test_extract_location():
    body = _envelope(
        {"from": "919876543210", "id": "wamid.5", "timestamp": "1700000004", "type": "location",
         "location": {"latitude": 12.9, "longitude": 77.6, "name": "Home"}}
    )
    result = extract_message(body)
    assert result.latitude == 12.9
    assert result.longitude == 77.6
    assert result.location_text == "Home"


def test_extract_returns_none_for_status_update_payload():
    body = {"entry": [{"changes": [{"value": {"statuses": [{"id": "wamid.6", "status": "delivered"}]}}]}]}
    assert extract_message(body) is None


def test_extract_status_update_parses_failed_status_with_errors():
    body = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "statuses": [
                                {
                                    "id": "wamid.6",
                                    "status": "failed",
                                    "errors": [{"code": 131047, "title": "Re-engagement message"}],
                                }
                            ]
                        }
                    }
                ]
            }
        ]
    }
    status = extract_status_update(body)
    assert status["status"] == "failed"
    assert status["errors"][0]["code"] == 131047


def test_extract_status_update_returns_none_for_message_payload():
    body = _envelope({"from": "919876543210", "id": "wamid.1", "timestamp": "1700000000", "type": "text", "text": {"body": "hi"}})
    assert extract_status_update(body) is None


def test_invalid_missing_phone_number():
    body = _envelope({"from": "", "id": "wamid.7", "timestamp": "1700000005", "type": "text", "text": {"body": "hi"}})
    result = extract_message(body)
    assert result.is_valid() is False


def test_verify_challenge_success():
    assert verify_webhook_challenge("subscribe", "secret", "12345", "secret") == "12345"


def test_verify_challenge_wrong_token():
    assert verify_webhook_challenge("subscribe", "wrong", "12345", "secret") is None
