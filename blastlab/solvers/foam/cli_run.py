"""Interactive CLI flow for `python -m blastlab --cli DIM --solver
blastfoam`. Kept separate from cli.py/legacy so the byte-pinned native
prompt flow is untouched."""

from . import env


def run(dim):
    dim = str(dim).lower().lstrip('-')[0]
    print("blastlab - blastFoam (WSL) backend")
    print("  Checking WSL blastFoam availability...")
    ok, detail = env.check_available()
    print(f"  {detail}")
    if not ok:
        raise SystemExit(
            "  The blastFoam backend is unavailable. Verify that WSL "
            f"distro '{env.WSL_DISTRO}' exists and that\n  "
            f"{env.FOAM_BASHRC} sources a build providing: "
            + ", ".join(env.NEEDED_TOOLS))
    raise SystemExit(
        f"  The blastFoam CLI workflow for {dim}D cases is not "
        f"implemented yet.")
