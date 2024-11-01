from flask import Flask, jsonify, request
from GoogleNews import GoogleNews
from flask_caching import Cache
import os

app = Flask(__name__)
cache = Cache(app, config={'CACHE_TYPE': 'simple'})

def fetch_news(query, start=0, count=3):
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

@app.route('/news', methods=['GET'])
@cache.cached(timeout=300, query_string=True)
def get_news():
    query = request.args.get('query')
    start = int(request.args.get('start', 2))
    count = int(request.args.get('count', 10))
    
    if not query:
        return jsonify({"error": "Query not provided"}), 400

    news_batch = fetch_news(query, start=start, count=count)
    return jsonify(news_batch)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))

