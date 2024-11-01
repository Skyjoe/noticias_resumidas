from flask import Flask, jsonify, request
from GoogleNews import GoogleNews
from flask_caching import Cache
import os
import threading
from functools import wraps
import time

app = Flask(__name__)

# Configuração de cache otimizada para o Render
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
    
    def get_news(self, query, start=0, count=3):
        """
        Obtém notícias com controle de taxa de requisições
        """
        with self.lock:
            current_time = time.time()
            last_time = self.last_request.get(query, 0)
            
            # Espera mínima entre requisições para mesma query
            if current_time - last_time < 2:
                time.sleep(2)
            
            self.last_request[query] = current_time
            self.googlenews.search(query)
            results = self.googlenews.results()
            self.googlenews.clear()  # Limpa resultados para liberar memória
            
            # Processa apenas a quantidade solicitada
            results = results[start:start + count]
            
            news_list = []
            for item in results:
                news_url = item.get('link', '')
                if not news_url:
                    continue
                
                # Usa o formato original de data que funcionava
                date = item.get('date', 'Data não disponível')
                
                news_list.append({
                    "title": item.get('title', 'Título indisponível'),
                    "summary": item.get('desc', 'Resumo indisponível'),
                    "url": news_url,
                    "date": date
                })
            
            return news_list

# Instância global do gerenciador de notícias
news_manager = NewsManager()

def rate_limit(f):
    """Decorator para limitar taxa de requisições por IP"""
    requests = {}
    @wraps(f)
    def decorated(*args, **kwargs):
        ip = request.remote_addr
        current_time = time.time()
        
        # Limpa requisições antigas
        requests[ip] = [t for t in requests.get(ip, []) if current_time - t < 60]
        
        # Verifica limite de requisições (30 por minuto)
        if len(requests.get(ip, [])) >= 30:
            return jsonify({"error": "Too many requests. Please try again later."}), 429
        
        # Registra nova requisição
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
    
    # Limita quantidade máxima de resultados
    count = min(count, 20)
    
    # Tenta obter do cache
    cache_key = f"news:{query}:{start}:{count}"
    cached_result = cache.get(cache_key)
    if cached_result:
        return jsonify(cached_result)
    
    try:
        news_batch = news_manager.get_news(query, start=start, count=count)
        if news_batch:
            # Armazena no cache
            cache.set(cache_key, news_batch)
            return jsonify(news_batch)
        return jsonify({"error": "No news found"}), 404
    except Exception as e:
        return jsonify({"error": "Failed to fetch news. Please try again later."}), 500

@app.route('/health', methods=['GET'])
def health_check():
    """Endpoint para verificação de saúde do servidor"""
    return jsonify({"status": "healthy"}), 200

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
