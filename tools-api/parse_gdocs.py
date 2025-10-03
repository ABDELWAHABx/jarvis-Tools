#!/usr/bin/env python3
import sys
import json
from app.services.docs_parser_service import parse_google_docs_file

def main():
    if len(sys.argv) != 2:
        print("Usage: python parse_gdocs.py <file_path>")
        sys.exit(1)
        
    file_path = sys.argv[1]
    result = parse_google_docs_file(file_path)
    
    # Pretty print the result
    print(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()