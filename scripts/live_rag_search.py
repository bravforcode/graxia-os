import sys
import json
import urllib.request
import urllib.parse
from bs4 import BeautifulSoup

def search_duckduckgo(query, num_results=3):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    encoded_query = urllib.parse.quote_plus(query)
    url = f"https://html.duckduckgo.com/html/?q={encoded_query}"
    
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req) as response:
            html = response.read()
            soup = BeautifulSoup(html, 'html.parser')
            
            results = []
            for a in soup.find_all('a', class_='result__url', href=True):
                if len(results) >= num_results:
                    break
                link = a['href']
                if link.startswith('//duckduckgo.com/l/?'):
                    # Extract the actual URL from the redirect
                    parsed = urllib.parse.urlparse(link)
                    qs = urllib.parse.parse_qs(parsed.query)
                    if 'uddg' in qs:
                        link = qs['uddg'][0]
                results.append(link)
            return results
    except Exception as e:
        print(f"Search Error: {e}", file=sys.stderr)
        return []

def extract_text(url):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'
    }
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=5) as response:
            html = response.read()
            soup = BeautifulSoup(html, 'html.parser')
            # Kill javascript and css
            for script in soup(["script", "style"]):
                script.extract()
            text = soup.get_text(separator=' ')
            # Collapse whitespace
            lines = (line.strip() for line in text.splitlines())
            chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
            text = '\n'.join(chunk for chunk in chunks if chunk)
            return text[:3000] # Return top 3000 chars to save tokens
    except Exception as e:
        return f"Error extracting {url}: {e}"

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python live_rag_search.py '<query>'")
        sys.exit(1)
        
    query = " ".join(sys.argv[1:])
    print(f"--- PERPLEXITY LIVE SEARCH: '{query}' ---")
    urls = search_duckduckgo(query)
    
    if not urls:
        print("No results found or rate limited. Try a more specific query.")
        sys.exit(0)
        
    for i, url in enumerate(urls):
        print(f"\n[{i+1}] SOURCE: {url}")
        print("-" * 50)
        print(extract_text(url))
        print("-" * 50)
