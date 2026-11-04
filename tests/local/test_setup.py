"""Validate startup/deployment guards without installing an Ethereum client."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from localchain import setup


class SetupTests(unittest.TestCase):
    def test_init_refuses_to_replace_existing_chain(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'chain.json'
            path.write_text('{"keep": true}')
            with patch('sys.argv',['setup','init','--data',directory]), self.assertRaises(SystemExit):
                setup.main()
            self.assertEqual(json.loads(path.read_text()),{'keep':True})

    def test_unknown_geth_version_is_rejected(self):
        with patch('shutil.which',return_value='/usr/bin/geth'), patch('subprocess.check_output',return_value='Version: 1.14.0'), self.assertRaises(SystemExit):
            setup.geth_binary()

    def test_observer_requires_explicit_peer(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch('sys.argv',['setup','observer','--data',directory]), patch('localchain.setup.geth_binary',return_value='/usr/bin/geth'), self.assertRaises(SystemExit):
                setup.main()

    def test_observer_does_not_require_writer_keys(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'genesis.json').write_text('{}')
            with patch('sys.argv',['setup','observer','--data',directory,'--enode','enode://nodeid@127.0.0.1:30303']), patch('localchain.setup.geth_binary',return_value='/usr/bin/geth'), patch('subprocess.run') as run, patch('os.execv',side_effect=SystemExit) as execute, self.assertRaises(SystemExit):
                setup.main()
            command=execute.call_args.args[1]
            self.assertNotIn('--unlock',command)
            self.assertNotIn('--mine',command)
            self.assertIn('--nodiscover',command)
            self.assertEqual(command[command.index('--http.addr')+1],'127.0.0.1')
            self.assertIn('StaticNodes', (root/'observer1.toml').read_text())


if __name__=='__main__':
    unittest.main()
