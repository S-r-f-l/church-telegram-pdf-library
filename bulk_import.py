#!/usr/bin/env python3
"""
Bulk Import Script
Reads all PDFs from a Telegram group and forwards them to the group
so the bot (in import mode) can save them automatically.

Usage:
  1. Start import mode in the group: /startimport
  2. Run: python bulk_import.py
  3. Stop import mode when done: /stopimport
"""

import asyncio
from telethon import TelegramClient
from telethon.tl.types import MessageMediaDocument

# ── Config ────────────────────────────────────────────────────────────────────
# Get API credentials from https://my.telegram.org
API_ID   = 0          # replace with your api_id (integer)
API_HASH = ""         # replace with your api_hash (string)

# The group where your PDFs are stored (and where the bot is a member)
# Use the group's @username, invite link, or numeric ID
GROUP    = "your_group_username_or_id"

# How many seconds to wait between forwards (avoid hitting Telegram rate limits)
DELAY    = 1.5
# ──────────────────────────────────────────────────────────────────────────────

async def main():
    async with TelegramClient("bulk_import_session", API_ID, API_HASH) as client:
        print("Connected. Scanning group history for PDFs...")

        count = 0
        skipped = 0

        async for message in client.iter_messages(GROUP, reverse=True):
            if not message.media or not isinstance(message.media, MessageMediaDocument):
                continue

            doc = message.media.document
            if not doc:
                continue

            # Check if it's a PDF
            mime = next((a.mime_type for a in doc.attributes
                         if hasattr(a, "mime_type")), None) or doc.mime_type
            is_pdf = mime == "application/pdf" or any(
                getattr(a, "file_name", "").endswith(".pdf")
                for a in doc.attributes
            )

            if not is_pdf:
                continue

            filename = next(
                (getattr(a, "file_name", "") for a in doc.attributes
                 if hasattr(a, "file_name")), "unknown.pdf"
            )

            try:
                await client.forward_messages(GROUP, message)
                count += 1
                print(f"[{count}] Forwarded: {filename}")
                await asyncio.sleep(DELAY)
            except Exception as e:
                skipped += 1
                print(f"  ⚠️  Skipped: {filename} — {e}")

        print(f"\nDone! {count} PDFs forwarded, {skipped} skipped.")
        print("Now run /stopimport in the group.")

if __name__ == "__main__":
    asyncio.run(main())
