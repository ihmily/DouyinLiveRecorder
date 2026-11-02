"""CLI contract tests; fixtures never contact services or decode payloads."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'nodecheck.py'


class NodeCheckCLI(unittest.TestCase):
    def call(self, *args, env=None):
        return subprocess.run([sys.executable, str(SCRIPT), *args],
                              capture_output=True, text=True, timeout=10, env=env)

    def report(self, *args, expected=0, env=None):
        result = self.call(*args, '--json', env=env)
        self.assertEqual(result.returncode, expected, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report['exit_code'], expected)
        self.assertEqual(report['service_patch_status'], 'not_verified')
        self.assertEqual(report['brotli_linkage'], 'not_verified')
        self.assertNotIn('safe', report['status'])
        return report

    def fake_node(self, code, *args, expected=3, env=None):
        with tempfile.TemporaryDirectory(prefix='nodecheck-test-') as tmp:
            fixture = Path(tmp) / 'node fixture'
            fixture.write_text('#!' + sys.executable + '\n' + code + '\n')
            fixture.chmod(0o700)
            return self.report('--local', '--node', str(fixture), *args,
                               expected=expected, env=env)

    def test_three_exact_fixed_boundaries(self):
        for version in ['22.23.4', '24.22.1', '26.12.1']:
            with self.subTest(version=version):
                r = self.report('--version-string', version)
                self.assertEqual(r['status'], 'version_fixed')
                self.assertEqual(r['fixed_version'], version)
                self.assertEqual(r['evidence_scope'], 'provided_version_only')

    def test_three_before_fixed_boundaries(self):
        for version in ['22.23.3', '24.22.0', '26.12.0']:
            with self.subTest(version=version):
                self.assertEqual(self.report('--version-string', version, expected=1)['status'], 'below_fixed')

    def test_newer_patch_and_minor(self):
        for version in ['22.23.5', '24.23.0', '26.13.0']:
            with self.subTest(version=version):
                self.assertEqual(self.report('--version-string', version)['status'], 'version_fixed')

    def test_older_minor_with_high_patch(self):
        self.assertEqual(self.report('--version-string', '24.21.999', expected=1)['status'], 'below_fixed')

    def test_v_prefix(self):
        self.assertEqual(self.report('--version-string', 'v24.22.1')['node_version'], 'v24.22.1')

    def test_semver_build_metadata(self):
        self.assertEqual(self.report('--version-string', '24.22.1+build.7')['status'], 'version_fixed')

    def test_eol_lines_not_marked_unaffected(self):
        for version in ['18.20.8', '20.99.0', '21.7.3', '23.11.1', '25.8.0']:
            with self.subTest(version=version):
                r = self.report('--version-string', version, expected=3)
                self.assertEqual(r['status'], 'eol_review')
                self.assertIsNone(r['fixed_version'])
                self.assertEqual(r['cves_for_known_line'], [])
                self.assertTrue(any('does not mean unaffected' in s for s in r['limitations']))

    def test_future_major_unknown(self):
        self.assertEqual(self.report('--version-string', '28.0.0', expected=3)['status'], 'unknown')

    def test_prerelease_unknown(self):
        for version in ['26.12.1-rc.1', '24.22.1-nightly20261022']:
            with self.subTest(version=version):
                self.assertEqual(self.report('--version-string', version, expected=3)['status'], 'unknown')

    def test_vendor_suffix_unknown(self):
        self.assertEqual(self.report('--version-string', '22.22.0-debian1', expected=3)['status'], 'unknown')

    def test_ranges_and_partial_versions_unknown(self):
        for version in ['^24.22.1', '>=24.22.1', '24.x', '24.22', '024.22.1', 'node24.22.1']:
            with self.subTest(version=version):
                r = self.report('--version-string', version, expected=3)
                self.assertEqual(r['status'], 'unknown')
                self.assertIsNone(r['node_version'])

    def test_all_ten_cves_on_26(self):
        r = self.report('--version-string', '26.12.1')
        self.assertEqual(len(r['cves_for_known_line']), 10)
        self.assertIn('CVE-2026-111497', r['cves_for_known_line'])

    def test_branch_specific_cve_mapping(self):
        r22 = self.report('--version-string', '22.23.4')
        r24 = self.report('--version-string', '24.22.1')
        self.assertEqual(len(r22['cves_for_known_line']), 7)
        self.assertEqual(len(r24['cves_for_known_line']), 8)
        self.assertNotIn('CVE-2026-105483', r22['cves_for_known_line'])
        self.assertIn('CVE-2026-105483', r24['cves_for_known_line'])
        self.assertNotIn('CVE-2026-106070', r24['cves_for_known_line'])

    def test_invalid_version_tokens_not_echoed(self):
        for token in ['', '24.22.1\nSECRET', '24.22.1 SECRET', 'X' * 201]:
            with self.subTest(token=repr(token[:20])):
                result = self.call('--version-string', token, '--json')
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, '')
                self.assertNotIn('SECRET', result.stderr)

    def test_timeout_bounds(self):
        for value in ['0', '-1', '61', 'nan', 'inf', '-inf', 'bad']:
            with self.subTest(value=value):
                self.assertEqual(self.call('--local', '--timeout=' + value).returncode, 2)

    def test_unknown_argument_redacted(self):
        result = self.call('--api-key=secret_value')
        self.assertEqual(result.returncode, 2)
        self.assertNotIn('secret_value', result.stderr)

    def test_modes_exclusive_and_required(self):
        self.assertEqual(self.call().returncode, 2)
        self.assertEqual(self.call('--local', '--version-string', '24.22.1').returncode, 2)

    def test_node_path_requires_local(self):
        self.assertEqual(self.call('--version-string', '24.22.1', '--node', '/tmp/unused').returncode, 2)
        self.assertEqual(self.call('--local', '--node', '').returncode, 2)

    def test_local_success_exact_argument_and_sanitized_node_env(self):
        env = os.environ.copy()
        env.update(NODE_OPTIONS='--require secret.js', NODE_PATH='/secret')
        code = ('import os, sys\n'
                'assert sys.argv[1:] == ["--version"]\n'
                'assert "NODE_OPTIONS" not in os.environ\n'
                'assert "NODE_PATH" not in os.environ\n'
                'print("v24.22.1")')
        r = self.fake_node(code, expected=0, env=env)
        self.assertEqual(r['evidence_scope'], 'local_binary_only')

    def test_missing_local_executable(self):
        r = self.report('--local', '--node', '/nonexistent/nodecheck-fixture', expected=3)
        self.assertEqual(r['status'], 'unknown')

    def test_absent_path_node(self):
        with tempfile.TemporaryDirectory(prefix='no-node-') as tmp:
            env = os.environ.copy()
            env['PATH'] = tmp
            r = self.report('--local', expected=3, env=env)
            self.assertIn('not found', r['reason'])

    def test_nonzero_command_unknown_and_output_redacted(self):
        r = self.fake_node('import sys\nprint("SECRET")\nprint("SECRET", file=sys.stderr)\nsys.exit(7)')
        self.assertEqual(r['status'], 'unknown')
        self.assertNotIn('SECRET', json.dumps(r))

    def test_timeout_unknown(self):
        r = self.fake_node('import time\ntime.sleep(2)', '--timeout', '0.05')
        self.assertIn('timed out', r['reason'])

    def test_invalid_utf8_unknown(self):
        r = self.fake_node('import sys\nsys.stdout.buffer.write(bytes([255]))')
        self.assertEqual(r['status'], 'unknown')

    def test_large_output_unknown(self):
        r = self.fake_node('print("S" * 5000)')
        self.assertEqual(r['status'], 'unknown')
        self.assertIsNone(r['node_version'])

    def test_multiline_output_unknown_and_redacted(self):
        r = self.fake_node('print("v24.22.1\\nSECRET")')
        self.assertEqual(r['status'], 'unknown')
        self.assertNotIn('SECRET', json.dumps(r))

    def test_plain_text_not_a_service_safe_verdict(self):
        result = self.call('--version-string', '24.22.1')
        self.assertEqual(result.returncode, 0)
        self.assertIn('Service patch status: NOT VERIFIED.', result.stdout)

    def test_help_and_tool_version(self):
        self.assertEqual(self.call('--help').returncode, 0)
        self.assertEqual(self.call('--version').stdout.strip(), '1.0.2')


if __name__ == '__main__':
    unittest.main()
