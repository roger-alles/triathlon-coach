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


def test_deploy_runs_inside_a_function_because_git_pull_can_rewrite_it():
    src = (ROOT / "scripts" / "deploy.sh").read_text()
    assert src.rstrip().endswith('main "$@"\nexit')
    assert src.index("main() {") < src.index("git pull -q")


def test_deploy_publishes_the_app_only_when_app_changed():
    src = (ROOT / "scripts" / "deploy.sh").read_text()
    assert 'git diff --quiet "$before" "$after" -- app/' in src
    assert "expo-dev" not in src  # el servidor d'Expo Go ja no existeix


def test_publish_app_tests_before_publishing_with_a_pinned_cli():
    src = (ROOT / "scripts" / "publish-app.sh").read_text()
    assert "set -euo pipefail" in src  # si els tests fallen, no es publica
    assert src.index("npx jest") < src.index("update --channel production")
    assert src.index("npx tsc --noEmit") < src.index("update --channel production")
    assert "eas-cli@24.8.0" in src
