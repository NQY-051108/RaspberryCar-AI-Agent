#!/usr/bin/env python3
"""Offline tests for the stream client's length-prefixed socket reader."""
import socket
import unittest

from realtime_stream_client import recv_exact


class ReceiveExactTests(unittest.TestCase):
    def test_receives_partial_chunks(self):
        reader, writer = socket.socketpair()
        try:
            writer.sendall(b"ab")
            writer.sendall(b"cde")
            self.assertEqual(recv_exact(reader, 5), b"abcde")
        finally:
            reader.close()
            writer.close()

    def test_peer_close_returns_none(self):
        reader, writer = socket.socketpair()
        writer.close()
        try:
            self.assertIsNone(recv_exact(reader, 4))
        finally:
            reader.close()


if __name__ == "__main__":
    unittest.main()
