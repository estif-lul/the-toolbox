"""The pipeline CLI. `make <target>` is a thin wrapper around this; it also works without Make:

    uv run python -m pipeline.run film
    uv run python -m pipeline.run narration --only s05 --force s05
    uv run python -m pipeline.run smoke --profile free

Every stage command validates storyboard.json first; an invalid storyboard stops the run before
any model call.
"""

from __future__ import annotations

import argparse
import os
import sys

from .common import env
from .common.log import start_run

STAGES = {
    # name: (step that implements it, one-line description)
    "script": (1, "draft storyboard.draft.json with Gemini from DESIGN.md + the schema"),
    "narration": (2, "Gemini TTS per narration line (cached) -> outputs/narration/timing.json"),
    "audition": (2, "the same lines in each candidate stock voice, one request per voice"),
    "radio": (2, "radio cut: narration + placeholder music on black, subtitles"),
    "refs": (3, "style + character reference sheets (candidates + contact sheets)"),
    "keyframes": (3, "per-shot keyframe candidates with crop previews"),
    "kenburns": (3, "Ken Burns clip per shot from the chosen keyframe"),
    "shots": (4, "Wan 2.2 moving shots on Kaggle (push / wait / pull)"),
    "music": (4, "ACE-Step score candidates on Kaggle + audition"),
    "assemble": (5, "edit: both aspect ratios, ducking, loudness, subtitles, end card"),
    "film": (5, "the whole pipeline end to end"),
    "costs": (6, "COSTS.md tables from runs.jsonl"),
}


def _parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--profile", default=None, help="provider profile from config/providers.yaml (default: free)")
    common.add_argument("--force", nargs="*", metavar="SHOT", default=None,
                        help="regenerate regardless of cache (all, or only the given shots)")
    common.add_argument("--dry-run", action="store_true", help="print what would run (FFmpeg commands, calls)")
    common.add_argument("--only", nargs="*", metavar="ITEM", default=None, help="limit to these shots / checks")

    ap = argparse.ArgumentParser(prog="pipeline.run", description=__doc__.split("\n\n")[0], parents=[common])
    sub = ap.add_subparsers(dest="cmd", required=True, metavar="COMMAND")
    sub.add_parser("smoke", parents=[common], help="one minimal call per provider, logged to runs.jsonl")
    sub.add_parser("models", parents=[common], help="list the models the API keys can see")
    v = sub.add_parser("validate", parents=[common], help="JSON Schema + semantic checks of storyboard.json")
    v.add_argument("--if-present", action="store_true", help="succeed quietly if storyboard.json does not exist yet")
    v.add_argument("--path", default=None, help="storyboard file (default: storyboard.json)")
    for name, (step, desc) in STAGES.items():
        sp = sub.add_parser(name, parents=[common], help=f"{desc} [Step {step}]")
        if name == "narration":
            sp.add_argument("--batch-lines", type=int, default=None,
                            help="max lines per TTS request (default: tts params batch_lines)")
            sp.add_argument("--verify", action="store_true",
                            help="hear every line back (transcribe) and compare with its text; no TTS calls")
        if name == "audition":
            sp.add_argument("--role", required=True, help="voice role in storyboard.voices (narrator, dad)")
            sp.add_argument("--model", default=None, help="TTS model id from the tts chain (default: the primary)")
            sp.add_argument("--voices", nargs="*", default=None, help="stock voices (default: the role's candidates)")
            sp.add_argument("--lines", nargs="*", default=None, help="line refs like s01:0 (default per role)")
            sp.add_argument("--no-style", action="store_true", help="send no style instruction (E03)")
        if name == "music":
            sp.add_argument("--placeholder", action="store_true",
                            help="only the code-generated placeholder pad for the current timeline")
        if name == "shots":
            sp.add_argument("--push", action="store_true", help="only push stale jobs to Kaggle")
            sp.add_argument("--pull", action="store_true", help="only pull and ingest finished clips")
    return ap


def cmd_validate(args) -> int:
    from rich.console import Console

    from .common import storyboard as sbm

    console = Console()
    path = args.path or sbm.STORYBOARD
    if not os.path.exists(path):
        if args.if_present:
            console.print("[dim]validate: no storyboard.json yet, skipping[/dim]")
            return 0
        console.print(f"[red]validate: {path} not found[/red]")
        return 1
    sb = sbm.load_storyboard(path)
    report = sbm.validate(sb, timing=sbm.load_timing())
    for w in report.warnings:
        console.print(f"[yellow]warning[/yellow] {w}")
    for e in report.errors:
        console.print(f"[red]error[/red]   {e}")
    tl = sbm.timeline(sb, sbm.load_timing())
    console.print(f"{len(sb.get('shots', []))} shots, {tl['total_s']:.1f}s incl. end card "
                  f"({'estimated from word count' if tl['estimated'] else 'measured TTS timing'}); "
                  f"{len(report.errors)} error(s), {len(report.warnings)} warning(s)")
    return 0 if report.ok else 1


def main(argv: list[str] | None = None) -> int:
    # Windows consoles and pipes default to cp1252, which cannot print Amharic (Ge'ez script).
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    args = _parser().parse_args(argv)
    env.load_env()
    if os.environ.get("FORCE") == "1" and args.force is None:
        args.force = []  # FORCE=1 means "everything"
    from .providers.registry import default_profile

    profile = args.profile or default_profile()
    start_run(profile, dry_run=args.dry_run)
    try:
        if args.cmd == "smoke":
            from .smoke import run_smoke

            rows = run_smoke(profile, args.only)
            return 0 if all(r.ok for r in rows) else 1
        if args.cmd == "models":
            from .smoke import list_models

            list_models(profile)
            return 0
        if args.cmd == "validate":
            return cmd_validate(args)
        if args.cmd == "script":
            # The one stage that does not read storyboard.json (it drafts an alternative to it).
            from .script import main as script_main

            return script_main(profile, force=args.force is not None, dry_run=args.dry_run)
        if args.cmd == "narration":
            from .narration import run_narration, run_verify

            if args.verify:
                return 0 if not run_verify(profile, force=args.force is not None)["bad"] else 1
            res = run_narration(profile, only=args.only, force=args.force, dry_run=args.dry_run,
                                batch_lines=args.batch_lines)
            return 0 if res["status"] == "dry_run" or (not res.get("missing") and not res.get("errors")) else 1
        if args.cmd == "audition":
            from .narration import run_audition

            run_audition(args.role, profile=profile, model=args.model, voices=args.voices, refs=args.lines,
                         no_style=args.no_style, dry_run=args.dry_run)
            return 0
        if args.cmd == "radio":
            from .assemble import run_radio

            res = run_radio(dry_run=args.dry_run)
            return 0 if res.get("status") == "dry_run" or res.get("ok") else 1
        if args.cmd == "music" and args.placeholder:
            from .common import storyboard as sbm
            from .music import placeholder

            total = sbm.timeline(sbm.load_storyboard(), sbm.load_timing())["total_s"]
            print(f"music: placeholder pad, {total:.1f}s -> {placeholder(total, dry_run=args.dry_run)}")
            return 0
        step, desc = STAGES[args.cmd]
        print(f"{args.cmd}: not implemented yet ({desc}); it is built in Step {step}", file=sys.stderr)
        return 2
    except env.MissingKeyError as exc:
        print(f"\n{exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(main())
