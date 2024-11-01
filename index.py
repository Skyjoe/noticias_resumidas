from flask import Flask, jsonify, request
from GoogleNews import GoogleNews
from flask_caching import Cache
import asyncio
import aiohttp
from concurrent.futures import ThreadPoolExecutor

app = Flask(__name__)
cache = Cache(app, config={'CACHE_TYPE': 'simple'})

async def fetch_news_async(query, start=0, count=3):
    googlenews = GoogleNews(lang='pt', region='BR')
    googlenews.search(query)
    results = googlenews.results()[start:start + count]
    
    news_list = []
    for item in results:
        news_url = item.get('link', '')
        if not news_url:
            continue
        
        date = item.get('date', 'Data não disponível')
        
        news_list.append({
            "title": item.get('title', 'Título indisponível'),
            "summary": item.get('desc', 'Resumo indisponível'),
            "url": news_url,
            "date": date
        })
    
    return news_list

@app.route('/initial_news', methods=['GET'])
@cache.cached(timeout=300, query_string=True)
def get_initial_news():
    query = request.args.get('query')
    
    if not query:
        return jsonify({"error": "Query not provided"}), 400

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    initial_news = loop.run_until_complete(fetch_news_async(query, start=0, count=3))
    loop.close()

    return jsonify(initial_news)

@app.route('/remaining_news', methods=['GET'])
@cache.cached(timeout=300, query_string=True)
def get_remaining_news():
    query = request.args.get('query')
    
    if not query:
        return jsonify({"error": "Query not provided"}), 400

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    remaining_news = loop.run_until_complete(fetch_news_async(query, start=3, count=12))
    loop.close()

    return jsonify(remaining_news)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
