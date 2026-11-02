#!/usr/bin/env python3
# SPDX-License-Identifier: MIT. Provided "as is", no warranty; use at your own risk. See LICENSE.
"""Ask a running PHP-FPM for its effective version and PHP2Shell-relevant ini values over FastCGI.

Stdlib only. Writes a tiny probe script to a world-readable temp dir, asks FPM to run it, deletes it.
Usage:
  python3 -I php-fpm-probe.py --socket /run/php/php8.3-fpm.sock
  python3 -I php-fpm-probe.py --host 127.0.0.1 --port 9000
  python3 -I php-fpm-probe.py --socket ... --script /var/www/html/probe.php   (chroot/open_basedir pools: pass a path FPM can read)
Run on the same host as FPM (the worker must be able to read the probe file).
"""
import argparse, json, os, socket, struct, sys, tempfile

PROBE = (b"<?php header('Content-Type: application/json');"
         b"echo json_encode(['php'=>PHP_VERSION,'sapi'=>PHP_SAPI,'ini'=>["
         b"'session.upload_progress.enabled'=>ini_get('session.upload_progress.enabled'),"
         b"'session.use_strict_mode'=>ini_get('session.use_strict_mode'),"
         b"'memory_limit'=>ini_get('memory_limit'),"
         b"'post_max_size'=>ini_get('post_max_size'),"
         b"'fatal_error_backtraces'=>ini_get('fatal_error_backtraces'),"
         b"'enable_post_data_reading'=>ini_get('enable_post_data_reading'),"
         b"'max_input_nesting_level'=>ini_get('max_input_nesting_level'),"
         b"'session.upload_progress.name'=>ini_get('session.upload_progress.name'),"
         b"'loaded_ini'=>php_ini_loaded_file(),'scanned_ini'=>php_ini_scanned_files()]]);")

FCGI_BEGIN, FCGI_PARAMS, FCGI_STDIN, FCGI_STDOUT, FCGI_STDERR, FCGI_END = 1, 4, 5, 6, 7, 3

def rec(t, body):
    pad = (-len(body)) % 8
    return struct.pack(">BBHHBB", 1, t, 1, len(body), pad, 0) + body + b"\0" * pad

def kv(k, v):
    k, v = k.encode(), v.encode()
    out = b""
    for s in (k, v):
        out += struct.pack(">B", len(s)) if len(s) < 128 else struct.pack(">I", len(s) | 0x80000000)
    return out + k + v

def run(conn, script):
    params = {"GATEWAY_INTERFACE": "FastCGI/1.0", "REQUEST_METHOD": "GET", "SCRIPT_FILENAME": script,
              "SCRIPT_NAME": "/" + os.path.basename(script), "REQUEST_URI": "/" + os.path.basename(script),
              "DOCUMENT_ROOT": os.path.dirname(script), "SERVER_PROTOCOL": "HTTP/1.1", "SERVER_SOFTWARE": "php2shell-probe",
              "REMOTE_ADDR": "127.0.0.1", "SERVER_ADDR": "127.0.0.1", "SERVER_PORT": "80", "SERVER_NAME": "localhost", "QUERY_STRING": ""}
    msg = rec(FCGI_BEGIN, struct.pack(">HB5x", 1, 0))
    msg += rec(FCGI_PARAMS, b"".join(kv(k, v) for k, v in params.items())) + rec(FCGI_PARAMS, b"")
    msg += rec(FCGI_STDIN, b"")
    conn.sendall(msg)
    out, err, buf = b"", b"", b""
    while True:
        chunk = conn.recv(65536)
        if not chunk:
            break
        buf += chunk
        while len(buf) >= 8:
            _, t, _, ln, pad, _ = struct.unpack(">BBHHBB", buf[:8])
            if len(buf) < 8 + ln + pad:
                break
            body, buf = buf[8:8 + ln], buf[8 + ln + pad:]
            if t == FCGI_STDOUT: out += body
            elif t == FCGI_STDERR: err += body
            elif t == FCGI_END: return out, err
    return out, err

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--socket"); ap.add_argument("--host"); ap.add_argument("--port", type=int, default=9000)
    ap.add_argument("--script", help="new file path to write the probe to, inside a dir FPM can read; "
                                     "must not exist yet (default: temp dir)")
    a = ap.parse_args()
    if not a.socket and not a.host:
        ap.error("--socket or --host required")
    tmpdir = None
    if a.script:
        path = os.path.abspath(a.script)
        if os.path.lexists(path):
            ap.error(f"{path} already exists; refusing to overwrite (the probe file is deleted afterwards)")
        if not os.path.isdir(os.path.dirname(path)):
            ap.error(f"directory of {path} does not exist")
    else:
        tmpdir = tempfile.mkdtemp(prefix="php2shell-probe-")
        os.chmod(tmpdir, 0o755)
        path = os.path.join(tmpdir, "probe.php")
    try:
        with open(path, "wb") as f:
            f.write(PROBE)
        os.chmod(path, 0o644)
        try:
            if a.socket:
                conn = socket.socket(socket.AF_UNIX); conn.settimeout(10); conn.connect(a.socket)
            else:
                conn = socket.create_connection((a.host, a.port), timeout=10)
        except OSError as e:
            target = a.socket or f"{a.host}:{a.port}"
            print(f"cannot connect to FPM at {target}: {e}", file=sys.stderr)
            sys.exit(2)
        out, err = run(conn, path)
        conn.close()
    finally:
        try: os.unlink(path)
        except OSError: pass
        if tmpdir:
            try: os.rmdir(tmpdir)
            except OSError: pass
    if err:
        print("FPM stderr:", err.decode(errors="replace"), file=sys.stderr)
    head, _, body = out.partition(b"\r\n\r\n")
    try:
        data = json.loads(body)
    except ValueError:
        print("Unexpected response (status/headers below). Common causes: pool user cannot read the probe "
              "(use --script inside the docroot), open_basedir, chroot, security.limit_extensions.", file=sys.stderr)
        print(head.decode(errors="replace")); print(body.decode(errors="replace")[:500]); sys.exit(2)
    ini = data["ini"]
    print(f"PHP {data['php']} ({data['sapi']})  loaded ini: {ini.get('loaded_ini') or '(none)'}")
    print(f"  scanned: {ini.get('scanned_ini')}")
    bad = 0
    on85 = data["php"].startswith("8.5")
    checks = (("session.upload_progress.enabled", {"0", "", "Off", "off"}),
              ("memory_limit", {"-1"}),
              ("fatal_error_backtraces", {"0", "", "Off", "off"} if on85 else None),
              ("session.use_strict_mode", {"1", "On", "on"}),
              ("post_max_size", None), ("enable_post_data_reading", None),
              ("max_input_nesting_level", None), ("session.upload_progress.name", None))
    for k, want in checks:
        v = ini.get(k)
        if k == "fatal_error_backtraces" and not on85:
            continue
        flag = "" if want is None else ("  OK" if str(v) in want else "  <-- NOT MITIGATED")
        if flag.endswith("MITIGATED"): bad += 1
        print(f"  {k} = {v!r}{flag}")
    sys.exit(1 if bad else 0)

if __name__ == "__main__":
    main()
