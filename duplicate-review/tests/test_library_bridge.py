import errno
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock
from urllib.error import URLError
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from library_bridge import LibraryClient


class LibraryTransportTests(unittest.TestCase):
    def test_oversized_json_is_rejected_before_sending(self):
        client=LibraryClient();client.opener=Mock()
        with self.assertRaisesRegex(ValueError,'request was not sent'):
            client.request('/api/organizer/preview',{'draft':'x'*client.JSON_LIMIT})
        client.opener.open.assert_not_called()

    def test_refused_closed_and_timeout_have_distinct_actionable_messages(self):
        for failure,message in [(URLError(ConnectionRefusedError(errno.ECONNREFUSED,'refused')),'no companion is accepting'),
                                (URLError(ConnectionResetError(errno.ECONNRESET,'reset')),'closed the connection'),
                                (URLError(TimeoutError('timeout')),'180 seconds')]:
            with self.subTest(failure=failure):
                client=LibraryClient();client.opener=Mock();client.opener.open.side_effect=failure
                with self.assertRaisesRegex(ValueError,message) as raised:
                    client.request('/api/organizer/preview',{})
                self.assertIn('No images were imported by this preview',str(raised.exception))
                self.assertEqual(client.opener.open.call_args.kwargs['timeout'],180)
