from __future__ import annotations

import tarfile
import zipfile
from pathlib import Path


def _only_artifact(pattern: str) -> Path:
    matches = sorted(Path("dist").glob(pattern))
    if len(matches) != 1:
        raise SystemExit(f"expected exactly one {pattern} artifact, found {len(matches)}")
    return matches[0]


def main() -> None:
    sdist = _only_artifact("*.tar.gz")
    wheel = _only_artifact("*.whl")

    with tarfile.open(sdist, "r:gz") as archive:
        sdist_files = {member.name for member in archive.getmembers() if member.isfile()}

    if not any(name.endswith("/tests/conftest.py") for name in sdist_files):
        raise SystemExit("source distribution is missing tests/conftest.py")
    test_modules = sorted(
        name for name in sdist_files if "/tests/test_" in name and name.endswith(".py")
    )
    if not test_modules:
        raise SystemExit("source distribution contains no test modules")

    with zipfile.ZipFile(wheel) as archive:
        wheel_files = archive.namelist()
    if any(name.startswith("tests/") for name in wheel_files):
        raise SystemExit("wheel must not contain the repository test suite")

    print(
        f"validated {sdist.name}: tests/conftest.py and "
        f"{len(test_modules)} test modules are present"
    )
    print(f"validated {wheel.name}: repository tests are absent")


if __name__ == "__main__":
    main()
