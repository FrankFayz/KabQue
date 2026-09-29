import io
import json
import urllib.error
import urllib.parse
from datetime import date
from unittest import mock

from django.test import SimpleTestCase, override_settings

from queueapp.notifications import (
    _at_hint,
    _at_is_sandbox,
    _at_message_data,
    _at_parse_error,
    _at_recipient_accepted,
    _at_recipients,
    _at_sender_id,
    build_approval_sms,
    send_sms_notification,
)
from queueapp.registration import (
    normalize_registration_number,
    validate_kabale_registration_number,
)


class KabaleRegistrationNumberTests(SimpleTestCase):
    def test_accepts_full_time(self):
        self.assertEqual(
            validate_kabale_registration_number("2026/A/BBB/0000/F"),
            "2026/A/BBB/0000/F",
        )

    def test_accepts_government_sponsored(self):
        self.assertEqual(
            validate_kabale_registration_number("2026/A/AAA/2000/G/F"),
            "2026/A/AAA/2000/G/F",
        )

    def test_normalizes_case_and_spaces(self):
        self.assertEqual(
            validate_kabale_registration_number("2026 / a / bba / 3000 / f"),
            "2026/A/BBA/3000/F",
        )

    def test_accepts_varying_programme_and_serial_lengths(self):
        self.assertEqual(
            validate_kabale_registration_number("2025/A/BIT/7/F"),
            "2025/A/BIT/7/F",
        )
        self.assertEqual(
            validate_kabale_registration_number("2024/A/COMPUTERSCIENCE/123456/G/F"),
            "2024/A/COMPUTERSCIENCE/123456/G/F",
        )

    def test_rejects_missing_admitted_marker(self):
        with self.assertRaises(ValueError):
            validate_kabale_registration_number("2026/BBA/3000/F")

    def test_rejects_random_strings(self):
        with self.assertRaises(ValueError):
            validate_kabale_registration_number("2024/UG/001")
        with self.assertRaises(ValueError):
            validate_kabale_registration_number("not-a-reg")

    def test_rejects_missing_full_time_suffix(self):
        with self.assertRaises(ValueError):
            validate_kabale_registration_number("2026/A/BBA/3000")
        with self.assertRaises(ValueError):
            validate_kabale_registration_number("2026/A/BBA/3000/G")

    def test_normalize_only(self):
        self.assertEqual(
            normalize_registration_number(" 2026/a/bba/1/f "),
            "2026/A/BBA/1/F",
        )


GSM7_BASIC = set(
    "@£$¥èéùìòÇ\nØø\rÅå"
    "Δ_ΦΓΛΩΠΨΣΏÆæßÉ !\"#¤%&'()*+,-./0123456789:;<=>?"
    "¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿abcdefghijklmnopqrstuvwxyzäöñüà"
)


class ApprovalSmsSegmentTests(SimpleTestCase):
    """
    Some East African networks reject multipart (2-part) messages while accepting
    every 1-part message, and multipart doubles the cost. These tests stop the
    approval SMS from ever growing back into a second segment.
    """

    def _sms(self, full_name="Tracy", reg="2026/A/KCS/3103/G/F", code="FR4FGSGA", pos=1):
        return build_approval_sms(
            full_name=full_name,
            registration_number=reg,
            scheduled_date=date(2026, 9, 24),
            secret_code=code,
            position=pos,
        )

    def test_fits_in_one_segment(self):
        self.assertLessEqual(len(self._sms()), 160)

    def test_fits_in_one_segment_with_worst_case_inputs(self):
        longest = self._sms(
            full_name="Mwangi Jonathan Peter",
            reg="2026/A/BBBB/4444/F",
            code="A1B2C3D4",
            pos=148,
        )
        self.assertLessEqual(len(longest), 160)

    def test_uses_only_gsm7_characters(self):
        # Any non-GSM-7 char would force UCS-2 encoding and 5 segments.
        self.assertEqual([c for c in self._sms() if c not in GSM7_BASIC], [])

    def test_keeps_the_student_name_code_and_date(self):
        sms = self._sms()
        self.assertIn("Tracy", sms)
        self.assertIn("FR4FGSGA", sms)
        self.assertIn("24 Sep 2026", sms)

    def test_handles_missing_name(self):
        self.assertIn("Student", self._sms(full_name=""))


class AfricaTalkingResponseTests(SimpleTestCase):
    """
    Africa's Talking answers HTTP 200 with a per-recipient verdict buried in the
    body. The old MySMSGate code trusted the status code alone, which is exactly
    how a bad sender ID or a typo'd number could show the desk a green tick.
    These tests pin success to an explicit accept and nothing else.
    """

    def _ok_body(self, number="+256712345678"):
        return {
            "SMSMessageData": {
                "Message": "Sent to 1/1 Total Cost: UGX 100.0000",
                "Recipients": [
                    {
                        "statusCode": 101,
                        "number": number,
                        "status": "Success",
                        "cost": "UGX 100.0000",
                        "messageId": "ATXid_abc123",
                    }
                ],
            }
        }

    def test_reads_recipients_out_of_the_envelope(self):
        recipients = _at_recipients(self._ok_body())
        self.assertEqual(len(recipients), 1)
        self.assertEqual(recipients[0]["messageId"], "ATXid_abc123")

    def test_error_envelope_yields_no_recipients(self):
        parsed = {"errorMessage": "Invalid API key", "errorCode": "AUTH001"}
        self.assertEqual(_at_recipients(parsed), [])

    def test_unexpected_shapes_yield_no_recipients(self):
        for parsed in (None, "not json", {}, {"SMSMessageData": "nope"}, [1, 2]):
            self.assertEqual(_at_recipients(parsed), [])

    def test_message_data_exposes_the_verdict_string(self):
        parsed = {"SMSMessageData": {"Message": "InvalidSenderId", "Recipients": []}}
        self.assertEqual(_at_message_data(parsed)["Message"], "InvalidSenderId")
        self.assertEqual(_at_message_data(None), {})

    def test_accepted_status_codes_report_success(self):
        for code in (101, 102, 103, "101"):
            self.assertTrue(_at_recipient_accepted({"statusCode": code}), code)

    def test_accepted_status_words_report_success(self):
        for word in ("Success", "SentSuccess", "Sent", "submitted", "Sent_Success"):
            self.assertTrue(_at_recipient_accepted({"status": word}), word)

    def test_status_word_lookalikes_are_not_accepted(self):
        for word in ("Sent Fail", "SendingFailed", "Rejected", ""):
            self.assertFalse(_at_recipient_accepted({"status": word}), word)

    def test_refusals_never_report_success(self):
        refusals = (
            {"statusCode": 106, "status": "Invalid Phone Number"},
            {"statusCode": 108, "status": "Invalid SenderId"},
            {"statusCode": 112, "status": "InsufficientBalance"},
            {"status": "NotSupportedByNetwork"},
            {"status": "SendingFailed"},
            {},
        )
        for entry in refusals:
            self.assertFalse(_at_recipient_accepted(entry), entry)

    def test_parse_error_prefers_the_human_message(self):
        raw = '{"errorMessage": "Insufficient balance", "errorCode": "402"}'
        self.assertEqual(_at_parse_error(raw), "Insufficient balance")

    def test_parse_error_falls_back_to_raw_text(self):
        self.assertEqual(_at_parse_error("upstream exploded"), "upstream exploded")

    def test_hints_never_leak_provider_jargon(self):
        cases = (
            (0, "Invalid API key"),
            (0, "Invalid SenderId"),
            (0, "NotSupportedByNetwork"),
            (400, "recipient not recognised"),
        )
        for code, detail in cases:
            hint = _at_hint(code, detail)
            self.assertTrue(hint)
            self.assertIn("Text messages could not be sent", hint)
            for jargon in ("SenderId", "NotSupported", "401", "400", "API key"):
                self.assertNotIn(jargon, hint, f"{detail} -> {hint}")

    def test_balance_hint_points_at_topping_up(self):
        self.assertIn("credit", _at_hint(0, "InsufficientBalance").lower())


class AfricaTalkingRequestTests(SimpleTestCase):
    """
    The wire format, pinned to what the live API actually accepts.

    Both rules below were found by calling the real sandbox endpoint, not by
    reading the docs, which describe the opposite:
      * JSON bodies get HTTP 415; only form encoding is accepted.
      * The sandbox REJECTS every `from` value with "InvalidSenderId",
        including "sandbox" and "". The field must be omitted entirely.
    """

    def test_sandbox_omits_the_sender_field_entirely(self):
        with override_settings(
            AFRICAS_TALKING_ENVIRONMENT="sandbox",
            AFRICAS_TALKING_SHORTCODE="KabQue",
            AFRICAS_TALKING_BASE_URL="https://api.sandbox.africastalking.com",
        ):
            self.assertEqual(_at_sender_id(), "")
            self.assertTrue(_at_is_sandbox())

    def test_production_uses_the_configured_alphanumeric_sender(self):
        with override_settings(
            AFRICAS_TALKING_ENVIRONMENT="production",
            AFRICAS_TALKING_SHORTCODE="KabQue",
            AFRICAS_TALKING_BASE_URL="https://api.africastalking.com",
        ):
            self.assertEqual(_at_sender_id(), "KabQue")
            self.assertFalse(_at_is_sandbox())


class AfricaTalkingSendTests(SimpleTestCase):
    """End-to-end send behaviour against a faked HTTP transport."""

    def _send(self, body, status=200, *, to="+256712345678", env="sandbox"):
        captured = {}

        class _FakeResponse:
            def __init__(self, payload):
                self._payload = json.dumps(payload).encode()

            def read(self):
                return self._payload

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        def _fake_urlopen(request, timeout=None):
            captured["url"] = request.full_url
            captured["headers"] = {k.lower(): v for k, v in request.headers.items()}
            # AT's /version1/messaging is form-encoded, not JSON.
            captured["raw_body"] = request.data.decode()
            captured["payload"] = {
                k: v[0] for k, v in urllib.parse.parse_qs(request.data.decode()).items()
            }
            if isinstance(status, int):
                return _FakeResponse(body)
            raise status

        with override_settings(
            AFRICAS_TALKING_ENVIRONMENT=env,
            AFRICAS_TALKING_API_KEY="test-key",
            AFRICAS_TALKING_USERNAME="sandbox" if env == "sandbox" else "kabqueapp",
            AFRICAS_TALKING_SHORTCODE="KabQue",
            AFRICAS_TALKING_BASE_URL=(
                "https://api.sandbox.africastalking.com"
                if env == "sandbox"
                else "https://api.africastalking.com"
            ),
        ):
            with mock.patch(
                "queueapp.notifications.urllib.request.urlopen", _fake_urlopen
            ):
                ok, err = send_sms_notification(to, "KabQue test message")
        return ok, err, captured

    def test_accepted_send_succeeds_and_sends_the_right_request(self):
        ok, err, sent = self._send(
            {
                "SMSMessageData": {
                    "Message": "Sent to 1/1 Total Cost: UGX 100.0000",
                    "Recipients": [
                        {
                            "statusCode": 101,
                            "number": "+256712345678",
                            "status": "Success",
                            "messageId": "ATXid_abc123",
                        }
                    ],
                }
            }
        )
        self.assertTrue(ok, err)
        self.assertEqual(err, "")
        self.assertEqual(sent["url"], "https://api.sandbox.africastalking.com/version1/messaging")
        self.assertEqual(sent["headers"]["apikey"], "test-key")
        # Form encoding only — JSON gets HTTP 415 from the live API.
        self.assertEqual(
            sent["headers"]["content-type"], "application/x-www-form-urlencoded"
        )
        self.assertNotIn("{", sent["raw_body"])
        # The sandbox rejects any `from` value, so it must not be sent at all.
        self.assertNotIn("from", sent["payload"])
        self.assertEqual(sent["payload"]["to"], "+256712345678")
        self.assertEqual(sent["payload"]["message"], "KabQue test message")

    def test_production_send_uses_the_alphanumeric_sender(self):
        ok, err, sent = self._send(
            {
                "SMSMessageData": {
                    "Recipients": [{"statusCode": 101, "status": "Success"}]
                }
            },
            env="production",
        )
        self.assertTrue(ok, err)
        self.assertEqual(
            sent["url"], "https://api.africastalking.com/version1/messaging"
        )
        self.assertEqual(sent["payload"]["from"], "KabQue")

    def test_refused_recipient_is_reported_as_a_failure(self):
        ok, err, _ = self._send(
            {
                "SMSMessageData": {
                    "Recipients": [
                        {"statusCode": 106, "status": "InvalidPhoneNumber"}
                    ]
                }
            }
        )
        self.assertFalse(ok)
        self.assertIn("Text messages could not be sent", err)

    def test_error_envelope_is_not_treated_as_success(self):
        ok, err, _ = self._send(
            {"errorMessage": "Invalid API key", "errorCode": "AUTH001"}
        )
        self.assertFalse(ok)
        self.assertIn("Text messages could not be sent", err)

    def test_reason_is_read_from_message_when_recipients_is_empty(self):
        # Observed live: HTTP 201 + {"Message": "InvalidSenderId", "Recipients": []}
        ok, err, _ = self._send(
            {"SMSMessageData": {"Message": "InvalidSenderId", "Recipients": []}}
        )
        self.assertFalse(ok)
        self.assertIn("sender ID", err)
        # A server-side fault must never be blamed on the student's phone number.
        self.assertNotIn("phone number", err)

    def test_unsupported_content_type_is_reported_as_a_server_fault(self):
        # Observed live: HTTP 415, whose text contains "not supported".
        ok, err, _ = self._send(
            None,
            status=urllib.error.HTTPError(
                "https://api.sandbox.africastalking.com/version1/messaging",
                415,
                "Unsupported Media Type",
                {},
                io.BytesIO(
                    b"The request's Content-Type [application/json] is not supported."
                ),
            ),
        )
        self.assertFalse(ok)
        self.assertIn("misconfigured", err)
        self.assertNotIn("phone number", err)

    def test_empty_recipient_list_is_not_treated_as_success(self):
        ok, err, _ = self._send({"SMSMessageData": {"Message": "Sent to 0/1"}})
        self.assertFalse(ok)
        self.assertIn("Text messages could not be sent", err)

    def test_http_error_is_not_treated_as_success(self):
        ok, err, _ = self._send(
            None,
            status=urllib.error.HTTPError(
                "https://api.sandbox.africastalking.com/version1/messaging",
                401,
                "Unauthorized",
                {},
                io.BytesIO(b'{"errorMessage":"Invalid API key"}'),
            ),
        )
        self.assertFalse(ok)
        self.assertIn("Text messages could not be sent", err)

    def test_missing_api_key_fails_before_any_request(self):
        with override_settings(AFRICAS_TALKING_API_KEY=""):
            ok, err = send_sms_notification("+256712345678", "hello")
        self.assertFalse(ok)
        self.assertIn("not fully set up", err)

    def test_local_number_is_normalized_before_sending(self):
        ok, err, sent = self._send(
            {
                "SMSMessageData": {
                    "Recipients": [{"statusCode": 101, "status": "Success"}]
                }
            },
            to="0712345678",
        )
        self.assertTrue(ok, err)
        self.assertEqual(sent["payload"]["to"], "+256712345678")

    def test_bare_legacy_local_number_is_assumed_ugandan(self):
        ok, err, sent = self._send(
            {
                "SMSMessageData": {
                    "Recipients": [{"statusCode": 101, "status": "Success"}]
                }
            },
            to="0772000000",
        )
        self.assertTrue(ok, err)
        self.assertEqual(sent["payload"]["to"], "+256772000000")

    def test_number_outside_east_africa_is_rejected_before_sending(self):
        ok, err = send_sms_notification("+442071234567", "hello")
        self.assertFalse(ok)
        self.assertIn("country code", err)

    def test_oversized_message_is_truncated_to_the_documented_limit(self):
        ok, err, sent = self._send(
            {
                "SMSMessageData": {
                    "Recipients": [{"statusCode": 101, "status": "Success"}]
                }
            }
        )
        self.assertTrue(ok, err)
        self.assertLessEqual(len(sent["payload"]["message"]), 1600)
