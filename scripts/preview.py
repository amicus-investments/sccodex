#!/usr/bin/env python3
"""Serve the documentation locally, with byte ranges for browser media seeking."""

import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


class MediaHandler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Accept-Ranges", "bytes")
        super().end_headers()

    def send_head(self):
        self.remaining = None
        requested = self.headers.get("Range")
        path = Path(self.translate_path(self.path))
        if not requested or not path.is_file() or self.headers.get("If-Range"):
            return super().send_head()
        match = re.fullmatch(r"bytes=(\d*)-(\d*)", requested.strip())
        stream = path.open("rb")
        size = path.stat().st_size
        start, end = 0, size - 1
        if match and any(match.groups()):
            first, last = match.groups()
            if first:
                start = int(first)
                end = min(int(last), end) if last else end
            else:
                start = max(0, size - int(last))
                if int(last) == 0:
                    start = size
        if not match or not any(match.groups()) or not 0 <= start <= end < size:
            stream.close()
            self.send_response(416)
            self.send_header("Content-Range", f"bytes */{size}")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return None
        self.send_response(206)
        self.send_header("Content-Type", self.guess_type(str(path)))
        self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.send_header("Content-Length", str(end - start + 1))
        self.send_header("Last-Modified", self.date_time_string(path.stat().st_mtime))
        self.end_headers()
        stream.seek(start)
        self.remaining = end - start + 1
        return stream

    def copyfile(self, source, outputfile):
        if self.remaining is None:
            return super().copyfile(source, outputfile)
        while self.remaining:
            data = source.read(min(65536, self.remaining))
            if not data:
                break
            outputfile.write(data)
            self.remaining -= len(data)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    with ThreadingHTTPServer(("127.0.0.1", args.port), partial(MediaHandler, directory=str(ROOT))) as server:
        print(f"SCCodex preview: http://127.0.0.1:{args.port}/docs/", flush=True)
        print("Press Ctrl+C to stop. No Codex hooks or settings are changed.", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
