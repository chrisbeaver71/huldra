"""Regenerate profile_catalog.json from the corrected default catalog.

Usage:
    python scripts/save_default_catalog.py [--huldra-home PATH]

Defaults to $HULDRA_HOME or the parent of ops/hermes.
"""
import argparse
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "source"))
from huldra_profiles import create_v1_default_catalog


def main():
    parser = argparse.ArgumentParser(description="Regenerate profile catalog JSON")
    parser.add_argument(
        "--huldra-home",
        type=pathlib.Path,
        default=None,
        help="HULDRA_HOME root (default: $HULDRA_HOME or auto-detect)",
    )
    args = parser.parse_args()

    huldra_home = args.huldra_home
    if huldra_home is None:
        import os
        configured = os.environ.get("HULDRA_HOME")
        if configured:
            huldra_home = pathlib.Path(configured)
        else:
            # Auto-detect: walk up from this script to find ops/hermes
            here = pathlib.Path(__file__).resolve()
            for parent in (here, *here.parents):
                if (parent / "ops" / "hermes").is_dir():
                    huldra_home = parent
                    break
            if huldra_home is None:
                huldra_home = pathlib.Path.cwd()

    catalog = create_v1_default_catalog()
    out = huldra_home / "config" / "profile_catalog.json"
    catalog.save(out)
    print(f"Saved {len(catalog.profiles)} profiles to {out}")
    for p in catalog.profiles:
        tag = "WORKER" if p.role == "worker" or p.optional else "PRIMARY"
        print(f"  [{tag}] {p.id}: {p.name}")
        if p.model_artifact:
            print(f"    model: {p.model_artifact.path}")
            if p.model_artifact.sha256:
                print(f"    sha256: {p.model_artifact.sha256[:16]}...")
            if p.model_artifact.size_bytes:
                print(f"    size: {p.model_artifact.size_bytes:,}")


if __name__ == "__main__":
    main()
