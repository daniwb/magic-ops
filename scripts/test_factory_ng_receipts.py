"""Receipt publication must survive failed writes without corrupting history."""
import errno
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import factory_ng_receipts as receipts


class ReceiptPublicationTest(unittest.TestCase):
    def test_readers_only_see_complete_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'receipt.json'
            value = {'schema': 'factory.observation-receipt/v1', 'outcome': 'gate_failed'}
            real_link = receipts.os.link

            def publish(source, destination):
                self.assertFalse(path.exists())
                self.assertEqual(list(path.parent.glob('*.json')), [])
                self.assertEqual(json.loads(Path(source).read_text()), value)
                real_link(source, destination)

            with mock.patch.object(receipts.os, 'link', side_effect=publish):
                receipts.write_receipt(path, value)
            self.assertEqual(json.loads(path.read_text()), value)
            self.assertEqual(list(path.parent.iterdir()), [path])

    def test_disk_full_does_not_publish_empty_or_partial_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'receipt.json'
            with mock.patch.object(receipts.os, 'fsync', side_effect=OSError(errno.ENOSPC, 'disk full')):
                with self.assertRaises(OSError):
                    receipts.write_receipt(path, {'outcome': 'gate_failed'})
            self.assertFalse(path.exists())
            self.assertEqual(list(path.parent.iterdir()), [])

    def test_collision_preserves_existing_immutable_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'receipt.json'
            original = '{"outcome":"gate_failed"}\n'
            path.write_text(original)
            with self.assertRaises(FileExistsError):
                receipts.write_receipt(path, {'outcome': 'accepted'})
            self.assertEqual(path.read_text(), original)
            self.assertEqual(list(path.parent.iterdir()), [path])


if __name__ == '__main__':
    unittest.main()
