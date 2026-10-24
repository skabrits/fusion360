import hashlib
import http.server
import importlib.util
import pathlib
import socket
import subprocess
import tarfile
import tempfile
import threading
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('seed', ROOT / 'bin/fusion-seed.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class SeedTests(unittest.TestCase):
    def test_seed_preserves_existing_and_rejects_partial_or_corruption(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            factory = root / 'factory'
            factory.mkdir()
            source = root / 'source/.autodesk_fusion'
            prefix = source / 'wineprefixes/default'
            (prefix / 'drive_c/app').mkdir(parents=True)
            (prefix / 'system.reg').write_text('registry')
            for name in ['Fusion360.exe', 'AdskIdentityManager.exe']:
                (prefix / 'drive_c/app' / name).write_bytes(b'MZtest')
            (prefix / 'dosdevices').mkdir()
            (prefix / 'dosdevices/c:').symlink_to('../drive_c')
            archive = factory / 'prefix.tar.gz'
            with tarfile.open(archive, 'w:gz') as tar:
                tar.add(source, arcname='.autodesk_fusion')
            checksum = factory / 'prefix.tar.gz.sha256'
            checksum.write_text(hashlib.sha256(archive.read_bytes()).hexdigest() + '  prefix.tar.gz\n')
            config = root / 'config'
            config.mkdir()
            module.seed(config, factory)
            installed = config / '.autodesk_fusion'
            self.assertTrue(module.has_install(installed))
            self.assertTrue((installed / 'wineprefixes/default/dosdevices/c:').is_symlink())
            marker = installed / 'user-login-marker'
            marker.write_text('keep')
            module.seed(config, factory)
            self.assertEqual(marker.read_text(), 'keep')
            partial = root / 'partial'
            (partial / '.autodesk_fusion').mkdir(parents=True)
            with self.assertRaisesRegex(RuntimeError, 'incomplete'):
                module.seed(partial, factory)
            empty = root / 'empty'
            empty.mkdir()
            checksum.write_text('0' * 64)
            with self.assertRaisesRegex(RuntimeError, 'checksum'):
                module.seed(empty, factory)
            self.assertEqual(list(empty.iterdir()), [])

    def test_download_resumes_and_reuses_verified_cache(self):
        payload = b'MZ' + b'x' * 262142
        offsets = []

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                offset = int(self.headers.get('Range', 'bytes=0-')[6:-1])
                offsets.append(offset)
                self.send_response(206 if offset else 200)
                self.send_header('Content-Length', str(len(payload) - offset))
                if offset:
                    self.send_header('Content-Range', f'bytes {offset}-{len(payload)-1}/{len(payload)}')
                self.end_headers()
                if len(offsets) == 1:
                    self.wfile.write(payload[:65536])
                    self.wfile.flush()
                    self.connection.shutdown(socket.SHUT_RDWR)
                    self.connection.close()
                else:
                    self.wfile.write(payload[offset:])

        server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                dest = pathlib.Path(tmp) / 'setup.exe'
                cmd = ['bash', str(ROOT / 'bin/fusion-fetch'), f'http://127.0.0.1:{server.server_port}/setup.exe', str(dest)]
                subprocess.run(cmd, check=True, capture_output=True, timeout=25)
                self.assertEqual(dest.read_bytes(), payload)
                self.assertEqual(offsets, [0, 65536])
                subprocess.run(cmd, check=True, capture_output=True, timeout=10)
                self.assertEqual(len(offsets), 2)
                dest.write_bytes(b'corrupt')
                subprocess.run(cmd, check=True, capture_output=True, timeout=10)
                self.assertEqual(dest.read_bytes(), payload)
                self.assertEqual(offsets[-1], 0)
        finally:
            server.shutdown()
            server.server_close()


if __name__ == '__main__':
    unittest.main()
