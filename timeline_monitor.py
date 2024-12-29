import asyncio
import textwrap
from html import escape
import os
from dotenv import load_dotenv
from datetime import datetime
import humanize

from atproto import AsyncClient

load_dotenv()

FETCH_NOTIFICATIONS_DELAY_SEC = 5

def process_post(post, seen_posts):
    if post.cid not in seen_posts:
        author = post.author.display_name or post.author.handle
        created_at = post.indexed_at
        timestamp = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
        age = humanize.naturaltime(datetime.now().astimezone() - timestamp)

        text = textwrap.fill(post.record.text, width=70)
        text = escape(text)

        print(f"\n\033[94m[{created_at}] ({age}) \033[92m{author}\033[0m ({post.author.did}):\n")
        print(text)

        seen_posts.add(post.cid)
        return True
    return False

async def main() -> None:
    client = AsyncClient()
    await client.login(os.getenv('BSKY_HANDLE'), os.getenv('BSKY_APP_PASSWORD'))

    print("Monitoring timeline for new posts...")

    seen_posts = set()
    cursor = None
    oldest = None

    while True:
        try:
            timeline = await client.get_timeline(limit=1, cursor=cursor)
            print(f"Got {len(timeline.feed)} new posts")
            if not timeline.feed and not seen_posts:
                cursor = timeline.cursor # startup go till we get a post since muted posts count in the limit but aren't returned
                continue

            for fv in timeline.feed:
                if process_post(fv.post, seen_posts):
                    cursor = timeline.cursor
                else:
                    cursor = None
                at = datetime.fromisoformat(fv.post.indexed_at.replace('Z', '+00:00'))
                if oldest is None or at < oldest:
                    oldest = at
                    cursor = None # never page older
            
        except Exception as e:
            print(f"Error: {e}")
            cursor = None
            await asyncio.sleep(10)
            continue

        await asyncio.sleep(FETCH_NOTIFICATIONS_DELAY_SEC)

if __name__ == '__main__':
    asyncio.run(main())