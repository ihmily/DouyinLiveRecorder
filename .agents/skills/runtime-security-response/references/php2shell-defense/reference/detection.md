# Detection

## Behavioural (works without knowing the exploit)
Alert on a process whose parent is `php-fpm`, `php-cgi`, `httpd`, `apache2`, `lsphp`, `litespeed`
and whose image is a shell or tool: `sh bash dash zsh curl wget nc ncat socat python* perl ruby
base64 busybox chmod id whoami uname`. Also command lines containing `/dev/tcp/`, `mkfifo`,
`fsockopen`, `bash -i`, `0>&1`, `base64 -d`.

Sysmon (Linux) / auditd rule sketch:
```
-a always,exit -F arch=b64 -S execve -F euid=www-data -k php2shell
-a always,exit -F arch=b64 -S execve -F euid=apache -k php2shell
```
Falco:
```
- rule: PHP worker spawned shell or downloader
  condition: spawned_process and proc.pname in (php-fpm, php-cgi, httpd, apache2, lsphp) and proc.name in (sh, bash, dash, curl, wget, nc, ncat, socat, python, python3, perl)
  output: "php2shell suspect (parent=%proc.pname cmd=%proc.cmdline user=%user.name)"
  priority: CRITICAL
```
osquery: `SELECT p.pid,p.name,p.cmdline,pp.name AS parent FROM processes p JOIN processes pp ON p.parent=pp.pid WHERE pp.name IN ('php-fpm','php-cgi','httpd','apache2') AND p.name IN ('sh','bash','curl','wget','nc','python3','perl');`

## Pre-exploitation signals
- PHP error log: bursts of `Allowed memory size of N bytes exhausted` (the CVE-2026-109618
  trigger) or `Maximum execution time of N seconds exceeded` and other fatals (the
  CVE-2026-109619 producer) from one client or against one path. Turn on `log_errors` with a
  working `error_log` now if they are off. PHP notes that clean logs do not prove safety.
- PHP-FPM log: `child <pid> exited on signal 11 (SIGSEGV)` bursts; kernel log `php-fpm[...]: segfault at ...`. Failed heap-grooming attempts crash workers.
- Access log: `multipart/form-data` POSTs to paths that never take uploads (`/`, `/index.php`, `/wp-login.php`, `/xmlrpc.php`, `/api/*`), especially with no `Content-Length` or with large bodies / `413` responses. Add `$content_type` and `$request_length` (nginx) or `%{Content-Type}i` (Apache) to the log format now; combined format does not record them.
- Bodies or query strings containing `PHP_SESSION_UPLOAD_PROGRESS` (only visible with body logging or WAF logs).
- Session store: files/keys with `upload_progress_` prefix when your app has no upload progress bars.

## Post-exploitation
- New/modified `.php`, `.phtml`, `.htaccess`, `.user.ini` in webroots, especially under `uploads/`, `cache/`, `tmp/`.
- Webshell patterns: `eval(base64_decode(`, `$_POST['x'](`, `assert($_REQUEST`, `gzinflate(`.
- New cron entries (`/etc/cron*`, `crontab -l -u www-data`), new users, new SSH keys, new systemd units.
- Outbound connections from PHP workers to unknown hosts; DNS lookups for odd domains.
- `scripts/php-hunt.sh` automates the host-local parts.

## Log query snippets
Loki: `{job="nginx"} |~ "(?i)multipart/form-data" | pattern "<_> \"<method> <path> <_>\"" | path !~ "/(upload|wp-admin/async-upload.php)"`
Splunk: `index=web content_type="multipart/form-data*" NOT uri_path IN ("/upload","/wp-admin/async-upload.php") | stats count by src_ip, uri_path`
Elastic/KQL: `http.request.headers.content-type:*multipart* and not url.path:(/upload or /wp-admin/async-upload.php)`

## Triage rule
Any behavioural hit, or any crash / OOM / timeout burst correlated with multipart POSTs, on a host that was
reachable and unpatched after 2026-10-21 07:00 UTC: isolate, preserve logs and session store,
image the disk if feasible, rotate credentials reachable from that host (DB, API keys, SSH),
rebuild rather than clean.
