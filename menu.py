"""A number-menu front end for non-technical use. Double-clicking
Throughline.command runs this. Every action is a plain sentence, every
failure is a plain sentence, nobody needs to remember a command."""
from __future__ import annotations

import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import throughline

ROOT = Path(__file__).resolve().parent
CHAPTERS = ROOT / "chapters"
MODEL_FILE = ROOT / "model.txt"


def say(text=""):
    print(text)


def ask(prompt):
    try:
        return input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        say()
        sys.exit(0)


def ollama_running() -> bool:
    try:
        urllib.request.urlopen("http://localhost:11434/api/tags", timeout=2)
        return True
    except Exception:
        return False


def ensure_ollama() -> bool:
    if ollama_running():
        return True
    say("Starting the AI engine (Ollama)...")
    subprocess.run(["open", "-a", "Ollama"], capture_output=True)
    for _ in range(30):
        time.sleep(2)
        if ollama_running():
            say("Ready.")
            return True
    say("I could not start Ollama. Open the Ollama app from your")
    say("Applications folder, wait a moment, then try again.")
    return False


def chapters() -> list[str]:
    if not CHAPTERS.is_dir():
        return []
    return sorted(p.name for p in CHAPTERS.iterdir()
                  if p.is_dir() and (p / "sources").is_dir())


def pick_chapter() -> str | None:
    names = chapters()
    if not names:
        say("No chapters yet. Choose 1 first to start one.")
        return None
    if len(names) == 1:
        return names[0]
    say("Which chapter?")
    for i, n in enumerate(names, 1):
        say(f"  {i}. {n}")
    choice = ask("Type its number: ")
    try:
        return names[int(choice) - 1]
    except (ValueError, IndexError):
        say("That was not one of the numbers.")
        return None


def run(args) -> int:
    os.chdir(ROOT)
    try:
        return throughline.main(args)
    except SystemExit as e:
        return int(e.code or 0)
    except Exception as e:
        say(f"Something went wrong: {e}")
        return 1


def do_new():
    name = ask("A short name for this chapter (letters and dashes, like chapter-2): ")
    name = name.replace(" ", "-").lower() or "chapter"
    run(["new", name])
    subprocess.run(["open", str(CHAPTERS / name / "sources")])
    subprocess.run(["open", "-e", str(CHAPTERS / name / "thesis.md")])
    say()
    say("Two windows just opened.")
    say("  1. A folder. Drop your sources in it (PDFs, EPUBs, even photos).")
    say("  2. A text file. Replace its contents with your thesis note.")
    say("When both are done, come back here and choose 2.")


def do_read():
    ch = pick_chapter()
    if not ch or not ensure_ollama():
        return
    say()
    say("Reading your sources. For a real stack of papers this takes a")
    say("while, sometimes an hour or more. Leave this window open, your")
    say("computer is allowed to do other things meanwhile.")
    say()
    rc = run(["ingest", ch])
    if rc != 0:
        return
    run(["extract", ch, "--resume"])
    run(["verify", ch])
    say()
    say("Done reading. Choose 3 to find connections.")


def do_connect():
    ch = pick_chapter()
    if not ch or not ensure_ollama():
        return
    say()
    say("Looking for connections across your sources. This usually takes")
    say("twenty minutes or so. Leave the window open.")
    say()
    rc = run(["connect", ch])
    if rc != 0:
        return
    subprocess.run(["open", "-e", str(CHAPTERS / ch / "report.md")])
    say()
    say("The report just opened. For each connection, change the line")
    say('    Decision: candidate')
    say('to  Decision: keep   or   Decision: drop')
    say("Save the file, then come back and choose 4.")


def do_draft():
    ch = pick_chapter()
    if not ch or not ensure_ollama():
        return
    say()
    say("Writing drafts for everything you marked keep...")
    rc = run(["draft", ch])
    if rc == 0:
        subprocess.run(["open", str(CHAPTERS / ch / "drafts")])
        say()
        say("The drafts folder just opened. Each draft ends with notes that")
        say("label every sentence as verified evidence or interpretation.")


def do_status():
    ch = pick_chapter()
    if not ch:
        return
    say()
    run(["verify", ch])
    run(["status", ch])


def main():
    if MODEL_FILE.exists():
        os.environ.setdefault("THROUGHLINE_MODEL",
                              MODEL_FILE.read_text().strip())
    say()
    say("=" * 56)
    say("  THROUGHLINE")
    say("  It reads your sources, proposes connections with")
    say("  verified quotations, and drafts what you keep.")
    say("=" * 56)
    while True:
        say()
        say("  1. Start a new chapter")
        say("  2. Read my sources        (slow, leave the window open)")
        say("  3. Find connections       (opens the report when done)")
        say("  4. Write drafts for my keeps")
        say("  5. Check on a chapter")
        say("  0. Quit")
        say()
        choice = ask("Type a number and press Return: ")
        actions = {"1": do_new, "2": do_read, "3": do_connect,
                   "4": do_draft, "5": do_status}
        if choice == "0":
            say("Bye.")
            return
        action = actions.get(choice)
        if action:
            action()
        else:
            say("That was not one of the numbers, try again.")


if __name__ == "__main__":
    main()
