import unittest
import io
import smtplib
from contextlib import redirect_stdout
from unittest.mock import MagicMock

from scripts.diagnose_smtp import describe_credentials, diagnose, diagnose_with_retry


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

    def test_response_reports_code_without_server_text(self):
        smtp = MagicMock()
        server = smtp.return_value.__enter__.return_value
        server.ehlo.return_value = (250, b'ok')
        server.esmtp_features = {'auth': 'PLAIN LOGIN'}
        server.login.side_effect = smtplib.SMTPAuthenticationError(535, b'5.7.8 secret text')
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertFalse(diagnose('sender', 'password', smtp))
        self.assertIn('535', output.getvalue())
        self.assertIn('5.7.8', output.getvalue())
        self.assertNotIn('secret text', output.getvalue())

    def test_describes_credential_shape_without_values(self):
        good = '\n'.join(describe_credentials('me@gmail.com', 'abcdefghijklmnop'))
        self.assertIn('16 lowercase letters): yes', good)
        self.assertIn('Password whitespace: none', good)
        self.assertIn('Sender domain: gmail.com', good)
        self.assertNotIn('abcdefghijklmnop', good)
        self.assertNotIn('me@', good)
        spaced = '\n'.join(describe_credentials(' me@corp.example ', 'abcd efgh ijkl mnop\n'))
        self.assertIn('Password length: 20 (without whitespace: 16)', spaced)
        self.assertIn('Password whitespace: inside', spaced)
        self.assertIn('Sender whitespace: leading/trailing', spaced)
        self.assertIn('custom domain', spaced)
        self.assertNotIn('corp.example', spaced)
        self.assertIn('): NO', '\n'.join(describe_credentials('me@gmail.com', 'MyRealPassw0rd!')))

    def _factory(self, accepted_password):
        smtp = MagicMock()
        server = smtp.return_value.__enter__.return_value
        server.ehlo.return_value = (250, b'ok')
        server.esmtp_features = {'auth': 'PLAIN LOGIN'}

        def login(user, password):
            if password != accepted_password:
                raise smtplib.SMTPAuthenticationError(535, b'5.7.8 rejected')
        server.login.side_effect = login
        return smtp, server

    def test_retry_reports_when_whitespace_is_the_problem(self):
        smtp, server = self._factory('abcdefghijklmnop')
        output = io.StringIO()
        with redirect_stdout(output):
            # 등록된 값 그대로는 실패이므로 결과는 False(시크릿을 고쳐야 한다는 뜻)
            self.assertFalse(diagnose_with_retry('me@corp.example', 'abcd efgh ijkl mnop', smtp))
        self.assertIn('Retry without whitespace: OK', output.getvalue())
        self.assertEqual(server.login.call_count, 2)
        server.sendmail.assert_not_called()

    def test_retry_reports_when_whitespace_is_not_the_cause(self):
        smtp, server = self._factory('something-else')
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertFalse(diagnose_with_retry('me@corp.example', 'abcd efgh ijkl mnop', smtp))
        self.assertIn('Retry without whitespace: FAILED', output.getvalue())

    def test_no_retry_when_password_has_no_whitespace(self):
        smtp, server = self._factory('something-else')
        with redirect_stdout(io.StringIO()):
            self.assertFalse(diagnose_with_retry('me@corp.example', 'abcdefghijklmnop', smtp))
        self.assertEqual(server.login.call_count, 1)


if __name__ == '__main__':
    unittest.main()
