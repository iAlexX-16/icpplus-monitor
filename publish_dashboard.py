"""Build a public dashboard without names, logs or booking-session URLs."""

import json
from pathlib import Path
from shutil import copyfile


def build_public_dashboard(root: Path, output: Path) -> None:
    profiles = json.loads((root / "data/profiles.json").read_text(encoding="utf-8"))
    status = json.loads((root / "data/status.json").read_text(encoding="utf-8"))
    public_profiles = []
    public_results = {}
    for index, profile in enumerate(profiles, start=1):
        public_id = f"profile{index}"
        public_profiles.append({
            "id": public_id,
            "name": f"Perfil {index}",
            "enabled": profile.get("enabled", True),
            "province": profile["province"],
            "procedure_name": profile["procedure_name"],
        })
        result = status.get("profiles", {}).get(profile["id"])
        if result:
            public_results[public_id] = {
                "status": result["status"],
                "last_check": result.get("last_check"),
                "url": "https://icp.administracionelectronica.gob.es/icpplustiem/index.html",
            }
    (output / "data").mkdir(parents=True, exist_ok=True)
    copyfile(root / "index.html", output / "index.html")
    (output / "data/profiles.json").write_text(
        json.dumps(public_profiles, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (output / "data/status.json").write_text(
        json.dumps({"profiles": public_results, "last_run": status.get("last_run")}, indent=2),
        encoding="utf-8",
    )


if __name__ == "__main__":
    root = Path(__file__).resolve().parent
    build_public_dashboard(root, root / "_site")
