"""Publication subset: seven original synthetic worker correction tests.
No historical, Checkpoint E, or cachetools candidate execution.
"""
import base64
import builtins
import io
import json
from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile
import unittest
from unittest.mock import patch

from common import sha
import historical_runner as runner
import historical_worker as worker
from execution_evidence import verify_nonfile_modules

class WorkerCorrections(unittest.TestCase):
    def invoke_synthetic(self, source, mutate_at_compile=False, pin=None):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); check = root / 'SYNTHETIC_ONLY.py'; check.write_text(source)
            manifest = root / 'manifest.json'; manifest.write_text('{"files":{}}')
            ident = runner.interpreter_identity()
            request = {'interpreter':ident,'check_path':str(check),'check_sha256':pin or sha(check.read_bytes()),
                       'manifest_path':str(manifest),'manifest_sha256':sha(manifest.read_bytes()),
                       'snapshot_root':str(root),'invocation_id':'SYNTHETIC_ONLY','check_stdout_limit':4096,'check_stderr_limit':1024}
            path = root / 'request.json';path.write_text(json.dumps(request))
            args = SimpleNamespace(request=path,request_sha256=sha(path.read_bytes()))
            original_compile = builtins.compile
            def compile_then_change_path(buffer, filename, mode):
                check.write_text('def main():\n    raise RuntimeError("UNAPPROVED_SYNTHETIC_BYTES")\n')
                return original_compile(buffer, filename, mode)
            output = io.StringIO()
            with patch.object(worker.argparse.ArgumentParser,'parse_args',return_value=args), patch.object(worker,'identity',return_value=ident), \
                 patch.object(worker,'module_inventory',return_value=({},{})), patch.object(sys,'argv',list(sys.argv)), \
                 patch.object(worker,'compile',side_effect=compile_then_change_path if mutate_at_compile else original_compile,create=True), \
                 patch('sys.stdout',output):
                code = worker.main()
            return code, json.loads(output.getvalue())

    def test_verified_buffer_execution_despite_path_mutation_and_postcheck(self):
        source='import json\ndef main():\n    print(json.dumps({"verified_buffer_executed":True}))\n    return 0\n'
        code, envelope=self.invoke_synthetic(source,mutate_at_compile=True)
        self.assertEqual(code,2)  # Mutation invalidates preservation, never acceptance.
        raw=base64.b64decode(envelope['check_stdout_b64'])
        self.assertTrue(json.loads(raw)['verified_buffer_executed'])
        self.assertEqual(envelope['stage'],'integrity')
        self.assertNotIn(b'UNAPPROVED_SYNTHETIC_BYTES',raw)

    def test_immutable_buffer_executes_without_path_reload(self):
        source=b'def main():\n    return 17\n'
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'synthetic.py';path.write_bytes(source)
            buffer=path.read_bytes();path.write_text('invalid replacement syntax!')
            self.assertEqual(worker.execute_verified(buffer,path,sha(buffer)),17)

    def test_wrong_check_hash_rejected_before_any_compilation(self):
        code,envelope=self.invoke_synthetic('def main():\n    raise AssertionError("MUST_NOT_EXECUTE")\n',pin='0'*64)
        self.assertEqual(code,2);self.assertEqual(envelope['stage'],'integrity')
        self.assertEqual(base64.b64decode(envelope['check_stdout_b64']),b'')
        with self.assertRaisesRegex(ValueError,'BUFFER_HASH'):
            worker.execute_verified(b'def main(): return 0',Path('/SYNTHETIC'), '0'*64)

    def test_duplicate_top_level_and_nested_keys_rejected_before_normalization(self):
        for raw in ('{"status":"ERROR","status":"PASS"}', '{"status":"PASS","nested":{"x":1,"x":2}}'):
            code,e=self.invoke_synthetic('def main():\n    print('+repr(raw)+')\n    return 0\n')
            self.assertEqual(code,2);self.assertEqual(e['stage'],'integrity')
            self.assertEqual(base64.b64decode(e['check_stdout_b64']), (raw+'\n').encode())

    def test_raw_stdout_stderr_retained_on_execution_failure(self):
        code,e=self.invoke_synthetic('import sys\ndef main():\n    print("controlled stdout")\n    print("controlled stderr",file=sys.stderr)\n    raise RuntimeError("synthetic failure")\n')
        self.assertEqual(code,2);self.assertEqual(e['stage'],'check_execution')
        for name in ('stdout','stderr'):
            raw=base64.b64decode(e['check_'+name+'_b64'])
            self.assertEqual(raw,('controlled '+name+'\n').encode())
            self.assertEqual(sha(raw),e['check_'+name+'_sha256'])

    def test_caught_output_overflow_still_rejects(self):
        code,e=self.invoke_synthetic('import sys,json\ndef main():\n    try:\n        sys.stdout.write("x"*5000)\n    except ValueError:\n        pass\n    print(json.dumps({"status":"PASS"}))\n    return 0\n')
        self.assertEqual(code,2);self.assertEqual(e['stage'],'output_limit')
        self.assertIs(e['check_output_overflow'],True)
        self.assertEqual(json.loads(base64.b64decode(e['check_stdout_b64']))['status'],'PASS')

    def test_originless_modules_rejected_builtin_frozen_classified(self):
        unknown=SimpleNamespace(__spec__=None)
        with patch.object(worker,'sys',SimpleNamespace(modules={'unexpected_originless':unknown})):
            with self.assertRaisesRegex(ValueError,'UNEXPLAINED'):
                worker.module_inventory(Path('/SYNTHETIC'),{'files':{}})
        import os
        with patch.object(worker,'sys',SimpleNamespace(modules={'sys':sys,'builtins':builtins,'os':os})):
            files,nonfiles=worker.module_inventory(Path('/SYNTHETIC'),{'files':{}})
        self.assertEqual(files,{})
        self.assertEqual(nonfiles['sys']['kind'],'built-in')
        self.assertEqual(nonfiles['os']['kind'],'frozen')
        verify_nonfile_modules(nonfiles)
        with self.assertRaises(ValueError):
            verify_nonfile_modules({**nonfiles,'unknown':{'kind':'built-in','canonical_name':'unknown'}})

if __name__ == "__main__":
    unittest.main()
