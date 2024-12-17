import curses
import asyncio
import time
import textwrap
from timeline import Timeline
from typing import List, Set
import json

class TimelineUI:
    def __init__(self, timeline: Timeline):
        self.timeline = timeline
        self.current_pos = 0
        self.expanded_posts: Set[int] = set()
        self.top_line = 0
        self.screen = None
        self.max_y = 0
        self.max_x = 0

    def write_wrapped_line(self, y: int, x: int, text: str, attr=curses.A_NORMAL) -> int:
        """Write a wrapped line to the screen and return number of lines used"""
        lines_used = 0
        wrapped_lines = textwrap.wrap(text, width=self.max_x - x)
        for wrapped_line in wrapped_lines:
            if y + lines_used < self.max_y:
                try:
                    self.screen.addstr(y + lines_used, x, wrapped_line, attr)
                except curses.error:
                    pass  # Handle edge case when writing to bottom-right corner
                lines_used += 1
        return lines_used

    def draw_post(self, y: int, post_idx: int) -> int:
        """Draw a single post and return number of lines used"""
        if post_idx >= len(self.timeline.timeline):
            return 0

        feed_view = self.timeline.timeline[post_idx]
        lines_used = 0
        
        # Highlight current selection
        is_selected = post_idx == self.current_pos
        attr = curses.A_REVERSE if is_selected else curses.A_NORMAL
        
        # Basic post info
        post_line = self.timeline.format_minimal_post(feed_view, post_idx + 1)
        lines_used += self.write_wrapped_line(y + lines_used, 0, post_line, attr)

        # If expanded, show details
        if post_idx in self.expanded_posts:
            # detailed_lines = self.timeline.format_detailed_post(feed_view)
            # for line in detailed_lines:
            #     lines_used += self.write_wrapped_line(y + lines_used, 4, line, curses.A_DIM)
            
            #post_json = feed_view.post.model_dump_json()
            #lines_used += self.write_wrapped_line(y + lines_used, 4, post_json, curses.A_DIM)
            
            post = feed_view.post.record
            if post.reply:
                post = post.reply
                if post.root:
                    lines_used += self.write_wrapped_line(y + lines_used, 4, f"Reply to: {post.root.uri}", curses.A_DIM)
            callables = []
            lists = []
            attributes = []
            for attr in dir(post):
                if not attr.startswith('_'):
                    value = getattr(post, attr)
                    if callable(value):
                        callables.append(f"{value.__name__}()")
                    elif isinstance(value, (list, dict)):
                        lists.append(f"{attr}[{len(value)}]")
                    else:
                        if isinstance(value, str):
                            attributes.append(f"{attr}:{value[:5]}")
                        else:
                            attributes.append(f"{attr}<{type(value).__name__}>")
            
            lines_used += self.write_wrapped_line(y + lines_used, 4, f"Attributes: {', '.join(attributes)}", curses.A_DIM)
            lines_used += self.write_wrapped_line(y + lines_used, 4, f"Callables: {', '.join(callables)}", curses.A_DIM)
            lines_used += self.write_wrapped_line(y + lines_used, 4, f"Lists: {', '.join(lists)}", curses.A_DIM)
        return lines_used

    def draw_screen(self):
        """Draw the entire screen"""
        self.screen.clear()
        
        title = "Timeline Navigator (↑↓/j/k: Navigate, Enter/Space: Expand/Collapse, q: Quit)"
        try:
            self.screen.addstr(0, 0, title[:self.max_x], curses.A_BOLD)
        except curses.error:
            pass
        
        # Draw posts
        current_y = 1
        visible_posts = 0
        post_idx = self.top_line

        while current_y < self.max_y and post_idx < len(self.timeline.timeline):
            lines_used = self.draw_post(current_y, post_idx)
            current_y += lines_used
            visible_posts += 1
            post_idx += 1

        self.screen.refresh()

    def handle_input(self, key: int):
        """Handle keyboard input"""
        # Support both arrow keys and vim-style navigation
        if key in [curses.KEY_UP, ord('k')] and self.current_pos > 0:
            self.current_pos -= 1
            # Scroll up if necessary
            if self.current_pos < self.top_line:
                self.top_line = self.current_pos
        
        elif key in [curses.KEY_DOWN, ord('j')] and self.current_pos < len(self.timeline.timeline) - 1:
            self.current_pos += 1
            # Calculate if we need to scroll down
            current_y = 1
            for i in range(self.top_line, self.current_pos + 1):
                if i in self.expanded_posts:
                    current_y += len(self.timeline.format_detailed_post(self.timeline.timeline[i]))
                else:
                    current_y += 1
                if current_y >= self.max_y:
                    self.top_line += 1
                    break
        
        elif key in [ord('\n'), ord(' '), curses.KEY_RIGHT]:
            if self.current_pos in self.expanded_posts:
                self.expanded_posts.remove(self.current_pos)
            else:
                self.expanded_posts.add(self.current_pos)

    def setup_screen(self, stdscr):
        """Setup the curses screen with proper configurations"""
        # Basic curses setup
        curses.start_color()
        curses.use_default_colors()
        curses.init_pair(1, curses.COLOR_CYAN, -1)
        curses.init_pair(2, curses.COLOR_GREEN, -1)
        curses.curs_set(0)        
        stdscr.keypad(True)
        curses.noecho()
        curses.cbreak()
        
        stdscr.nodelay(1)
        
        return stdscr

    async def run(self, stdscr):
        """Main UI loop"""
        self.screen = self.setup_screen(stdscr)
        
        while True:
            self.max_y, self.max_x = self.screen.getmaxyx()
            self.draw_screen()
            
            try:
                key = self.screen.getch()
            except curses.error:
                key = None

            if key == ord('q'):
                break
                
            self.handle_input(key)
            
            time.sleep(0.05)  # Add a small delay to avoid high CPU usage

async def main():
    # Initialize timeline
    timeline = Timeline()
    await timeline.initialize()
    
    # Start the UI
    ui = TimelineUI(timeline)
    await curses.wrapper(ui.run)

if __name__ == "__main__":
    asyncio.run(main())