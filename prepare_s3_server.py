#!/usr/bin/env python3
"""
prepare_s3_server.py - Servidor S3 minimalista para servir arquivos Parquet.
Uso: python prepare_s3_server.py /data/parquet 8000
"""

import os, sys, re, urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler

PARQUET_DIR = sys.argv[1] if len(sys.argv) > 1 else "/data/parquet"
PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 8000

os.chdir(PARQUET_DIR)

class S3Handler(BaseHTTPRequestHandler):
    def _send_xml(self, code, xml):
        self.send_response(code)
        self.send_header("Content-Type", "application/xml")
        self.end_headers()
        self.wfile.write(xml.encode())

    def _key(self):
        path = urllib.parse.urlparse(self.path).path
        parts = path.strip("/").split("/", 1)
        return parts[1] if len(parts) > 1 else (parts[0] if parts[0] else None)

    def _parse_range(self):
        r = self.headers.get("Range", "")
        m = re.match(r"bytes=(\d+)-(\d*)", r)
        if m:
            return (int(m.group(1)), int(m.group(2)) if m.group(2) else None)
        return None

    def _serve_file(self, fpath, range_spec=None):
        size = os.path.getsize(fpath)
        if range_spec:
            start, end = range_spec
            if end is None or end >= size:
                end = size - 1
            length = end - start + 1
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.send_header("Content-Length", str(length))
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Type", "application/octet-stream")
            self.end_headers()
            with open(fpath, "rb") as f:
                f.seek(start)
                remaining = length
                while remaining > 0:
                    chunk = f.read(min(65536, remaining))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)
        else:
            self.send_response(200)
            self.send_header("Content-Length", str(size))
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Type", "application/octet-stream")
            self.end_headers()
            with open(fpath, "rb") as f:
                while True:
                    c = f.read(65536)
                    if not c:
                        break
                    self.wfile.write(c)

    def do_HEAD(self):
        key = self._key()
        fpath = os.path.join(os.getcwd(), key) if key else None
        if not fpath or not os.path.isfile(fpath):
            return self._send_xml(404, "NoSuchKey")
        size = os.path.getsize(fpath)
        self.send_response(200)
        self.send_header("Content-Length", str(size))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Type", "application/octet-stream")
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path in ("/", ""):
            return self._send_xml(200, '<?xml version="1.0"?><ListAllMyBucketsResult><Buckets><Bucket><Name>data</Name></Bucket></Buckets></ListAllMyBucketsResult>')
        key = self._key()
        if key is None:
            files = "".join(f"<Contents><Key>{f}</Key><Size>{os.path.getsize(f)}</Size></Contents>" for f in sorted(os.listdir(".")) if os.path.isfile(f))
            return self._send_xml(200, f'<?xml version="1.0"?><ListBucketResult>{files}</ListBucketResult>')
        fpath = os.path.join(os.getcwd(), key)
        if not os.path.isfile(fpath):
            return self._send_xml(404, "NoSuchKey")
        try:
            self._serve_file(fpath, self._parse_range())
        except (BrokenPipeError, ConnectionResetError):
            pass

    def log_message(self, format, *args):
        pass  # silencia logs do servidor

HTTPServer(("0.0.0.0", PORT), S3Handler).serve_forever()
