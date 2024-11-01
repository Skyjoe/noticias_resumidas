from flask import Flask, jsonify, request
from GoogleNews import GoogleNews
from flask_caching import Cache
import os
from datetime import datetime, timedelta
import threading
from functools import wraps
import time
import dateparser
import pytz

app = Flask(__name__)

# Configuração de cache
cache = Cache(app, config={
    'CACHE_TYPE': 'simple',
    'CACHE_DEFAULT_TIMEOUT': 300,
    'CACHE_THRESHOLD': 100
})

class NewsManager:
    def __init__(self):
        self.googlenews = GoogleNews(lang='pt', region='BR')
        self.last_request = {}
        self.lock = threading.Lock()
        self.timezone = pytz.timezone('America/Sao_Paulo')
    
    def _parse_date(self, date_str):
        """
        Trata diferentes formatos de data que podem vir do GoogleNews
        """
        if not date_str:
            return 'Data não disponível'
            
        try:
            # Tenta fazer o parse da data com dateparser
            # que é mais flexível com diferentes formatos
            parsed_date = dateparser.parse(
                date_str,
                languages=['pt', 'en'],
                settings={
                    'TIMEZONE': 'America/Sao_Paulo',
                    'RETURN_AS_TIMEZONE_AWARE': True
                }
            )
            
            if parsed_date:
                # Converte para timezone do Brasil e formata
                localized_date = parsed_date.astimezone(self.timezone)
                return localized_date.strftime('%d/%m/%Y %H:%M')
            
            return 'Data não disponível'
            
        except Exception:
            return 'Data não disponível'
    
    def get_news(self, query, start=0, count=3):
        """
        Obtém notícias com controle de taxa de requisições
        """
        with self.lock:
            current_time = time.time()
            last_time = self.last_request.get(query, 0)
            
            if current_time - last_time < 2:
                time.sleep(2)
            
            self.last_request[query] = current_time
            self.googlenews.search(query)
            results = self.googlenews.results()
            self.googlenews.clear()
        
        return self._process_results(results[start:start + count])
    
    def _process_results(self, results):
        news_list = []
        for item in results:
            news_url = item.get('link', '')
            if not news_url:
                continue
            
            # Processa a data usando o novo método
            date = self._parse_date(item.get('datetime', '') or item.get('date', ''))
            
            news_list.append({
                "title": item.get('title', 'Título indisponível'),
                "summary": item.get('desc', 'Resumo indisponível'),
                "url": news_url,
                "date": date,
                "source": item.get('media', 'Fonte desconhecida')
            })
        
        return news_list

news_manager = NewsManager()

def rate_limit(f):
    requests = {}
    @wraps(f)
    def decorated(*args, **kwargs):
        ip = request.remote_addr
        current_time = time.time()
        
        requests[ip] = [t for t in requests.get(ip, []) if current_time - t < 60]
        
        if len(requests.get(ip, [])) >= 30:
            return jsonify({"error": "Too many requests. Please try again later."}), 429
        
        requests.setdefault(ip, []).append(current_time)
        return f(*args, **kwargs)
    return decorated

@app.route('/news', methods=['GET'])
@rate_limit
def get_news():
    query = request.args.get('query')
    try:
        start = int(request.args.get('start', 0))
        count = int(request.args.get('count', 10))
    except ValueError:
        return jsonify({"error": "Invalid start or count parameters"}), 400
    
    if not query:
        return jsonify({"error": "Query not provided"}), 400
    
    count = min(count, 20)
    
    cache_key = f"news:{query}:{start}:{count}"
    cached_result = cache.get(cache_key)
    if cached_result:
        return jsonify(cached_result)
    
    try:
        news_batch = news_manager.get_news(query, start=start, count=count)
        if news_batch:
            cache.set(cache_key, news_batch)
            return jsonify(news_batch)
        return jsonify({"error": "No news found"}), 404
    except Exception as e:
        return jsonify({"error": "Failed to fetch news. Please try again later."}), 500

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "healthy"}), 200

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
