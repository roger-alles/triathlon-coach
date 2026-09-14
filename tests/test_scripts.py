"""Els scripts d'operació (bash) i els plists de launchd han de ser vàlids."""
import glob
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = sorted(glob.glob(str(ROOT / "scripts" / "*.sh")))
PLISTS = sorted(glob.glob(str(ROOT / "scripts" / "launchd" / "*.plist")))


@pytest.mark.parametrize("script", SCRIPTS, ids=[Path(s).name for s in SCRIPTS])
def test_bash_syntax(script):
    subprocess.run(["bash", "-n", script], check=True)


def test_backup_pull_exists_and_never_deletes_local_copies():
    src = (ROOT / "scripts" / "backup-pull.sh").read_text()
    assert "rsync" in src
    assert "--delete" not in src, "la còpia al Mac és l'última xarxa: mai esborrar"


def test_backup_pull_plist_points_to_script():
    plist = (ROOT / "scripts" / "launchd" / "cat.entrenador.backup-pull.plist").read_text()
    assert "scripts/backup-pull.sh" in plist
    assert "<key>Label</key><string>cat.entrenador.backup-pull</string>" in plist


@pytest.mark.skipif(shutil.which("plutil") is None, reason="plutil només a macOS")
@pytest.mark.parametrize("plist", PLISTS, ids=[Path(p).name for p in PLISTS])
def test_plist_is_valid(plist):
    subprocess.run(["plutil", "-lint", "-s", plist], check=True)
