import json
import subprocess
import sys
import textwrap
from pathlib import Path

from td_plugin.install import MODULES, component_sources, module_dat_name, source_hashes

ROOT = Path(__file__).resolve().parents[1]
TOX = ROOT / "tox" / "td_python_debug.tox"
MANIFEST = ROOT / "tox" / "td_python_debug.manifest.json"


def test_tox_is_committed():
    assert TOX.is_file() and TOX.stat().st_size > 1000


def test_tox_matches_repo_sources():
    """A stale tox fails here: rebuild with `python scripts/build_tox.py` after changing td_plugin/*.py or install.py callbacks."""
    manifest = json.loads(MANIFEST.read_text())["sources"]
    assert manifest == source_hashes(str(ROOT)), "tox/ is stale: run python scripts/build_tox.py"


def test_embedded_modules_cover_runtime_imports():
    names = set(component_sources(str(ROOT)))
    assert {module_dat_name(m) for m in MODULES} <= names
    for needed in ("bootstrap", "callbacks", "par_callbacks"):
        assert needed in names


def test_no_absolute_user_paths_in_embedded_sources():
    for name, text in component_sources(str(ROOT)).items():
        assert "/Users/" not in text and "C:\\Users" not in text, name


def test_bootstrap_resolves_embedded_modules_without_a_checkout(tmp_path):
    """Run the bootstrap DAT text against fake DATs: `import td_plugin.runtime` must come from the embedded texts."""
    sources = component_sources(str(ROOT))
    dump = tmp_path / "dats.json"
    dump.write_text(json.dumps(sources))
    script = textwrap.dedent(
        f"""
        import json, os, sys, types
        dats = json.load(open({str(dump)!r}))
        class Dat:
            def __init__(self, name): self.name = name; self.text = dats[name]
        class Par:
            def __init__(self, v): self.v = v
            def eval(self): return self.v
        class Comp:
            path = "/p/comp"
            def __init__(self, mp=""): self.par = types.SimpleNamespace(Modulepath=Par(mp))
            def op(self, n): return Dat(n) if n in dats else None
        comp = Comp()
        ns = {{"op": lambda p: comp if p == comp.path else None}}
        exec(compile(dats["bootstrap"], "bootstrap", "exec"), ns)
        os.environ.pop("TD_MCP_MODULEPATH", None)
        assert ns["prepare"](comp) == "embedded"
        assert ns["prepare"](comp) == "embedded"
        assert sum(1 for f in sys.meta_path if getattr(f, "_td_mcp_embedded_finder", False)) == 1
        import td_plugin.runtime as rt
        assert rt.__spec__.loader.__class__.__name__ == "_EmbeddedFinder", rt.__spec__
        import td_plugin.connection, td_plugin.handlers, td_plugin.context
        # Modulepath wins and drops the embedded finder
        assert ns["prepare"](Comp({str(ROOT)!r})) == "path"
        assert not any(getattr(f, "_td_mcp_embedded_finder", False) for f in sys.meta_path)
        # env var is the second choice
        os.environ["TD_MCP_MODULEPATH"] = {str(ROOT)!r}
        assert ns["prepare"](comp) == "path"
        print("ok")
        """
    )
    proc = subprocess.run([sys.executable, "-I", "-c", script], cwd=tmp_path, capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "ok"
