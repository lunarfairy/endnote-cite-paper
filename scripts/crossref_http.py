"""Bounded Crossref JSON retrieval; transport recovery is not verification."""
import http.client
import json
import sys
import urllib.error
import urllib.request


def validate_response(data):
    if not isinstance(data, dict) or not isinstance(data.get('message'), dict):
        raise ValueError('Crossref response must contain a message object')
    return data


def fetch_json(url, timeout=25, attempts=2, audit=None):
    if attempts < 1:
        raise ValueError('attempts must be positive')
    for attempt in range(1, attempts + 1):
        try:
            request = urllib.request.Request(url, headers={'User-Agent': 'endnote-cite-paper/1.1'})
            recovered = False
            with urllib.request.urlopen(request, timeout=timeout) as response:
                try:
                    raw = response.read()
                except http.client.IncompleteRead as exc:
                    raw = exc.partial
                    recovered = True
            data = validate_response(json.loads(raw.decode('utf-8')))
            if recovered:
                event = {'url': url, 'attempt': attempt, 'status': 'complete_json_recovered_from_incomplete_read'}
                if audit is not None:
                    audit.append(event)
                print(json.dumps(event), file=sys.stderr)
            return data
        except (ValueError, UnicodeError, urllib.error.URLError, TimeoutError, http.client.HTTPException) as exc:
            event = {'url': url, 'attempt': attempt, 'status': 'fetch_failed', 'error': str(exc)}
            if audit is not None:
                audit.append(event)
            print(json.dumps(event), file=sys.stderr)
            if attempt == attempts:
                raise
