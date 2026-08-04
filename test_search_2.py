import urllib.request, urllib.parse, json

query = 'hari webinars'
q = urllib.parse.quote(query)
req = urllib.request.Request(f'https://systechusa.com/wp-json/wp/v2/search?search={q}', headers={'User-Agent': 'Mozilla/5.0'})
try:
    data = json.loads(urllib.request.urlopen(req, timeout=10).read().decode('utf-8'))
    print('Search Results for hari webinars:')
    for item in data[:5]:
        print(f"Title: {item.get('title')}, URL: {item.get('url')}")
except Exception as e:
    print('Error:', e)
