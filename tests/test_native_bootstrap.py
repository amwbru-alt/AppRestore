"""Exercise the actual bootstrap against the actual archive packer, offline."""
from pathlib import Path
import shutil
import subprocess
import os
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.skipif(os.name == 'nt' or not shutil.which('bash'),reason='POSIX bootstrap')
def test_bootstrap_installs_actual_packer_layout_and_reuses_binary(tmp_path):
    package = tmp_path/'packaging';package.mkdir()
    (package/'patches').mkdir();(package/'patches'/'0001-test.patch').write_text('fixture')
    shutil.copy2(ROOT/'packaging'/'bootstrap-ipatool.sh',package/'bootstrap-ipatool.sh')
    shutil.copy2(ROOT/'packaging'/'pack_ipatool.py',package/'pack_ipatool.py')
    # These are the extensions the bootstrap promises to its caller; the
    # build itself is stubbed to avoid downloading Go or contacting Apple.
    markers = [
      'too many authentication redirects','appstore.CountryCodeFromStoreFront',
      '--all cannot be combined with --page or --max-results',
      'keychain-passphrase-stdin','catalog-independent redownload does not match the requested app',
      'Inspect download channels without purchase, asset download or private response data',
      'invalid Apple product redirect','purchase response unconfirmed',
      'catalog-independent update has no license material',
    ]
    binary=tmp_path/'fake-ipatool'
    binary.write_text('#!/bin/sh\n'+'\n'.join('# '+m for m in markers)+'''\ncase "$1" in
--version) echo 'ipatool 2.6.0' ;;
--help) echo '--keychain-passphrase-stdin' ;;
esac
''');binary.chmod(0o755)
    builder=package/'build-ipatool.sh'
    builder.write_text('''#!/bin/bash
set -eu
root="$(cd "$(dirname "$0")/.." && pwd)"
python3 "$root/packaging/pack_ipatool.py" --binary "$root/fake-ipatool" --name ipatool --mtime 0 --out "$IPATOOL_OUT/ipatool-2.6.0-$1.tar.gz"
''');builder.chmod(0o755)
    fakebin=tmp_path/'tools';fakebin.mkdir()
    go=fakebin/'go';go.write_text('#!/bin/sh\necho go1.25.0\n');go.chmod(0o755)
    cc=fakebin/'cc';cc.write_text('#!/bin/sh\nexit 0\n');cc.chmod(0o755)
    python3=fakebin/'python3'
    python3.symlink_to(sys.executable)
    env=dict(os.environ,PATH=str(fakebin)+os.pathsep+os.environ['PATH'])
    command=['bash',str(package/'bootstrap-ipatool.sh'),'--asset','linux-amd64','--repo',str(tmp_path)]
    result=subprocess.run(command,capture_output=True,text=True,env=env,timeout=30)
    assert result.returncode==0,result.stderr
    installed=tmp_path/'bin'/'ipatool'
    assert installed.read_bytes()==binary.read_bytes()
    again=subprocess.run(command,capture_output=True,text=True,env=env,timeout=30)
    assert again.returncode==0,again.stderr
    assert 'already built from the same inputs' in again.stdout
