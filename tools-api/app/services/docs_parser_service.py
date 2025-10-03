import json
from typing import Dict, List, Optional, Union
import re
from dataclasses import dataclass
from urllib.parse import urlparse


@dataclass
class ExtractedContent:
    text: str
    urls: List[str]
    images: List[str]


class GoogleDocsParser:
    def __init__(self):
        self._text_segments: List[str] = []
        self._urls: List[str] = []
        self._images: List[str] = []
        
    def _is_valid_url(self, url: str) -> bool:
        """Check if a string is a valid URL."""
        try:
            result = urlparse(url)
            return all([result.scheme, result.netloc])
        except ValueError:
            return False
            
    def _extract_urls_from_text(self, text: str) -> tuple:
        """Extract URLs from text and return cleaned text and URL list."""
        url_pattern = r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+'
        found_urls = re.findall(url_pattern, text)
        
        clean_text = text
        for url in found_urls:
            clean_text = clean_text.replace(url, ' ')
        
        clean_text = ' '.join(clean_text.split())
        return clean_text, [url for url in found_urls if self._is_valid_url(url)]

    def _process_text_run(self, text_run: Dict) -> None:
        """Process a text run element from the Google Docs JSON."""
        if 'content' not in text_run:
            return
            
        content = text_run['content']
        if content.strip():
            clean_text, urls = self._extract_urls_from_text(content)
            if clean_text:
                self._text_segments.append(clean_text)
            self._urls.extend(urls)

    def _process_inline_object(self, element: Dict) -> None:
        """Process an inline object (like images) from the Google Docs JSON."""
        if 'inlineObjectElement' in element:
            inline_obj = element['inlineObjectElement']
            if 'imageProperties' in inline_obj:
                source_uri = inline_obj['imageProperties'].get('sourceUri')
                if source_uri and self._is_valid_url(source_uri):
                    self._images.append(source_uri)

    def _process_paragraph(self, paragraph: Dict) -> None:
        """Process a paragraph element from the Google Docs JSON."""
        if 'elements' not in paragraph:
            return
            
        for element in paragraph['elements']:
            if 'textRun' in element:
                self._process_text_run(element['textRun'])
            elif 'inlineObjectElement' in element:
                self._process_inline_object(element)

    def _process_table(self, table: Dict) -> None:
        """Process a table element from the Google Docs JSON."""
        if 'tableRows' not in table:
            return
            
        for row in table['tableRows']:
            if 'tableCells' in row:
                for cell in row['tableCells']:
                    if 'content' in cell:
                        for content_item in cell['content']:
                            if 'paragraph' in content_item:
                                self._process_paragraph(content_item['paragraph'])

    def _process_content(self, content: List[Dict]) -> None:
        """Process the main content array from the Google Docs JSON."""
        for item in content:
            if 'paragraph' in item:
                self._process_paragraph(item['paragraph'])
            elif 'table' in item:
                self._process_table(item['table'])

    def parse_docs_json(self, docs_json: Union[str, List, Dict]) -> ExtractedContent:
        """Parse Google Docs JSON and return structured content."""
        # Reset state
        self._text_segments = []
        self._urls = []
        self._images = []
        
        # Parse JSON if string
        if isinstance(docs_json, str):
            try:
                docs_data = json.loads(docs_json)
            except json.JSONDecodeError:
                raise ValueError("Invalid JSON string")
        else:
            docs_data = docs_json

        # The input is directly an array of content objects
        if isinstance(docs_data, list):
            self._process_content(docs_data)
        # Handle case where there's a body wrapper
        elif isinstance(docs_data, dict):
            if 'body' in docs_data and 'content' in docs_data['body']:
                self._process_content(docs_data['body']['content'])
            elif 'content' in docs_data:
                self._process_content(docs_data['content'])
        
        # Join text segments with appropriate spacing
        full_text = ' '.join(self._text_segments)
        
        # Remove duplicate URLs and images while preserving order
        unique_urls = list(dict.fromkeys(self._urls))
        unique_images = list(dict.fromkeys(self._images))
        
        return ExtractedContent(
            text=full_text.strip(),
            urls=unique_urls,
            images=unique_images
        )


def parse_google_docs_file(file_path: str) -> Dict:
    """Parse a Google Docs JSON file and return structured content."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            
        parser = GoogleDocsParser()
        result = parser.parse_docs_json(content)
        
        return {
            "text": result.text,
            "urls": result.urls,
            "images": result.images
        }
    except Exception as e:
        return {
            "error": f"Failed to parse file: {str(e)}",
            "text": "",
            "urls": [],
            "images": []
        }


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        file_path = sys.argv[1]
        result = parse_google_docs_file(file_path)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("Please provide a file path as an argument")