from django.test import SimpleTestCase

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
