"""Exercise cleanup decisions without touching the real build cache."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


GUARD = Path(__file__).resolve().with_name('gocache-guard.sh')


class CacheGuardTest(unittest.TestCase):
    def decision(self, size, free, expected, **overrides):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'scripts').mkdir()
            (root / 'bin').mkdir()
            for path, body in [
                (root / 'bin/du', f'echo "{size * 1048576} cache"'),
                (root / 'bin/df', f'echo "Filesystem 1024-blocks Used Available Capacity Mounted"\necho "disk 134217728 0 {free * 1048576} 0% /"'),
                (root / 'scripts/go-cache-run.sh', 'echo "$1" > "$GO_CACHE_TEST_TRACE"'),
            ]:
                path.write_text('#!/bin/sh\n' + body + '\n')
                path.chmod(0o755)
            env = dict(os.environ)
            for key in ('GO_CACHE_CLEAN_AT_GIB', 'GO_CACHE_MIN_FREE_GIB'):
                env.pop(key, None)
            env.update(PATH=str(root / 'bin') + ':' + env['PATH'],
                       GO_CACHE_OPS_ROOT=str(root), GO_CACHE_ROOT=str(root),
                       GO_CACHE_GUARD_LOG=str(root / 'log'),
                       GO_CACHE_TEST_TRACE=str(root / 'trace'), **overrides)
            subprocess.run(['bash', str(GUARD)], env=env, check=True,
                           capture_output=True, text=True)
            self.assertEqual((root / 'trace').exists(), expected)
            if expected:
                self.assertEqual((root / 'trace').read_text().strip(), 'clean')

    def test_preserves_warm_cache_with_disk_headroom(self):
        self.decision(21, 76, False)

    def test_hard_cap_still_cleans(self):
        self.decision(40, 55, True)

    def test_disk_pressure_cleans_before_cap(self):
        self.decision(10, 19, True)

    def test_empty_cache_is_not_cleaned(self):
        self.decision(0, 10, False)

    def test_explicit_size_cap_is_preserved(self):
        self.decision(20, 76, True, GO_CACHE_CLEAN_AT_GIB='20')

    def test_exact_free_space_reserve_is_retained(self):
        self.decision(39, 20, False)


if __name__ == '__main__':
    unittest.main()
