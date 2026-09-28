from datetime import date

from django.test import SimpleTestCase

from queueapp.notifications import (
    SMS_POLL_SECONDS,
    SMS_TERMINAL_FAILURES,
    SMS_TERMINAL_SUCCESSES,
    build_approval_sms,
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
    The gateway phone/carrier began rejecting every 2-part (multipart) message
    on 2026-07-20 with Android RESULT_ERROR_GENERIC_FAILURE, while continuing to
    deliver every 1-part message. These tests stop the approval SMS from ever
    growing back into a second segment.
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


class MySmsGateStatusReportingTests(SimpleTestCase):
    """
    A 202 from the gateway only means 'queued for sending'. Treating
    'sending'/'pending' as success made the desk display a green tick for
    messages the carrier later failed. Only terminal states may report success.
    """

    def test_in_flight_states_are_not_terminal_successes(self):
        for state in ("sending", "pending", ""):
            self.assertNotIn(state, SMS_TERMINAL_SUCCESSES)

    def test_delivered_states_are_terminal_successes(self):
        for state in ("sent", "delivered"):
            self.assertIn(state, SMS_TERMINAL_SUCCESSES)

    def test_failure_states_are_terminal_failures(self):
        for state in ("failed", "error"):
            self.assertIn(state, SMS_TERMINAL_FAILURES)

    def test_failure_and_success_vocabularies_do_not_overlap(self):
        self.assertEqual(
            set(SMS_TERMINAL_SUCCESSES) & set(SMS_TERMINAL_FAILURES), set()
        )

    def test_poll_window_is_long_enough_for_a_queued_send(self):
        self.assertGreaterEqual(SMS_POLL_SECONDS, 10)

