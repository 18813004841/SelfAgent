"""Positive/negative regression for the physical Tools ownership rule."""
from pathlib import Path
import tempfile
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from check_architecture import check_tools_ownership  # noqa: E402


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="selfagent-boundary-") as raw:
        root = Path(raw)
        (root / "Tools" / "machine-control").mkdir(parents=True)
        (root / "Tools" / "machine-control" / "owned.py").write_text("# ok", encoding="utf-8")
        assert check_tools_ownership(root) == []
        (root / "Tools" / "wrong.py").write_text("# reject", encoding="utf-8")
        errors = check_tools_ownership(root)
        assert any("business file outside project boundary" in item for item in errors), errors
    print("architecture boundary positive/negative validation passed")


if __name__ == "__main__":
    main()
