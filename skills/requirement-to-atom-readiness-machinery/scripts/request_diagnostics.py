"""Bounded loopback OTLP/JSON collector. Persist metadata, never raw exports."""
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import threading
import time
from socketserver import TCPServer
from urllib.parse import urlsplit

MAX_BODY = 1048576
MAX_LOG = 131072
EVENTS = {'codex.api_request', 'codex.sse_event', 'codex.websocket_request',
          'codex.websocket_event', 'codex.conversation_starts', 'codex.startup_phase'}
COUNTERS = {'attempt', 'duration_ms', 'http.response.status_code'}
LABELS = {'event.kind', 'startup.phase', 'startup.status'}


def scalar(value):
    if not isinstance(value, dict) or len(value) != 1:
        return None
    for key in ('stringValue', 'intValue', 'boolValue'):
        if key in value:
            return value[key]
    return None


def sanitize(item):
    attrs = {a.get('key'): scalar(a.get('value')) for a in item.get('attributes', []) if isinstance(a, dict)}
    event = attrs.get('event.name')
    if event not in EVENTS:
        return None
    result = {'event': event}
    for key in COUNTERS:
        value = attrs.get(key)
        if type(value) is int and 0 <= value < 10**12:
            result[key] = value
        elif type(value) is str and re.fullmatch(r'[0-9]{1,12}', value):
            result[key] = int(value)
    for key in LABELS:
        value = attrs.get(key)
        if type(value) is str and re.fullmatch(r'[a-zA-Z0-9_.-]{1,80}', value):
            result[key] = value
    if type(attrs.get('success')) is bool:
        result['success'] = attrs['success']
    endpoint = attrs.get('endpoint')
    if type(endpoint) is str:
        # Persist only a fixed classification, never a URL, host, query or ID.
        path = urlsplit(endpoint).path.rstrip('/')
        result['endpoint_class'] = 'responses' if path.endswith('/responses') else 'other'
    errors = [value for key, value in attrs.items() if isinstance(key, str) and 'error' in key and value not in (None, '', False)]
    result['error_present'] = bool(errors)
    if errors:
        result['error_fingerprint'] = hashlib.sha256(json.dumps(errors, sort_keys=True).encode()).hexdigest()
    return result


def settings(port):
    if type(port) is not int or not 0 < port < 65536:
        raise ValueError('collector port must be a bound loopback port')
    return ['otel.log_user_prompt=false', 'otel.metrics_exporter="none"',
            'otel.trace_exporter="none"',
            f'otel.exporter={{otlp-http={{endpoint="http://127.0.0.1:{port}/v1/logs",protocol="json"}}}}']


def validate_metadata(raw):
    allowed = {'event', 'received_elapsed_ms', 'error_present', 'error_fingerprint',
               'success', 'endpoint_class', *COUNTERS, *LABELS}
    rows = [json.loads(line) for line in raw.splitlines()]
    for row in rows:
        if type(row) is not dict or set(row) - allowed or not {'event', 'received_elapsed_ms', 'error_present'} <= set(row):
            raise ValueError('request metadata has missing or forbidden fields')
        if row['event'] not in EVENTS or type(row['error_present']) is not bool:
            raise ValueError('request metadata event or error flag is invalid')
        for key in COUNTERS | {'received_elapsed_ms'}:
            if key in row and (type(row[key]) is not int or not 0 <= row[key] < 10**12):
                raise ValueError('request metadata counter is invalid')
        for key in LABELS:
            if key in row and (type(row[key]) is not str or not re.fullmatch(r'[a-zA-Z0-9_.-]{1,80}', row[key])):
                raise ValueError('request metadata label is invalid')
        if 'success' in row and type(row['success']) is not bool:
            raise ValueError('request metadata success flag is invalid')
        if 'endpoint_class' in row and row['endpoint_class'] not in ('responses', 'other'):
            raise ValueError('request metadata endpoint classification is invalid')
        if row['error_present'] != ('error_fingerprint' in row):
            raise ValueError('request metadata error fingerprint is missing or spurious')
        if 'error_fingerprint' in row and (type(row['error_fingerprint']) is not str or not re.fullmatch('[0-9a-f]{64}', row['error_fingerprint'])):
            raise ValueError('request metadata error fingerprint is invalid')
    return len(rows)


class LoopbackServer(ThreadingHTTPServer):
    def server_bind(self):
        # No DNS is necessary for an explicitly numeric, loopback-only listener.
        TCPServer.server_bind(self)
        self.server_name = '127.0.0.1'
        self.server_port = self.server_address[1]


class Collector:
    def __init__(self, path):
        self.path = Path(path)
        self.fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        self.started = time.monotonic()
        self.lock = threading.Lock()
        self.bytes = 0
        self.count = 0
        self.failure = None
        self.last_event = None
        self.closed = False
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *unused):
                pass

            def do_POST(self):
                self.connection.settimeout(2)
                try:
                    size = int(self.headers.get('Content-Length', '0'))
                    if self.path != '/v1/logs' or not 0 < size <= MAX_BODY:
                        raise ValueError('invalid OTLP endpoint or bounded body length')
                    payload = json.loads(self.rfile.read(size))
                    owner.consume(payload)
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/json')
                    self.send_header('Content-Length', '2')
                    self.end_headers()
                    self.wfile.write(b'{}')
                except (ValueError, TypeError, KeyError, OSError, AttributeError):
                    owner.failure = 'collector rejected malformed or oversized telemetry'
                    self.send_error(400)

        try:
            self.server = LoopbackServer(('127.0.0.1', 0), Handler)
        except BaseException:
            os.close(self.fd)
            raise
        # Bounded socket reads allow close to drain handlers before sealing files.
        self.server.daemon_threads = False
        self.thread = threading.Thread(target=lambda: self.server.serve_forever(poll_interval=.05), daemon=True)
        self.thread.start()

    def consume(self, payload):
        if not isinstance(payload, dict):
            raise ValueError('OTLP export must be an object')
        for resource in payload.get('resourceLogs', []):
            for scope in resource.get('scopeLogs', []):
                for item in scope.get('logRecords', []):
                    row = sanitize(item)
                    if row is None:
                        continue
                    row['received_elapsed_ms'] = int((time.monotonic() - self.started) * 1000)
                    raw = (json.dumps(row, sort_keys=True) + '\n').encode()
                    with self.lock:
                        if self.closed:
                            raise ValueError('collector is closed')
                        if self.bytes + len(raw) > MAX_LOG:
                            self.failure = 'collector metadata byte limit exceeded'
                            raise ValueError(self.failure)
                        os.write(self.fd, raw)
                        os.fsync(self.fd)
                        self.bytes += len(raw)
                        self.count += 1
                        self.last_event = row

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        with self.lock:
            os.close(self.fd)
            self.closed = True

    def summary(self):
        with self.lock:
            return {'schema_version': 1, 'record_count': self.count,
                    'metadata_sha256': hashlib.sha256(self.path.read_bytes()).hexdigest(),
                    'collector_failure': self.failure}
