from pathlib import Path

from backend.app.main import app


LEGACY_PATHS = {
    "/api/v1/records/{record_id}/notes",
    "/api/v1/records/{record_id}/outcome-decision",
    "/api/v1/records/{record_id}/close",
    "/api/v1/records/{record_id}/reopen",
    "/api/v1/records/{record_id}/interview-schedule",
}


def test_legacy_routes_remain_available_but_are_marked_deprecated():
    operations = app.openapi()["paths"]
    for path in LEGACY_PATHS:
        assert path in operations
        assert operations[path]["post"]["deprecated"] is True


def test_production_frontend_has_no_legacy_route_owner():
    frontend_root = Path(__file__).parents[1] / "frontend" / "src"
    source_files = [
        path for path in frontend_root.rglob("*")
        if path.suffix in {".ts", ".tsx"} and not path.name.endswith(".test.tsx")
    ]
    combined_source = "\n".join(path.read_text(encoding="utf-8") for path in source_files)
    for suffix in ("/notes", "/outcome-decision", "/close", "/reopen", "/interview-schedule"):
        assert suffix not in combined_source


def test_route_ownership_document_lists_every_legacy_route():
    document = (Path(__file__).parents[1] / "docs" / "route-ownership.md").read_text(encoding="utf-8")
    for path in LEGACY_PATHS:
        assert path.replace("{record_id}", "{id}") in document
