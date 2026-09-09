#!/usr/bin/env python3
"""Lemon Pi camera pipeline.
Snaps a photo, has Claude analyze the plant, and texts the photo + report
to Telegram. Also keeps one dated frame per day for the timelapse.
Run manually:  python3 ~/lemonpi/camera/snap.py
"""
import base64, datetime, pathlib, subprocess, sys, time
import requests

HERE = pathlib.Path(__file__).resolve().parent
PHOTOS = HERE / "photos"; PHOTOS.mkdir(exist_ok=True)
MODEL = "claude-sonnet-5"          # switch to claude-haiku-4-5-20251001 to spend even less

# Crop out the desk on the right — x,y,width,height as fractions (0-1) of
# the full sensor frame. 0.7 keeps the left 70%. Tune this with
# test_shot.sh until the framing looks right, then copy the same value here.
ROI = "0,0,0.7,1"

def load_secrets(p):
    d = {}
    for ln in open(p):
        ln = ln.strip()
        if ln and not ln.startswith("#") and "=" in ln:
            k, v = ln.split("=", 1); d[k.strip()] = v.strip()
    return d

S = load_secrets(HERE / "secrets.env")
TG, CHAT, KEY = S["TELEGRAM_TOKEN"], S["TELEGRAM_CHAT_ID"], S["ANTHROPIC_API_KEY"]

def tg_text(msg):
    requests.post(f"https://api.telegram.org/bot{TG}/sendMessage",
                  data={"chat_id": CHAT, "text": msg}, timeout=60)

def capture(frame):
    """Run rpicam-still, retrying once after a short pause — camera-not-ready
    right after boot is a known flaky failure. Raises with the ACTUAL
    libcamera stderr on failure, not just an exit code, so a Telegram alert
    is actually useful instead of just 'exit 255'."""
    cmd = ["rpicam-still", "-n", "--autofocus-mode", "auto",
           "-t", "5000", "--roi", ROI, "-o", str(frame)]
    last_err = f"exit {-1}"
    for attempt in range(2):
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode == 0:
            return
        tail = r.stderr.strip().splitlines()
        last_err = tail[-1] if tail else f"exit {r.returncode}"
        if attempt == 0:
            time.sleep(5)
    raise RuntimeError(f"rpicam-still failed after retry: {last_err}")

def main():
    now = datetime.datetime.now()
    frame = PHOTOS / f"{now:%Y-%m-%d}.jpg"

    # 1. capture (no preview so it won't fight the display; 5s for autofocus;
    #    cropped to just the plant via ROI)
    capture(frame)
    img = base64.b64encode(frame.read_bytes()).decode()

    # 2. analyze with Claude
    prompt = ("You're reviewing today's photo of an indoor variegated lemon tree under a "
              "grow light. Look closely at the leaves and foliage before answering — "
              "examine as many individual leaves as you can make out for spots, "
              "discoloration, yellowing, browning, curling, holes, webbing, sticky "
              "residue, or small pests/eggs, including faint or early signs, not just "
              "obvious damage. Then reply in EXACTLY this compact format and nothing "
              "else:\n\n"
              "Health: N/10 — <2-4 word status>\n"
              "<one short summary sentence>\n"
              "• Foliage: <a few words>\n"
              "• Pests/disease: <a few words>\n"
              "• Soil: <a few words>\n"
              "• Action: <one short thing to do, or 'nothing today'>\n\n"
              "Keep every line short and phone-friendly. Grow-light color looks intense, "
              "so account for that. If you spot anything even slightly off, name it "
              "specifically in the Foliage or Pests/disease line instead of staying "
              "vague. If it all genuinely looks healthy after a close look, say so and "
              "score high.")
    r = requests.post("https://api.anthropic.com/v1/messages",
        headers={"x-api-key": KEY, "anthropic-version": "2023-06-01",
                 "content-type": "application/json"},
        json={"model": MODEL, "max_tokens": 220,
              "messages": [{"role": "user", "content": [
                  {"type": "image", "source": {"type": "base64",
                      "media_type": "image/jpeg", "data": img}},
                  {"type": "text", "text": prompt}]}]},
        timeout=90)
    r.raise_for_status()
    data = r.json()
    text_blocks = [b["text"] for b in data.get("content", []) if b.get("type") == "text"]
    if not text_blocks:
        raise RuntimeError(f"Claude response had no text block: {data}")
    report = "\n".join(text_blocks).strip()

    # 3. deliver photo + report to Telegram
    header = f"\U0001F34B Lemon Pi — {now:%b %-d, %-I:%M %p}"
    caption = f"{header}\n\n{report}"
    with open(frame, "rb") as f:
        if len(caption) <= 1024:
            requests.post(f"https://api.telegram.org/bot{TG}/sendPhoto",
                data={"chat_id": CHAT, "caption": caption},
                files={"photo": f}, timeout=90).raise_for_status()
        else:
            requests.post(f"https://api.telegram.org/bot{TG}/sendPhoto",
                data={"chat_id": CHAT, "caption": header},
                files={"photo": f}, timeout=90).raise_for_status()
            tg_text(report)
    print("Sent", frame.name)

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        try: tg_text(f"⚠️ Lemon Pi camera run failed: {e}")
        except Exception: pass
        print("ERROR:", e, file=sys.stderr); sys.exit(1)
