#!/usr/bin/env python3
"""Offline Node.js October 2026 release comparator; Python stdlib only.

Does not import projects, install packages, make network requests, or decode data.
Copyright 2026. Licensed under Apache-2.0; see LICENSE.
"""
import argparse
import datetime
import json
import math
import os
import re
import shutil
import subprocess
import sys

VERSION = "1.0.2"
FACTS_DATE = "2026-10-22"
ADVISORY = "https://nodejs.org/en/blog/vulnerability/october-2026-security-releases"
FIXED = {22: (22, 23, 4), 24: (24, 22, 1), 26: (26, 12, 1)}
# Explicit snapshot list, never assume future or unlisted major versions are safe.
EOL_MAJORS = frozenset(range(0, 22)) | {23, 25}
CODES = {"version_fixed": 0, "below_fixed": 1, "eol_review": 3, "unknown": 3}
CVE_LINES = {
    "CVE-2026-111497": [22, 24, 26],
    "CVE-2026-105482": [22, 24, 26],
    "CVE-2026-105483": [24, 26],
    "CVE-2026-106069": [22, 24, 26],
    "CVE-2026-105481": [22, 24, 26],
    "CVE-2026-106072": [22, 24, 26],
    "CVE-2026-106074": [22, 24, 26],
    "CVE-2026-106070": [26],
    "CVE-2026-106071": [26],
    "CVE-2026-106073": [22, 24, 26],
}


def classify(version):
    match = re.fullmatch(r"v?(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(\+[0-9A-Za-z.-]+)?", version or "")
    if not match or len(version) > 200:
        return {"status": "unknown", "fixed_version": None, "major": None,
                "reason": "Need an exact stable Node.js version; ranges, prereleases and vendor suffixes need review"}
    parts = tuple(int(n) for n in match.groups()[:3])
    major = parts[0]
    target = FIXED.get(major)
    if target:
        return {"status": "version_fixed" if parts >= target else "below_fixed",
                "fixed_version": ".".join(map(str, target)), "major": major,
                "reason": "Meets this release baseline; serving process and linked libraries still need verification"
                if parts >= target else "Below this release baseline; check vendor backports or update"}
    return {"status": "eol_review" if major in EOL_MAJORS else "unknown",
            "fixed_version": None, "major": major,
            "reason": "EOL line: migrate or verify vendor support and patches" if major in EOL_MAJORS
            else "Major version absent from this advisory snapshot"}


class SafeParser(argparse.ArgumentParser):
    def error(self, message):
        # argparse otherwise echoes unknown arguments, possibly containing secrets.
        self.exit(2, "Invalid arguments. Use --help for accepted input.\n")


def main(argv=None):
    parser = SafeParser(description="Node.js October 2026 version check. Exit 0 is NOT a service-safe verdict.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--version-string", help="exact observed Node.js version; no executable is run")
    mode.add_argument("--local", action="store_true", help="run only the selected node --version")
    parser.add_argument("--node", help="trusted executable path; requires --local")
    parser.add_argument("--timeout", type=float, default=10, help="local process timeout, >0 and <=60 seconds")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--version", action="version", version=VERSION)
    args = parser.parse_args(argv)
    if args.node is not None and (not args.local or not args.node.strip()):
        parser.error("--node requires --local")
    if not math.isfinite(args.timeout) or not 0 < args.timeout <= 60:
        parser.error("invalid timeout")
    if args.version_string is not None and (len(args.version_string) > 200 or not args.version_string
                                            or re.search(r"[\s\x00-\x1f\x7f]", args.version_string)):
        parser.error("invalid version token")

    version = args.version_string
    failure = None
    if args.local:
        executable = args.node or shutil.which("node")
        if not executable:
            failure = "Node executable not found; no conclusion"
        else:
            env = os.environ.copy()
            env.pop("NODE_OPTIONS", None)
            env.pop("NODE_PATH", None)
            try:
                # No shell, no eval, no require/import, no package lifecycle hooks.
                result = subprocess.run([executable, "--version"], stdin=subprocess.DEVNULL,
                                        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                        timeout=args.timeout, env=env, check=False)
                if result.returncode != 0:
                    failure = "Node version command failed; no conclusion"
                elif len(result.stdout) > 4096:
                    failure = "Unexpected version output; no conclusion"
                else:
                    version = result.stdout.decode("utf-8", errors="strict").strip()
            except subprocess.TimeoutExpired:
                failure = "Node version command timed out; no conclusion"
            except (OSError, UnicodeError):
                failure = "Unable to read selected Node executable; no conclusion"

    verdict = classify(version)
    if failure:
        verdict = {"status": "unknown", "fixed_version": None, "major": None, "reason": failure}
    major = verdict.pop("major")
    # Never echo arbitrary executable output or invalid user tokens.
    observed = version if major is not None else None
    report = {"schema_version": 1, "tool_version": VERSION,
              "checked_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
              "facts_as_of": FACTS_DATE, "advisory": ADVISORY,
              "node_version": observed, **verdict,
              "evidence_scope": "local_binary_only" if args.local else "provided_version_only",
              "service_patch_status": "not_verified", "brotli_linkage": "not_verified",
              "cves_for_known_line": [cve for cve, lines in CVE_LINES.items() if major in lines],
              "limitations": [
                  "CVE list is this advisory's supported-line mapping, not proof of reachability or compromise.",
                  "An empty CVE list on EOL/unknown versions does not mean unaffected.",
                  "Vendor backports and dynamically linked Brotli require package and runtime evidence.",
                  "A new CLI process does not prove which Node build existing workers use.",
                  "No network scan, exploit test, project execution or dependency audit is performed.",
              ]}
    report["exit_code"] = CODES[report["status"]]
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"{report['status'].upper()}: {report['reason']}")
        print(f"Scope: {report['evidence_scope']}. Service patch status: NOT VERIFIED.")
    return report["exit_code"]


if __name__ == "__main__":
    sys.exit(main())
