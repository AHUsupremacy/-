"""Execute the installer and its rollback against an isolated systemctl model."""
from contextlib import redirect_stdout
import importlib.util
from io import StringIO
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
UNIT = 'systemd-networkd-wait-online.service'
spec = importlib.util.spec_from_file_location(
    'boot_order', ROOT/'scripts/gmk_network/fix_network_boot_order.py')
boot_order = importlib.util.module_from_spec(spec)
spec.loader.exec_module(boot_order)


SYSTEMCTL = '''#!/usr/bin/python3
import json
import os
from pathlib import Path
import sys

path = Path(os.environ['FAKE_SYSTEMD_STATE'])
state = json.loads(path.read_text())
args = sys.argv[1:]
state['calls'].append(args)
status = 0
if args[0] == 'is-enabled':
    if args[1] == 'NetworkManager-wait-online.service':
        print('enabled')
    else:
        value = state['masked'] or state['enabled']
        print(value)
        status = 0 if value in ('enabled', 'enabled-runtime') else 1
elif args[0] == 'is-active':
    print('active')
elif args[0] == 'show':
    print('')
elif args[0] == 'mask':
    state['masked'] = 'masked'
elif args[0] == 'unmask':
    state['masked'] = ''
elif args[0] == 'enable':
    state['enabled'] = 'enabled-runtime' if '--runtime' in args else 'enabled'
elif args[0] == 'disable':
    state['enabled'] = 'disabled'
elif args[0] != 'daemon-reload':
    raise SystemExit('Unexpected systemctl command: '+repr(args))
path.write_text(json.dumps(state))
raise SystemExit(status)
'''


class BootOrderRollbackTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='gmk-boot-order-test-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        commands = self.root/'bin'
        commands.mkdir()
        systemctl = commands/'systemctl'
        systemctl.write_text(SYSTEMCTL)
        systemctl.chmod(0o755)
        self.state_file = self.root/'state.json'
        self.backups = self.root/'backups'
        self.environment = dict(os.environ, PATH=str(commands)+':/usr/bin:/bin',
                                FAKE_SYSTEMD_STATE=str(self.state_file))

    def set_state(self, before):
        masked = before if before.startswith('masked') else ''
        self.state_file.write_text(json.dumps(
            {'enabled': before, 'masked': masked, 'calls': []}))

    def state(self):
        return json.loads(self.state_file.read_text())

    def install(self):
        with patch.dict(os.environ, self.environment, clear=True), \
                patch.object(boot_order.os, 'geteuid', return_value=0), \
                patch.object(boot_order, 'BACKUP_ROOT', self.backups), \
                redirect_stdout(StringIO()):
            return boot_order.main()

    def round_trip(self, before):
        self.backups = self.root/('backups-'+before)
        self.set_state(before)
        self.assertEqual(self.install(), 0)
        self.assertEqual(self.state()['masked'], 'masked')
        backups = list(self.backups.glob('boot-order-*'))
        self.assertEqual(len(backups), 1)
        saved = json.loads((backups[0]/'before.json').read_text())
        self.assertEqual(saved['enabled'], before)
        restore = backups[0]/'restore.sh'
        result = subprocess.run(['bash', str(restore)], env=self.environment,
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        state = self.state()
        self.assertEqual(state['masked'], '')
        self.assertEqual(state['enabled'], before)
        mutations = [args for args in state['calls']
                     if args[0] not in ('is-enabled', 'is-active', 'show')]
        self.assertTrue(all(args[0] in ('mask', 'unmask', 'enable', 'disable', 'daemon-reload')
                            for args in mutations))
        self.assertTrue(all(args[0] == 'daemon-reload' or args[-1] == UNIT
                            for args in mutations))
        return state['calls']

    def test_disabled_service_remains_disabled_after_restore(self):
        self.round_trip('disabled')

    def test_enabled_service_is_enabled_after_restore(self):
        self.round_trip('enabled')

    def test_runtime_enable_does_not_become_persistent(self):
        self.round_trip('enabled-runtime')

    def test_units_without_enablement_are_only_unmasked(self):
        for before in ('static', 'indirect', 'generated', 'transient', 'linked', 'linked-runtime', 'alias'):
            with self.subTest(before=before):
                calls = self.round_trip(before)
                self.assertFalse(any(args[0] in ('enable', 'disable') for args in calls))

    def test_already_masked_states_are_not_changed(self):
        for before in ('masked', 'masked-runtime'):
            with self.subTest(before=before):
                self.set_state(before)
                self.assertEqual(self.install(), 0)
                self.assertEqual(self.state()['masked'], before)
                self.assertFalse(self.backups.exists())
                self.assertTrue(all(args[0] == 'is-enabled' for args in self.state()['calls']))

    def test_unknown_states_are_rejected_before_changes(self):
        for before in ('', 'not-found', 'bad', 'unknown'):
            with self.subTest(before=before):
                self.set_state(before)
                with self.assertRaises(SystemExit):
                    self.install()
                self.assertEqual(self.state()['masked'], '')
                self.assertFalse(self.backups.exists())
                self.assertTrue(all(args[0] == 'is-enabled' for args in self.state()['calls']))


if __name__ == '__main__':
    unittest.main()
