#!/usr/bin/env python3
"""
XR3 measurement probe -- read-only, Festiflow guide round XR3 (2026-10-21).

    python -I guide/xr3/probe_xr3.py inventory     # secret NAMES + token shapes; no API call

WHAT IT MAY DO
  GET on api.shotgun.live, POST GraphQL *queries* (never a mutation) on DICE.

WHAT IT MAY PRINT OR COMMIT (ticketing_api is PUBLIC, so are its Actions logs)
  Field NAMES, COUNTS, timings, event ids, event names (public marketing names),
  event dates, HTTP status codes. NEVER a token, a header, an organiser secret, a
  URL (a Shotgun URL carries its token), a personal value, or a MONEY TOTAL.
  Money goes to guide/xr3/private/ only, which seal.sh encrypts to a key held by
  the measurement seat and deletes; it is never printed, logged or committed.
  Every string that leaves this process goes through scrub().

Secrets arrive as one JSON object (SECRETS_JSON = toJSON(secrets)). Only keys
starting SHOTGUN_ or DICE_ are kept; the rest are dropped at once.
Stdlib only.
"""

import base64
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / 'out'
PRIV = HERE / 'private'
OUT.mkdir(parents=True, exist_ok=True)

KNOWN_ORGS = {'171835': 'episode', '207784': 'sonora'}


def _load_secrets():
    raw = os.environ.pop('SECRETS_JSON', '') or '{}'
    try:
        allv = json.loads(raw)
    except ValueError:
        allv = {}
    names = sorted(allv)
    keep = {k: str(v).strip() for k, v in allv.items() if re.match(r'(SHOTGUN|DICE)_', k)}
    del allv, raw
    return names, keep


SECRET_NAMES, SEC = _load_secrets()
SECRETS = sorted({v for v in SEC.values() if v and len(v) >= 4}, key=len, reverse=True)

_PATTERNS = [
    (re.compile(r'(?i)(token|key|api_key)=[^&\s"\']+'), r'\1=***'),
    (re.compile(r'(?i)bearer\s+\S+'), 'Bearer ***'),
    (re.compile(r'eyJ[\w-]{5,}\.[\w-]{5,}\.[\w-]*'), '<jwt>'),
    (re.compile(r'[\w.+-]+@[\w-]+\.[\w.-]+'), '<email>'),
    (re.compile(r'https?://\S+'), '<url>'),
    (re.compile(r'[A-Za-z0-9_\-]{40,}'), '<opaque>'),
]


def scrub(text):
    s = str(text)
    for sec in SECRETS:
        s = s.replace(sec, '***')
    for rx, rep in _PATTERNS:
        s = rx.sub(rep, s)
    return s


LOG = []


def out(*parts):
    line = scrub(' '.join(str(p) for p in parts))
    LOG.append(line)
    print(line, flush=True)


PRIVATE = {}


def private(key, value):
    """Money: kept for the sealed file only. Never printed."""
    PRIVATE[key] = value


def token_shape(name, tok):
    r = {'name': name, 'set': bool(tok)}
    if not tok:
        return r
    r['length'] = len(tok)
    r['segments_on_dot'] = tok.count('.') + 1
    r['charset'] = ''.join(sorted({('A' if c.isupper() else 'a' if c.islower() else '9' if c.isdigit() else c)
                                   for c in tok}))
    r['numeric'] = tok.isdigit()
    if tok.isdigit():
        r['equals_known_org'] = KNOWN_ORGS.get(tok, 'no (not printed)')
    parts = tok.split('.')
    if len(parts) == 3:
        def dec(p):
            p += '=' * (-len(p) % 4)
            return json.loads(base64.urlsafe_b64decode(p.encode()).decode())
        try:
            pl = dec(parts[1])
            claims = {}
            for k, v in pl.items():
                if k in ('exp', 'iat', 'nbf') and isinstance(v, (int, float)):
                    claims[k] = datetime.fromtimestamp(v, timezone.utc).strftime('%Y-%m-%d')
                else:
                    claims[k] = f'<{type(v).__name__}>'
            r['jwt_claims'] = claims
            org = str(pl.get('organizerId', ''))
            r['organizerId_is'] = KNOWN_ORGS.get(org, 'another organiser (not printed)' if org else 'absent')
        except Exception:
            r['jwt_claims'] = 'undecodable'
    return r


def inventory():
    out('\n## Secret inventory (names only)')
    out('repository secret names: ' + json.dumps(SECRET_NAMES))
    res = {'secret_names': SECRET_NAMES, 'shapes': []}
    for k in sorted(SEC):
        sh = token_shape(k, SEC[k])
        res['shapes'].append(sh)
        out(json.dumps(sh, sort_keys=True))
    # one sealed test value, to prove the private channel end to end
    private('seal_test', {'value_cents': 4242})
    return res


def main(which):
    started = datetime.now(timezone.utc)
    result = {'probe': 'XR3', 'part': which, 'started_utc': started.strftime('%Y-%m-%dT%H:%MZ')}
    out(f'# XR3 probe · {which} · {result["started_utc"]}')
    if which == 'inventory':
        result['inventory'] = inventory()
    result['wall_seconds'] = round((datetime.now(timezone.utc) - started).total_seconds())
    (OUT / f'xr3_{which}.json').write_text(scrub(json.dumps(result, indent=1, ensure_ascii=False, default=str)),
                                           encoding='utf-8')
    (OUT / f'xr3_{which}.log').write_text('\n'.join(LOG) + '\n', encoding='utf-8')
    if PRIVATE:
        PRIV.mkdir(parents=True, exist_ok=True)
        (PRIV / f'xr3_{which}_money.json').write_text(json.dumps(PRIVATE, indent=1, ensure_ascii=False), encoding='utf-8')
        out(f'private: {len(PRIVATE)} key(s) written for sealing (values not printed)')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else 'inventory'))
