import json
import os
from pathlib import Path
import subprocess
import tempfile
import textwrap
import unittest

TOOL = Path(__file__).resolve().parents[1] / 'plugins/alex-coding/scripts/gh_as'


def fake_gh(directory, token='synthetic-token', login='example-bot'):
    (Path(directory) / 'roles.json').write_text(json.dumps({'bot': {'account': 'saved-bot', 'login': 'example-bot'}, 'admin': {'account': 'saved-admin', 'login': 'example-admin'}}))
    path = Path(directory) / 'gh'
    path.write_text(textwrap.dedent(f'''\
        #!/usr/bin/env python3
        import os, sys
        argv = sys.argv[1:]
        if argv[:2] == ['auth', 'token']:
            print({token!r})
        elif argv[:2] == ['api', '--hostname']:
            print({login!r})
        else:
            print('EXECUTED ' + ' '.join(argv))
            print('TOKEN_VISIBLE=' + os.environ.get('GH_TOKEN', ''))
    '''))
    path.chmod(0o755)
    return path


def run(directory, *arguments):
    env = dict(os.environ, GH_AS_CONFIG=str(Path(directory) / 'roles.json'), PATH=f'{directory}:{os.environ["PATH"]}')
    return subprocess.run(['python3', str(TOOL), *arguments], env=env, capture_output=True, text=True, timeout=30)


class AllowListTests(unittest.TestCase):
    def test_missing_role_config_fails_without_reading_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            fake_gh(directory)
            (Path(directory) / 'roles.json').unlink()
            result = run(directory, 'bot', 'pr', 'list')
        self.assertEqual(result.returncode, 1)
        self.assertIn('configure account and login', result.stderr)
        self.assertNotIn('EXECUTED', result.stdout)

    def test_admin_uses_its_configured_expected_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            fake_gh(directory, login='example-admin')
            result = run(directory, 'admin', 'pr', 'list')
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_a_built_in_command_runs_under_the_role(self):
        with tempfile.TemporaryDirectory() as directory:
            fake_gh(directory)
            result = run(directory, 'bot', 'pr', 'list')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('EXECUTED pr list', result.stdout)

    def test_an_alias_or_extension_name_never_reaches_gh(self):
        for name in ('show-role-env', 'sync', 'dash', 'whoami'):
            with tempfile.TemporaryDirectory() as directory:
                fake_gh(directory)
                result = run(directory, 'bot', name)
            self.assertEqual(result.returncode, 1, name)
            self.assertIn('not an allowed gh command', result.stderr)
            self.assertNotIn('EXECUTED', result.stdout)
            self.assertNotIn('TOKEN_VISIBLE', result.stdout)

    def test_management_subcommands_stay_refused(self):
        for command in (['auth', 'token'], ['alias', 'list'], ['extension', 'list'], ['config', 'get', 'x']):
            with tempfile.TemporaryDirectory() as directory:
                fake_gh(directory)
                result = run(directory, 'bot', *command)
            self.assertEqual(result.returncode, 1, command)
            self.assertNotIn('EXECUTED', result.stdout)

    def test_an_unknown_role_is_refused_before_any_credential_read(self):
        with tempfile.TemporaryDirectory() as directory:
            fake_gh(directory)
            result = run(directory, 'reviewer', 'pr', 'list')
        self.assertEqual(result.returncode, 1)
        self.assertIn('specify bot or admin', result.stderr)

    def test_an_identity_that_does_not_match_the_role_stops_before_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            fake_gh(directory, login='someone-else')
            result = run(directory, 'bot', 'pr', 'list')
        self.assertEqual(result.returncode, 1)
        self.assertIn('did not verify', result.stderr)
        self.assertNotIn('EXECUTED', result.stdout)

    def test_credential_and_debug_variables_do_not_leak_in_from_the_caller(self):
        with tempfile.TemporaryDirectory() as directory:
            fake_gh(directory)
            env = dict(os.environ, GH_AS_CONFIG=str(Path(directory) / 'roles.json'), PATH=f'{directory}:{os.environ["PATH"]}',
                       GH_TOKEN='caller-token', GH_DEBUG='api')
            result = subprocess.run(['python3', str(TOOL), 'bot', 'pr', 'list'],
                                    env=env, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('TOKEN_VISIBLE=synthetic-token', result.stdout)

    def test_a_non_github_host_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            fake_gh(directory)
            result = run(directory, 'bot', 'api', '--hostname', 'ghe.example.com', 'user')
        self.assertEqual(result.returncode, 1)
        self.assertIn('only github.com', result.stderr)


if __name__ == '__main__':
    unittest.main()
