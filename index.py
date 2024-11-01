from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from GoogleNews import GoogleNews
from fastapi_cache import FastAPICache
from fastapi_cache.backends.memory import MemoryCacheBackend
from fastapi_cache.decorator import cache
import asyncio
import time
from typing import List, Dict, Optional
import uvicorn

app = FastAPI()

class NewsManager:
    def __init__(self):
        self.googlenews = GoogleNews(lang='pt', region='BR')
        self.last_request = {}
        self.lock = asyncio.Lock()
    
    async def get_news(self, query: str, start: int = 0, count: int = 3) -> List[Dict]:
        async with self.lock:
            current_time = time.time()
            last_time = self.last_request.get(query, 0)
            
            if current_time - last_time < 2:
                await asyncio.sleep(2)
            
            try:
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
                
                self.last_request[query] = current_time
                return news_list
            finally:
                self.googlenews.clear()

news_manager = NewsManager()

# Rate limiting
class RateLimiter:
    def __init__(self, requests_per_minute: int = 30):
        self.requests_per_minute = requests_per_minute
        self.requests = {}
    
    async def check(self, ip: str) -> bool:
        current_time = time.time()
        
        # Limpar requisições antigas
        self.requests[ip] = [t for t in self.requests.get(ip, []) 
                           if current_time - t < 60]
        
        if len(self.requests.get(ip, [])) >= self.requests_per_minute:
            return False
        
        self.requests.setdefault(ip, []).append(current_time)
        return True

rate_limiter = RateLimiter()

@app.on_event("startup")
async def startup():
    FastAPICache.init(MemoryCacheBackend())

@app.get("/news")
@cache(expire=300)
async def get_news(
    request: Request,
    query: str,
    start: Optional[int] = 0,
    count: Optional[int] = 10
):
    # Verificar rate limit
    if not await rate_limiter.check(request.client.host):
        raise HTTPException(
            status_code=429,
            detail="Too many requests. Please try again later."
        )
    
    if not query:
        raise HTTPException(
            status_code=400,
            detail="Query not provided"
        )
    
    count = min(count, 20)
    
    try:
        news_batch = await news_manager.get_news(query, start=start, count=count)
        if not news_batch:
            raise HTTPException(
                status_code=404,
                detail="No news found"
            )
        return news_batch
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail="Failed to fetch news. Please try again later."
        )

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        workers=4
    )
