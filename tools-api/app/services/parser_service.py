from bs4 import BeautifulSoup, Tag
import markdown
import asyncio
from typing import List, Dict, Any, Optional, Tuple
import re
import colorsys


class RichTextParser:
    def __init__(self):
        self.current_index = 1  # Start at 1 (Google Docs typically has newline at 0)
        self.requests: List[Dict[str, Any]] = []

    def _parse_color(self, color: str) -> Optional[Dict[str, Any]]:
        """Convert CSS color to Google Docs color format."""
        try:
            # Handle named colors - expanded list
            NAMED_COLORS = {
                "red": {"color": {"rgbColor": {"red": 1, "green": 0, "blue": 0}}},
                "blue": {"color": {"rgbColor": {"red": 0, "green": 0, "blue": 1}}},
                "green": {"color": {"rgbColor": {"red": 0, "green": 0.5, "blue": 0}}},
                "yellow": {"color": {"rgbColor": {"red": 1, "green": 1, "blue": 0}}},
                "orange": {"color": {"rgbColor": {"red": 1, "green": 0.647, "blue": 0}}},
                "purple": {"color": {"rgbColor": {"red": 0.5, "green": 0, "blue": 0.5}}},
                "pink": {"color": {"rgbColor": {"red": 1, "green": 0.753, "blue": 0.796}}},
                "black": {"color": {"rgbColor": {"red": 0, "green": 0, "blue": 0}}},
                "white": {"color": {"rgbColor": {"red": 1, "green": 1, "blue": 1}}},
                "gray": {"color": {"rgbColor": {"red": 0.5, "green": 0.5, "blue": 0.5}}},
                "grey": {"color": {"rgbColor": {"red": 0.5, "green": 0.5, "blue": 0.5}}},
            }
            if color.lower() in NAMED_COLORS:
                return NAMED_COLORS[color.lower()]

            # Handle hex colors
            if color.startswith("#"):
                color = color.lstrip("#")
                if len(color) == 3:
                    color = "".join(c + c for c in color)
                r, g, b = [int(color[i:i+2], 16) / 255 for i in (0, 2, 4)]
                return {
                    "color": {
                        "rgbColor": {
                            "red": r,
                            "green": g,
                            "blue": b
                        }
                    }
                }

            # Handle rgb/rgba
            rgb_match = re.match(r'rgba?\((\d+),\s*(\d+),\s*(\d+)(?:,\s*[\d.]+)?\)', color)
            if rgb_match:
                r, g, b = [int(x) / 255 for x in rgb_match.groups()]
                return {
                    "color": {
                        "rgbColor": {
                            "red": r,
                            "green": g,
                            "blue": b
                        }
                    }
                }
        except Exception:
            pass
        return None

    def _get_text_style(self, el: Tag, parent_style: Dict[str, Any] = None) -> Dict[str, Any]:
        """Extract text style information from HTML element."""
        style: Dict[str, Any] = {}
        
        # Start with parent style
        if parent_style:
            style.update(parent_style)
        
        # Bold - check tag name and inline style
        if el.name in ['b', 'strong']:
            style["bold"] = True
        elif 'font-weight' in el.get('style', ''):
            weight_match = re.search(r'font-weight:\s*(\w+|\d+)', el.get('style', ''))
            if weight_match:
                weight = weight_match.group(1)
                if weight in ['bold', 'bolder', '700', '800', '900']:
                    style["bold"] = True
        
        # Italic
        if el.name in ['i', 'em']:
            style["italic"] = True
        elif 'font-style' in el.get('style', ''):
            if 'italic' in el.get('style', ''):
                style["italic"] = True
        
        # Underline
        if el.name == 'u':
            style["underline"] = True
        elif 'text-decoration' in el.get('style', ''):
            if 'underline' in el.get('style', ''):
                style["underline"] = True
        
        # Strikethrough
        if el.name in ['s', 'strike', 'del']:
            style["strikethrough"] = True
        elif 'text-decoration' in el.get('style', ''):
            if 'line-through' in el.get('style', ''):
                style["strikethrough"] = True
        
        # Subscript and Superscript
        if el.name == 'sub':
            style["baselineOffset"] = "SUBSCRIPT"
        elif el.name == 'sup':
            style["baselineOffset"] = "SUPERSCRIPT"
        
        # Code/monospace
        if el.name in ['code', 'pre', 'tt', 'kbd', 'samp']:
            style["weightedFontFamily"] = {"fontFamily": "Courier New"}
        
        # Font family from style
        if 'font-family' in el.get('style', ''):
            font = re.search(r'font-family:\s*([^;]+)', el.get('style', ''))
            if font:
                font_name = font.group(1).strip().strip('"\'').split(',')[0]
                style["weightedFontFamily"] = {"fontFamily": font_name}
        
        # Font size
        if 'font-size' in el.get('style', ''):
            # Try to extract pt size
            size_pt = re.search(r'font-size:\s*(\d+(?:\.\d+)?)pt', el.get('style', ''))
            if size_pt:
                style["fontSize"] = {"magnitude": float(size_pt.group(1)), "unit": "PT"}
            else:
                # Try px size (convert to pt: 1pt = 1.333px)
                size_px = re.search(r'font-size:\s*(\d+(?:\.\d+)?)px', el.get('style', ''))
                if size_px:
                    pt_size = float(size_px.group(1)) * 0.75
                    style["fontSize"] = {"magnitude": pt_size, "unit": "PT"}
        
        # Handle heading tags with default sizes
        if el.name in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
            # Google Docs heading sizes (approximate)
            heading_sizes = {
                'h1': 20,
                'h2': 16,
                'h3': 14,
                'h4': 12,
                'h5': 11,
                'h6': 11
            }
            if "fontSize" not in style:
                style["fontSize"] = {"magnitude": heading_sizes[el.name], "unit": "PT"}
            style["bold"] = True
        
        # Color (foreground)
        color = None
        if 'color' in el.get('style', ''):
            color_match = re.search(r'color:\s*([^;]+)', el.get('style', ''))
            if color_match:
                color = self._parse_color(color_match.group(1).strip())
        elif el.get('color'):
            color = self._parse_color(el.get('color'))
            
        if color:
            style["foregroundColor"] = color

        # Background color
        bg_color = None
        if 'background-color' in el.get('style', ''):
            bg_match = re.search(r'background-color:\s*([^;]+)', el.get('style', ''))
            if bg_match:
                bg_color = self._parse_color(bg_match.group(1).strip())
        elif el.get('bgcolor'):
            bg_color = self._parse_color(el.get('bgcolor'))
            
        if bg_color:
            style["backgroundColor"] = bg_color
        
        # Handle <mark> tag for highlighting
        if el.name == 'mark':
            if "backgroundColor" not in style:
                style["backgroundColor"] = self._parse_color("#ffff00")  # Yellow highlight

        return style

    def _process_text_with_style(self, text: str, style: Dict[str, Any], is_block_end: bool = False):
        """Add text with its style to requests."""
        if not text and not is_block_end:
            return

        # Don't strip text - preserve spacing for inline formatting
        text_to_insert = text + ("\n" if is_block_end else "")
        if not text_to_insert:
            text_to_insert = "\n"

        text_request = {
            "insertText": {
                "location": {"index": self.current_index},
                "text": text_to_insert
            }
        }
        self.requests.append(text_request)

        # Apply style to the actual text content (excluding newline)
        if style and len(text) > 0:
            style_request = {
                "updateTextStyle": {
                    "range": {
                        "startIndex": self.current_index,
                        "endIndex": self.current_index + len(text)
                    },
                    "textStyle": style,
                    "fields": ",".join(style.keys())
                }
            }
            self.requests.append(style_request)

        self.current_index += len(text_to_insert)

    def _process_element(self, el: Tag, parent_style: Dict[str, Any] = None):
        """Process an HTML element and its children recursively."""
        if not isinstance(el, Tag):
            # Text node - preserve spaces but don't strip leading/trailing within inline context
            text = str(el)
            # Only strip if this text is standalone (not between inline elements)
            if text.strip():
                self._process_text_with_style(text, parent_style or {})
            return

        # Get current element's style merged with parent
        current_style = self._get_text_style(el, parent_style)

        # Handle block elements
        if el.name in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
            level = int(el.name[1])
            # Process children with heading style
            start_index = self.current_index
            for child in el.children:
                self._process_element(child, current_style)
            
            # Add newline if not already there
            if not self.requests or not self.requests[-1].get('insertText', {}).get('text', '').endswith('\n'):
                self._process_text_with_style("", {}, is_block_end=True)
            
            # Apply paragraph style
            self.requests.append({
                "updateParagraphStyle": {
                    "range": {
                        "startIndex": start_index,
                        "endIndex": self.current_index
                    },
                    "paragraphStyle": {"namedStyleType": f"HEADING_{level}"},
                    "fields": "namedStyleType"
                }
            })
            return

        if el.name == 'p':
            for child in el.children:
                self._process_element(child, current_style)
            self._process_text_with_style("", {}, is_block_end=True)
            return

        if el.name == 'br':
            self._process_text_with_style("", {}, is_block_end=True)
            return

        if el.name == 'hr':
            # Insert a horizontal line using a special character
            self._process_text_with_style("___", current_style, is_block_end=True)
            return

        if el.name in ['ul', 'ol']:
            list_items = el.find_all('li', recursive=False)
            list_start_index = self.current_index
            for item in list_items:
                for child in item.children:
                    self._process_element(child, current_style)
                self._process_text_with_style("", {}, is_block_end=True)
            
            if list_items:
                self.requests.append({
                    "createParagraphBullets": {
                        "range": {
                            "startIndex": list_start_index,
                            "endIndex": self.current_index
                        },
                        "bulletPreset": "NUMBERED_DECIMAL_ALPHA_ROMAN" if el.name == "ol" else "BULLET_DISC_CIRCLE_SQUARE"
                    }
                })
            return

        # Handle blockquote
        if el.name == 'blockquote':
            for child in el.children:
                self._process_element(child, current_style)
            if not self.requests or not self.requests[-1].get('insertText', {}).get('text', '').endswith('\n'):
                self._process_text_with_style("", {}, is_block_end=True)
            return

        # Handle div and span as style containers
        if el.name in ['div', 'span', 'section', 'article']:
            for child in el.children:
                self._process_element(child, current_style)
            # Only add newline for block-level divs
            if el.name in ['div', 'section', 'article']:
                if el.get_text(strip=True) and not self.requests[-1].get('insertText', {}).get('text', '').endswith('\n'):
                    self._process_text_with_style("", {}, is_block_end=True)
            return

        # Handle anchor tags
        if el.name == 'a':
            href = el.get('href', '')
            start_index = self.current_index
            for child in el.children:
                self._process_element(child, current_style)
            
            # Apply link styling if there's a valid href
            if href and self.current_index > start_index:
                link_style = current_style.copy()
                link_style["link"] = {"url": href}
                link_style["underline"] = True
                link_style["foregroundColor"] = self._parse_color("#0563C1")  # Standard link blue
                
                self.requests.append({
                    "updateTextStyle": {
                        "range": {
                            "startIndex": start_index,
                            "endIndex": self.current_index
                        },
                        "textStyle": link_style,
                        "fields": ",".join(link_style.keys())
                    }
                })
            return
        
        # Handle images
        if el.name == 'img':
            src = el.get('src', '')
            alt = el.get('alt', '')
            
            if src:
                # Get image dimensions if specified
                width = el.get('width')
                height = el.get('height')
                
                image_request = {
                    "insertInlineImage": {
                        "uri": src,
                        "location": {"index": self.current_index}
                    }
                }
                
                # Add size if specified
                if width or height:
                    object_size = {}
                    if width:
                        try:
                            width_val = float(re.sub(r'[^\d.]', '', str(width)))
                            object_size["width"] = {"magnitude": width_val, "unit": "PT"}
                        except ValueError:
                            pass
                    if height:
                        try:
                            height_val = float(re.sub(r'[^\d.]', '', str(height)))
                            object_size["height"] = {"magnitude": height_val, "unit": "PT"}
                        except ValueError:
                            pass
                    
                    if object_size:
                        image_request["insertInlineImage"]["objectSize"] = object_size
                
                self.requests.append(image_request)
                self.current_index += 1  # Images take up one character position
            return

        # Handle table
        if el.name == 'table':
            rows = el.find_all('tr', recursive=False)
            if not rows:
                tbody = el.find('tbody')
                if tbody:
                    rows = tbody.find_all('tr', recursive=False)
            
            if rows:
                cols = max(len(row.find_all(['td', 'th'], recursive=False)) for row in rows)
                if cols > 0:
                    table_start_index = self.current_index
                    self._process_text_with_style("", {}, is_block_end=True)
                    
                    self.requests.append({
                        "insertTable": {
                            "rows": len(rows),
                            "columns": cols,
                            "location": {"index": table_start_index}
                        }
                    })
                    
                    # Note: Proper cell content insertion requires calculating exact cell indices
                    # which is complex due to Google Docs table structure
                    # This is a simplified version
                    self.current_index = table_start_index + 1
            return

        # Default: process children with current style
        for child in el.children:
            self._process_element(child, current_style)

    def parse_html(self, html: str) -> List[Dict[str, Any]]:
        """Parse HTML into Google Docs API requests with rich text formatting."""
        self.current_index = 1
        self.requests = []
        
        soup = BeautifulSoup(html, "html.parser")
        
        # Process body content if exists, otherwise process all top-level elements
        body = soup.find('body')
        if body:
            for el in body.children:
                if isinstance(el, Tag):
                    self._process_element(el)
        else:
            for el in soup.children:
                if isinstance(el, Tag):
                    self._process_element(el)
            
        return self.requests


def parse_html_to_docs_sync(html: str) -> List[Dict[str, Any]]:
    """Convert HTML to Google Docs API requests, preserving rich text formatting."""
    parser = RichTextParser()
    return parser.parse_html(html or "")


def parse_markdown_to_docs_sync(md: str) -> List[Dict[str, Any]]:
    """Convert Markdown to HTML, then to Google Docs API requests."""
    html = markdown.markdown(md or "", extensions=['extra', 'nl2br', 'sane_lists'])
    return parse_html_to_docs_sync(html)


# Keep async versions for compatibility
async def parse_html(html: str):
    """Async wrapper for HTML parsing (simplified version for compatibility)."""
    await asyncio.sleep(0)
    return parse_html_to_docs_sync(html)


async def parse_markdown(md: str):
    """Async wrapper for Markdown parsing (simplified version for compatibility)."""
    await asyncio.sleep(0)
    return parse_markdown_to_docs_sync(md)