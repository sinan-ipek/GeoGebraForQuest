#!/usr/bin/env python3
"""Exp34 compatibility gate: cookie authentication is disabled.

This historical file is still called by build-geogebra-quest.sh, but Exp34 uses
one session authority only: GeoGebra's real OAuth login token. The old Exp33
`logincookie` source branch must therefore NOT be installed.

The Exp22 READY/SUCCESS handshake remains the only Quest-specific LoginOperationW
extension. Android Exp34 obtains a real token either from the trusted ggtcallback
or from the authenticated remote GeoGebra page's own WebStorage `token` entry.
"""

from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit("usage: patch-geogebra-quest-v0934.py <geogebra-source-root>")

root = Path(sys.argv[1]).resolve()
path = root / (
    "source/web/web/src/main/java/org/geogebra/web/shared/ggtapi/"
    "LoginOperationW.java"
)
text = path.read_text(encoding="utf-8")

if "GGQ_EXP22_LOGIN_READY_ACK" not in text:
    raise RuntimeError("exp34 requires Exp22 login READY/SUCCESS handshake")

for forbidden in (
    '"logincookie".equals(action)',
    "GGQ_EXP33_COOKIE_AUTH_SEMANTICS",
    "new GeoGebraTubeUser(null, ggqPendingLoginToken)",
):
    if forbidden in text:
        raise RuntimeError(f"exp34 cookie-auth source residue present: {forbidden}")

if '"logintoken".equals(action)' not in text:
    raise RuntimeError("exp34 OAuth token message path missing")
if "performTokenLogin(ggqPendingLoginToken, false)" not in text:
    raise RuntimeError("exp34 Exp22 token login path missing")

print("[GGQ] exp34 token-first source gate: cookie authentication disabled")
