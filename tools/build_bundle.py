#!/usr/bin/env python3
"""Sinh tài liệu tham chiếu TỪ CODE rồi đóng gói toàn bộ mã nguồn.

    python tools/build_bundle.py

Tạo:
  docs/reference.md          bảng API (route, quyền), biến môi trường, thống kê bộ test: đọc từ code nên luôn đúng
  dist/wms_source_full.md    toàn bộ mã nguồn trong một file Markdown (có mục lục) để đọc, review, đưa vào báo cáo
  dist/wms-backend.zip       toàn bộ repo (không có .env, __pycache__, dist) để chuyển giao
Chỉ dùng thư viện chuẩn; không cần cài gì.
"""
import ast
import pathlib
import re
import stat
import zipfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
EXCLUDE_DIRS = {"__pycache__", ".pytest_cache", "dist", ".venv", ".git", "node_modules", ".pio", "certs", "runtime"}
EXCLUDE_FILES = {".env", "secrets.h", "compile_commands.json"}
ROLE_ALIASES = {"any_user": ["Admin", "Operator", "Viewer"]}
METHOD_ORDER = {"GET": 0, "POST": 1, "PUT": 2, "PATCH": 3, "DELETE": 4, "WEBSOCKET": 5}
LANG = {".py": "python", ".sql": "sql", ".sh": "bash", ".yml": "yaml", ".md": "markdown", ".txt": "text",
        ".ini": "ini", ".example": "ini"}


def source_files() -> list[pathlib.Path]:
    out = []
    for p in sorted(ROOT.rglob("*")):
        rel = p.relative_to(ROOT)
        if (p.is_file() and not (set(rel.parts) & EXCLUDE_DIRS) and p.name not in EXCLUDE_FILES
                and not (p.name.startswith(".env.") and not p.name.endswith(".example"))
                and p.suffix not in {".pyc", ".db", ".db-wal", ".db-shm", ".pem", ".key", ".p12", ".pfx", ".exe"}):
            out.append(p)
    return out


# ----------------------------------------------------------------------------- tham chiếu API
def _roles(call: ast.Call) -> list[str]:
    return [a.value for a in call.args if isinstance(a, ast.Constant)]


def _resolve_roles(depends: ast.AST, assigns: dict) -> list[str] | None:
    if not (isinstance(depends, ast.Call) and getattr(depends.func, "id", "") == "Depends" and depends.args):
        return None
    target = depends.args[0]
    if isinstance(target, ast.Name):
        if target.id in ROLE_ALIASES:
            return ROLE_ALIASES[target.id]
        value = assigns.get(target.id)
        if isinstance(value, ast.Call):
            return _roles(value)
    if isinstance(target, ast.Call) and getattr(target.func, "id", "") == "require_roles":
        return _roles(target)
    return None


def collect_routes() -> list[dict]:
    rows = []
    files = sorted((ROOT / "backend/app/routers").glob("*.py")) + [ROOT / "backend/app/main.py"]
    for f in files:
        tree = ast.parse(f.read_text(encoding="utf-8"))
        prefix, assigns = "", {}
        for n in tree.body:
            if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name):
                assigns[n.targets[0].id] = n.value
                if isinstance(n.value, ast.Call) and getattr(n.value.func, "id", "") == "APIRouter":
                    for k in n.value.keywords:
                        if k.arg == "prefix":
                            prefix = k.value.value
        for fn in [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]:
            for d in fn.decorator_list:
                if not (isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute) and d.args
                        and d.func.attr in {"get", "post", "put", "patch", "delete", "websocket"}):
                    continue
                path = (prefix if d.func.value.id == "router" else "") + d.args[0].value
                args = fn.args.args
                defaults = [None] * (len(args) - len(fn.args.defaults)) + list(fn.args.defaults)
                roles = None
                for a, default in zip(args, defaults):
                    if default is not None and getattr(a.annotation, "id", "") == "Actor":
                        roles = _resolve_roles(default, assigns)
                if d.func.attr == "websocket":
                    who = "JWT (thông điệp `auth`)"
                elif roles is None:
                    who = "Công khai"
                elif set(roles) == {"Admin", "Operator", "Viewer"}:
                    who = "Mọi vai trò"
                else:
                    who = ", ".join(roles)
                doc = (ast.get_docstring(fn) or "").strip().splitlines()
                rows.append({"method": d.func.attr.upper(), "path": path, "who": who,
                             "desc": doc[0].rstrip(".") if doc else fn.name.replace("_", " ")})
    return sorted(rows, key=lambda r: (r["path"], METHOD_ORDER[r["method"]]))


def collect_settings() -> list[tuple]:
    src = (ROOT / "backend/app/config.py").read_text(encoding="utf-8")
    lines = src.splitlines()
    tree = ast.parse(src)
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "Settings")
    rows = []
    for n in cls.body:
        if isinstance(n, ast.AnnAssign) and n.value is not None:
            comment = re.search(r"#\s*(.*)$", lines[n.lineno - 1])
            value = n.value
            if isinstance(value, ast.Call) and getattr(value.func, "id", "") == "Field":
                value = next((k.value for k in value.keywords if k.arg == "default"), value)
            default = ast.unparse(value)
            rows.append((n.target.id.upper(), ast.unparse(n.annotation), default if default != "''" else "(trống)",
                         comment.group(1) if comment else ""))
    return rows


def collect_tests() -> list[tuple]:
    rows = []
    for f in sorted((ROOT / "tests").glob("test_*.py")):
        total = 0
        for fn in [n for n in ast.parse(f.read_text(encoding="utf-8")).body if isinstance(n, ast.FunctionDef)]:
            if not fn.name.startswith("test_"):
                continue
            cases = 1
            for d in fn.decorator_list:
                if (isinstance(d, ast.Call) and getattr(d.func, "attr", "") == "parametrize" and len(d.args) > 1
                        and isinstance(d.args[1], (ast.List, ast.Tuple))):
                    cases *= len(d.args[1].elts)
            total += cases
        rows.append((f.name, total))
    return rows


def build_reference() -> str:
    routes, settings, tests = collect_routes(), collect_settings(), collect_tests()
    out = ["# Tham chiếu (sinh tự động từ code)", "",
           "> File này do `python tools/build_bundle.py` tạo ra. Đừng sửa tay: sửa code rồi chạy lại.", "",
           f"## API ({len(routes)} route)", "",
           "Xác thực bằng JWT (`Authorization: Bearer <token>`) trừ khi ghi 'Công khai'. Operator và Viewer chỉ thấy "
           "thiết bị được gán (ngoài phạm vi trả 404). Giao diện thử: `/docs` (OpenAPI) khi chạy backend. "
           "Hợp đồng WebSocket: [websocket.md](websocket.md).", "",
           "| Method | Đường dẫn | Quyền | Mô tả |", "| --- | --- | --- | --- |"]
    out += [f"| {r['method']} | `{r['path']}` | {r['who']} | {r['desc']} |" for r in routes]
    out += ["", f"## Biến môi trường ({len(settings)})", "",
            "Đặt trong `backend/.env` (mẫu: `backend/.env.example`) hoặc biến môi trường; tên không phân biệt hoa thường.", "",
            "| Biến | Kiểu | Mặc định | Ghi chú |", "| --- | --- | --- | --- |"]
    out += [f"| `{n}` | `{t}` | `{d}` | {c} |" for n, t, d, c in settings]
    out += ["", f"## Bộ kiểm thử ({sum(c for _, c in tests)} ca)", "",
            "| File | Số ca |", "| --- | --- |"]
    out += [f"| `{n}` | {c} |" for n, c in tests]
    out += ["", "Số ca đã tính cả `parametrize`. Chạy: `pytest` từ thư mục gốc (dùng SQLite, không cần MySQL/Mosquitto).", ""]
    return "\n".join(out)


# ----------------------------------------------------------------------------- bản tổng hợp một file
ORDER = ["README.md", "docs/", "database/", "backend/requirements.txt", "backend/requirements-dev.txt",
         "backend/.env.example", "backend/app/config.py", "backend/app/db.py", "backend/app/models/",
         "backend/app/schemas.py", "backend/app/errors.py", "backend/app/events.py", "backend/app/security/",
         "backend/app/services/",
         "backend/app/audit.py", "backend/app/deps.py", "backend/app/access.py", "backend/app/lifecycle.py",
         "backend/app/broker_admin.py", "backend/app/accounts.py", "backend/app/ingest.py",
         "backend/app/mqtt_client.py", "backend/app/commands.py", "backend/app/device_params.py",
         "backend/app/device_config.py", "backend/app/alerts.py", "backend/app/realtime.py",
         "backend/app/routers/", "backend/app/main.py", "backend/scripts/", "tests/", "tools/"]


def _rank(rel: str) -> tuple:
    for i, prefix in enumerate(ORDER):
        if rel == prefix or (prefix.endswith("/") and rel.startswith(prefix)):
            return (i, rel)
    return (len(ORDER), rel)


def build_source_md(files: list[pathlib.Path]) -> str:
    rels = sorted((str(p.relative_to(ROOT)) for p in files), key=_rank)
    texts = {}
    for r in rels:
        try:
            texts[r] = (ROOT / r).read_text(encoding="utf-8")
        except UnicodeDecodeError:
            texts[r] = f"Binary artifact ({(ROOT / r).stat().st_size} bytes); included in the ZIP.\n"
    total = sum(len(t.splitlines()) for t in texts.values())
    out = ["# Mã nguồn đầy đủ: backend và CSDL hệ thống quản lý cấp nước thông minh", "",
           f"{len(rels)} file, {total} dòng. Sinh bởi `tools/build_bundle.py`; muốn chạy được hãy dùng `wms-backend.zip` "
           "hoặc làm theo README.", "", "## Mục lục", "", "| # | File | Dòng |", "| --- | --- | --- |"]
    out += [f"| {i} | `{r}` | {len(texts[r].splitlines())} |" for i, r in enumerate(rels, 1)]
    for i, r in enumerate(rels, 1):
        text = texts[r]
        out += ["", "---", "", f"## {i}. `{r}`", ""]
        if not text.strip():
            out.append("_(file trống)_")
            continue
        fence = "~~~~~"                     # tilde: nội dung có chứa ``` vẫn không làm hỏng khối mã
        out += [f"{fence}{LANG.get(pathlib.Path(r).suffix, 'text')}", text.rstrip("\n"), fence]
    return "\n".join(out) + "\n"


def build_zip(files: list[pathlib.Path], path: pathlib.Path) -> int:
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for p in files:
            info = zipfile.ZipInfo.from_file(p, arcname="wms-backend/" + str(p.relative_to(ROOT)))
            if p.suffix == ".sh" or p.name == "build_bundle.py":        # một số hệ thống file bỏ qua chmod: ghi quyền thẳng vào zip
                info.external_attr = (stat.S_IFREG | 0o755) << 16
            z.writestr(info, p.read_bytes(), compress_type=zipfile.ZIP_DEFLATED)
    return len(files)


def main() -> None:
    DIST.mkdir(exist_ok=True)
    (ROOT / "docs").mkdir(exist_ok=True)
    (ROOT / "docs" / "reference.md").write_text(build_reference(), encoding="utf-8")   # trước khi liệt kê file
    for sh in ROOT.rglob("*.sh"):
        sh.chmod(sh.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    files = source_files()
    (DIST / "wms_source_full.md").write_text(build_source_md(files), encoding="utf-8")
    n = build_zip(files, DIST / "wms-backend.zip")
    import shutil
    shutil.copyfile(DIST / "wms-backend.zip", DIST / "wms-team-source.zip")
    print(f"docs/reference.md, dist/wms_source_full.md, dist/wms-backend.zip ({n} file)")


if __name__ == "__main__":
    main()
