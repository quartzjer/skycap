import asyncio
import os
import argparse
from dotenv import load_dotenv
from atproto import AsyncClient
from datetime import datetime
import humanize  # Add this import

load_dotenv()

def get_post_image_alt_texts(post):
    """Extract all image alt texts from a post"""
    if not hasattr(post, 'embed') or post.embed is None:
        return []
    
    if post.embed.py_type == 'app.bsky.embed.images#view':
        alt_texts = []
        for img in post.embed.images:
            if hasattr(img, 'alt') and img.alt:
                alt_texts.append(img.alt)
        return alt_texts
    
    return []

def format_embed_info(post):
    """Format embed information for display"""
    if not hasattr(post, 'embed') or post.embed is None:
        return None
    
    embed = post.embed
    
    if embed.py_type == 'app.bsky.embed.images#view':
        alt_texts = get_post_image_alt_texts(post)
        image_info = f"📷 {len(embed.images)} image(s)"
        if alt_texts:
            image_info += "\n" + "\n".join(f"└─ Alt: {alt}" for alt in alt_texts)
        return image_info
    elif embed.py_type == 'app.bsky.embed.record#view':
        if hasattr(embed.record, 'value') and hasattr(embed.record.value, 'text'):
            return f"💬 Quoted: {embed.record.value.text[:100]}..."
        return None
    elif 'external' in embed.py_type:
        return f"🔗 Link: {embed.external.title}"
    elif 'video' in embed.py_type:
        return f"🎥 Video: {embed.video.mime_type}"
    
    return None

def format_post_content(post, indent_level=0):
    """Format a post's content with specified indentation"""
    indent = "    " * indent_level
    record = post.record
    author = post.author
    
    created_at = datetime.fromisoformat(record.created_at.replace('Z', '+00:00'))
    created_str = humanize.naturaltime(datetime.now().astimezone() - created_at)

    summary_lines = [
        f"{indent}[@{author.handle}] {author.display_name}",
        f"{indent}└─ {record.text or '(no text content)'}"
    ]

    embed_info = format_embed_info(post)
    if embed_info:
        summary_lines.append(f"{indent}└─ {embed_info}")

    summary_lines.append(
        f"{indent}└─ 👍 {post.like_count} 🔄 {post.repost_count} 💬 {post.reply_count} "
        f"📝 {post.quote_count} • {created_str}"
    )
    
    return summary_lines

async def main(limit):
    client = AsyncClient()
    handle = os.getenv('BSKY_HANDLE')
    password = os.getenv('BSKY_APP_PASSWORD')
    profile = await client.login(handle, password)
    print('Welcome,', profile.display_name)

    print('Home (Following):\n')
    timeline = await client.get_timeline(algorithm='reverse-chronological')
    for i, feed_view in enumerate(timeline.feed):
        if i >= limit:
            break
        
        summary_lines = []
        
        # Handle repost information
        is_repost = hasattr(feed_view.reason, 'by')
        if is_repost:
            summary_lines.append(f"🔄 Reposted by @{feed_view.reason.by.handle}")
            
            # Add the original post with indentation
            if hasattr(feed_view, 'post') and hasattr(feed_view.post, 'record'):
                summary_lines.extend(format_post_content(feed_view.post, indent_level=1))
        else:
            # Format the main post content without indentation
            summary_lines.extend(format_post_content(feed_view.post))
        
        print('\n'.join(summary_lines))
        print('-' * 80)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Process some integers.')
    parser.add_argument('--limit', type=int, default=10, help='number of entries to process')
    args = parser.parse_args()
    asyncio.run(main(args.limit))
