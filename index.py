from flask import Flask, jsonify, request
from GoogleNews import GoogleNews
from flask_caching import Cache
import os
import threading
from functools import wraps
import time
from concurrent.futures import ThreadPoolExecutor
import logging
from collections import OrderedDict

app = Flask(__name__)

# Configuração de cache mais agressiva
cache = Cache(app, config={
    'CACHE_TYPE': 'simple',
    'CACHE_DEFAULT_TIMEOUT': 600,  # 10 minutos
    'CACHE_THRESHOLD': 500  # Aumentado para guardar mais itens
})

class LRUCache:
    """Cache local para queries mais frequentes"""
    def __init__(self, capacity):
        self.cache = OrderedDict()
        self.capacity = capacity

    def get(self, key):
        if key not in self.cache:
            return None
        self.cache.move_to_end(key)
        return self.cache[key]

    def put(self, key, value):
        if key in self.cache:
            self.cache.move_to_end(key)
        self.cache[key] = value
        if len(self.cache) > self.capacity:
            self.cache.popitem(last=False)

class NewsManager:
    def __init__(self):
        self.googlenews = GoogleNews(lang='pt', region='BR')
        self.last_request = {}
        self.lock = threading.Lock()
        self.local_cache = LRUCache(100)  # Cache para 100 queries mais recentes
        self.executor = ThreadPoolExecutor(max_workers=4)
        self.popular_queries = set()  # Conjunto para rastrear queries populares
        self.query_count = {}  # Contador de frequência de queries
        
    def _fetch_and_cache(self, query, force=False):
        """Busca notícias e armazena em cache"""
        current_time = time.time()
        
        # Se não for forçado, verifica o rate limit
        if not force:
            last_time = self.last_request.get(query, 0)
            if current_time - last_time < 2:
                time.sleep(2)
        
        self.last_request[query] = current_time
        
        try:
            self.googlenews.search(query)
            results = self.googlenews.results()
            
            news_list = []
            for item in results[:20]:  # Cache mais resultados
                news_url = item.get('link', '')
                if not news_url:
                    continue
                
                news_list.append({
                    "title": item.get('title', 'Título indisponível'),
                    "summary": item.get('desc', 'Resumo indisponível'),
                    "url": news_url,
                    "date": item.get('date', 'Data não disponível')
                })
            
            # Armazena no cache local e no cache do Flask
            self.local_cache.put(query, news_list)
            cache.set(f"news:{query}", news_list)
            
            return news_list
        finally:
            self.googlenews.clear()
    
    def update_popular_queries(self, query):
        """Atualiza contagem de queries populares"""
        self.query_count[query] = self.query_count.get(query, 0) + 1
        if self.query_count[query] >= 3:  # Se query foi usada 3 ou mais vezes
            self.popular_queries.add(query)
            # Agenda atualização em background
            self.executor.submit(self._fetch_and_cache, query, force=True)
    
    def get_news(self, query, start=0, count=3):
        """Obtém notícias com múltiplas camadas de cache"""
        # Primeiro tenta o cache local (mais rápido)
        cached_news = self.local_cache.get(query)
        if cached_news:
            return cached_news[start:start + count]
        
        # Depois tenta o cache do Flask
        flask_cached = cache.get(f"news:{query}")
        if flask_cached:
            self.local_cache.put(query, flask_cached)  # Atualiza cache local
            return flask_cached[start:start + count]
        
        # Se não encontrou em cache, busca novo
        with self.lock:
            news_list = self._fetch_and_cache(query)
            
        # Atualiza estatísticas de uso
        self.update_popular_queries(query)
        
        return news_list[start:start + count]
    
    def start_background_updates(self):
        """Inicia thread para atualização periódica de queries populares"""
        def update_popular():
            while True:
                try:
                    for query in list(self.popular_queries):
                        self._fetch_and_cache(query, force=True)
                except Exception as e:
                    logging.error(f"Error updating popular queries: {e}")
                time.sleep(300)  # Atualiza a cada 5 minutos
        
        threading.Thread(target=update_popular, daemon=True).start()

news_manager = NewsManager()
news_manager.start_background_updates()

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
    
    try:
        news_batch = news_manager.get_news(query, start=start, count=count)
        if news_batch:
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
