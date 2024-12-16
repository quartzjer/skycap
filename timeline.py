import os
from dotenv import load_dotenv
from atproto import AsyncClient
from datetime import datetime
import humanize

load_dotenv()

class Timeline:
    def __init__(self):
        self.client = AsyncClient()
        self.handle = os.getenv('BSKY_HANDLE')
        self.password = os.getenv('BSKY_APP_PASSWORD')
        self.profile = None
        self.timeline = []
        self.post_index = {}  # Maps numbered IDs to atproto post IDs
        self.page_size = 10   # Number of posts per page
        self.initialized = False

    async def initialize(self):
        """Initialize the client and fetch the timeline."""
        try:
            self.profile = await self.client.login(self.handle, self.password)
            await self.fetch_timeline()
            self.initialized = True
        except Exception as e:
            print(f"Failed to initialize timeline: {str(e)}")
            raise

    async def fetch_timeline(self):
        """Fetch the home timeline and build the post index."""
        try:
            timeline_data = await self.client.get_timeline(algorithm='reverse-chronological')
            self.timeline = timeline_data.feed
            self.build_post_index()
        except Exception as e:
            print(f"Failed to fetch timeline: {str(e)}")
            raise

    def build_post_index(self):
        """Build an index mapping numbered IDs to atproto post IDs."""
        for idx, feed_view in enumerate(self.timeline):
            self.post_index[idx + 1] = {
                'cid': feed_view.post.cid,
                'uri': feed_view.post.uri
            }

    def find_feed_view(self, post_number):
        """Find a feed view by post number."""
        post_info = self.post_index.get(post_number)
        if not post_info:
            return None
        return next(
            (fv for fv in self.timeline if fv.post.cid == post_info['cid']),
            None
        )

    def get_post_detail(self, post_number):
        """Return rich details about a single post."""
        if not self.initialized:
            raise Exception("Timeline not initialized. Call 'initialize()' first.")

        feed_view = self.find_feed_view(post_number)
        if not feed_view:
            return f"No post found with number {post_number}."

        detailed_info = self.format_detailed_post(feed_view)
        return "\n".join(detailed_info)

    def get_minimal_posts(self, page):
        """Return minimal information on posts for a given page."""
        if not self.initialized:
            raise Exception("Timeline not initialized. Call 'initialize()' first.")

        start = (page - 1) * self.page_size
        end = start + self.page_size
        posts = self.timeline[start:end]
        minimal_info = []

        for idx, feed_view in enumerate(posts, start=start):
            post_number = idx + 1
            summary = self.format_minimal_post(feed_view, post_number)
            minimal_info.append(summary)

        return "\n".join(minimal_info)

    def format_minimal_post(self, feed_view, post_number):
        """Format minimal information for a single post."""
        author = feed_view.post.author
        record = feed_view.post.record
        text_content = (record.text or '(no text content)').replace('\n', ' ')
        created_at = datetime.fromisoformat(record.created_at.replace('Z', '+00:00'))
        created_str = humanize.naturaltime(datetime.now().astimezone() - created_at)

        summary = (
            f"{post_number}. {author.display_name} - {text_content[:50]}... • {created_str}"
        )
        return summary

    def format_detailed_post(self, feed_view):
        """Format rich details for a single post."""
        summary_lines = []

        # Handle repost information
        is_repost = hasattr(feed_view.reason, 'by')
        if is_repost:
            summary_lines.append(f"🔄 Reposted by @{feed_view.reason.by.handle}")
            summary_lines.extend(self.format_post_content(feed_view.post, indent_level=1))
        else:
            summary_lines.extend(self.format_post_content(feed_view.post))

        summary_lines.append('-' * 80)
        return summary_lines

    def format_post_content(self, post, indent_level=0):
        """Format a post's content with specified indentation."""
        indent = "    " * indent_level
        record = post.record
        author = post.author

        created_at = datetime.fromisoformat(record.created_at.replace('Z', '+00:00'))
        created_str = humanize.naturaltime(datetime.now().astimezone() - created_at)

        text_content = (record.text or '(no text content)').replace('\n', ' ')
        post_line = f"{indent}[@{author.handle}] {author.display_name} - {text_content}"

        embed_info = self.format_embed_info(post)
        if embed_info:
            post_line += f" | {embed_info}"

        post_line += (f" | 👍 {post.like_count} 🔄 {post.repost_count} 💬 {post.reply_count} "
                     f"📝 {post.quote_count} • {created_str}")

        return [post_line]

    def format_embed_info(self, post):
        """Format embed information for display."""
        if not hasattr(post, 'embed') or post.embed is None:
            return None

        embed = post.embed

        if embed.py_type == 'app.bsky.embed.images#view':
            alt_texts = self.get_post_image_alt_texts(post)
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

    def get_post_image_alt_texts(self, post):
        """Extract all image alt texts from a post."""
        if not hasattr(post, 'embed') or post.embed is None:
            return []

        if post.embed.py_type == 'app.bsky.embed.images#view':
            alt_texts = []
            for img in post.embed.images:
                if hasattr(img, 'alt') and img.alt:
                    alt_texts.append(img.alt)
            return alt_texts

        return []
