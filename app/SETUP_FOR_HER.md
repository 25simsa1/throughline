# Throughline, the clickable version

A small app that lets you run the pipeline by clicking instead of typing menu numbers.
It opens in your web browser but runs entirely on your own Mac. Nothing is uploaded anywhere.

## Running it (once it is set up)

Double-click **Throughline.app**. A browser tab opens with your chapters. Pick a chapter on
the left, then click the steps in order.

- Step 1 Ingest, reads the source PDFs
- Step 2 Extract, pulls claims, concepts and quotes
- Step 3 Connect, finds cross-source connections
- Step 4 Review, this is your part. Each connection has a **Keep** and a **Drop** button and a
  note box. What you click is saved straight to the report, so you never edit the markdown by hand.
- Step 5 Draft, writes prose for the connections you kept

To stop it, quit Throughline (Cmd-Q) or close the Terminal window if one opened.

## First-time setup on a new Mac

The app itself is tiny, but the pipeline underneath needs three things installed once. This is
the heavy part and it only has to be done a single time.

1. **Python 3.** Most Macs already have it. Check by opening Terminal and running `python3 --version`.
   If it is missing, install it from python.org.

2. **The Throughline folder.** Copy the whole `throughline` folder to your Mac (for example into
   your home folder). Then in Terminal, from inside that folder, set up its environment once

   ```
   cd ~/throughline
   python3 -m venv .venv
   .venv/bin/pip install -r requirements.txt
   ```

3. **Ollama, the local model runner.** Download it from ollama.com, then pull the models the
   pipeline uses (this downloads a few GB, one time)

   ```
   ollama pull qwen3:14b
   ollama pull granite-embedding:30m
   ```

That is it. From then on, double-click Throughline.app whenever you want to use it.

## If macOS blocks the app the first time

Because the app is not signed by a registered developer, the first open may be blocked.
**Right-click** Throughline.app and choose **Open**, then confirm. You only do this once.
If it still refuses, run this in Terminal from the folder that holds the app

```
xattr -dr com.apple.quarantine Throughline.app
```

## Good to know

- The Review step is the only one that is truly yours. The other steps just run the tools; you
  can always re-run any of them.
- Your keep and drop choices, and any notes, are written into the chapter's `report.md`, the
  same file as before, so nothing about the underlying project changes.
- If the app says the Python environment was not found, it means step 2 above has not been done
  in that folder yet.
