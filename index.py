from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from GoogleNews import GoogleNews
import time
from typing import List, Dict, Optional
import uvicorn

app = FastAPI()

class NewsManager:
    def __init__(self):
        self.googlenews = GoogleNews(lang='pt', region='BR')
        self.last_request = {}
        self.cache = {}  # Dicionário para armazenar o cache interno

    def get_news_from_cache(self, query: str):
        # Verifica se há cache e se ainda está válido (300 segundos)
        if query in self.cache:
            cached_data, timestamp = self.cache[query]
            if time.time() - timestamp < 300:  # 5 minutos de validade
                return cached_data
        return None

    def store_news_in_cache(self, query: str, data: List[Dict]):
        # Armazena os dados no cache com o timestamp atual
        self.cache[query] = (data, time.time())

    def get_news(self, query: str, start: int = 0, count: int = 3) -> List[Dict]:
        cached_news = self.get_news_from_cache(query)
        if cached_news is not None:
            return cached_news

        # Se não houver cache válido, faz uma nova busca
        self.googlenews.search(query)
        results = self.googlenews.results()
        
        news_list = []
        for item in results[start:start + count]:
            news_url = item.get('link', '')
            if not news_url:
                continue
            
            news_list.append({
                "title": item.get('title', 'Título indisponível'),
                "summary": item.get('desc', 'Resumo indisponível'),
                "url": news_url,
                "date": item.get('date', 'Data não disponível')
            })

        # Armazena os resultados no cache
        self.store_news_in_cache(query, news_list)
        return news_list

news_manager = NewsManager()

@app.get("/news")
async def get_news(query: str, start: Optional[int] = 0, count: Optional[int] = 10):
    if not query:
        raise HTTPException(status_code=400, detail="Query not provided")
    
    count = min(count, 20)
    try:
        news_batch = news_manager.get_news(query, start=start, count=count)
        if not news_batch:
            raise HTTPException(status_code=404, detail="No news found")
        return news_batch
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to fetch news. Please try again later.")

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

if __name__ == "__main__":
    uvicorn.run("index:app", host="0.0.0.0", port=8000, workers=4)
