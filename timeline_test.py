from timeline import Timeline
import asyncio

async def main():
    try:
        timeline = Timeline()
        await timeline.initialize()
        
        # Get minimal posts on page 1
        minimal_posts = timeline.get_minimal_posts(page=1)
        print("=== Minimal Posts ===")
        print(minimal_posts)
        print("\n=== Detailed Post ===")
        
        # Get detailed info for post number 1
        detailed_post = timeline.get_post_detail(post_number=1)
        print(detailed_post)
    except Exception as e:
        print(f"Error occurred: {str(e)}")

if __name__ == '__main__':
    asyncio.run(main())