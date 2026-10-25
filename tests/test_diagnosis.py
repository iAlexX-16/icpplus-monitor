import unittest

from diagnose_connection import public_url


class DiagnosticPrivacyTests(unittest.TestCase):
    def test_session_and_query_are_not_in_report_urls(self):
        url = "https://example.org/icpplustiem/acEntrada;jsessionid=PRIVATE_SESSION?token=SECRET#data"
        self.assertEqual(public_url(url), "https://example.org/icpplustiem/acEntrada")


if __name__ == "__main__":
    unittest.main()
