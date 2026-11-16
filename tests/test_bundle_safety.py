import importlib.util
from pathlib import Path


def test_integrated_bundle_excludes_device_secrets_build_cache_and_private_keys(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("bundle", Path(__file__).parents[1] / "tools/build_bundle.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for name in ["firmware/include/secrets.h", "firmware/include/secrets.example.h", ".env", ".env.production", ".env.example",
                 "deployment/certs/server.key", "firmware/.pio/build/firmware.bin", "frontend/index.html"]:
        file = tmp_path / name
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text("fixture", encoding="utf-8")
    monkeypatch.setattr(module, "ROOT", tmp_path)
    included = {p.relative_to(tmp_path).as_posix() for p in module.source_files()}
    assert included == {"firmware/include/secrets.example.h", ".env.example", "frontend/index.html"}
