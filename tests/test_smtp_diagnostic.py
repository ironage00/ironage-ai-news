import unittest
from unittest.mock import MagicMock

from scripts.diagnose_smtp import diagnose


class DiagnosticTests(unittest.TestCase):
    def test_authenticates_without_sending(self):
        smtp = MagicMock()
        server = smtp.return_value.__enter__.return_value
        server.ehlo.return_value = (250, b'ok')
        self.assertTrue(diagnose('sender', 'password', smtp))
        server.login.assert_called_once_with('sender', 'password')
        server.sendmail.assert_not_called()
        server.send_message.assert_not_called()

    def test_connection_failure(self):
        smtp = MagicMock(side_effect=OSError('private error'))
        self.assertFalse(diagnose('sender', 'password', smtp))

    def test_auth_failure(self):
        smtp = MagicMock()
        server = smtp.return_value.__enter__.return_value
        server.ehlo.return_value = (250, b'ok')
        server.login.side_effect = OSError('private error')
        self.assertFalse(diagnose('sender', 'password', smtp))
        server.sendmail.assert_not_called()

    def test_missing_credentials(self):
        smtp = MagicMock()
        self.assertFalse(diagnose('', '', smtp))
        smtp.assert_not_called()


if __name__ == '__main__':
    unittest.main()
