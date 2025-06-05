from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import instaloader
from typing import Optional, List
import random
import requests
import time

app = FastAPI(title="Instagram Post Likes API")

class PostRequest(BaseModel):
    shortcode: str

class LikesResponse(BaseModel):
    shortcode: str
    likes_count: int
    comments_count: int
    views_count: Optional[int] = None
    caption: Optional[str] = None
    error: Optional[str] = None

# List of proxy IPs - replace with your actual proxy list
PROXY_LIST = [
    {"http": "http://proxy1:port", "https": "https://proxy1:port"},
    {"http": "http://proxy2:port", "https": "https://proxy2:port"},
    {"http": "http://proxy3:port", "https": "https://proxy3:port"},
    # Add more proxies as needed
]

# If you have authenticated proxies, use this format:
# {"http": "http://username:password@proxy1:port", "https": "https://username:password@proxy1:port"}

class ProxyRotator:
    def __init__(self, proxy_list: List[dict]):
        self.proxy_list = proxy_list
        self.current_index = 0
        self.failed_proxies = set()
    
    def get_next_proxy(self):
        if len(self.failed_proxies) >= len(self.proxy_list):
            # Reset failed proxies if all have failed
            self.failed_proxies.clear()
        
        available_proxies = [p for i, p in enumerate(self.proxy_list) 
                           if i not in self.failed_proxies]
        
        if not available_proxies:
            return None
            
        return random.choice(available_proxies)
    
    def mark_proxy_failed(self, proxy):
        try:
            index = self.proxy_list.index(proxy)
            self.failed_proxies.add(index)
        except ValueError:
            pass

proxy_rotator = ProxyRotator(PROXY_LIST)

def create_instaloader_with_proxy(proxy=None):
    """Create Instaloader instance with proxy configuration"""
    L = instaloader.Instaloader()
    
    if proxy:
        # Configure session with proxy
        session = requests.Session()
        session.proxies.update(proxy)
        L._session = session
    
    return L

@app.post("/get_likes", response_model=LikesResponse)
async def get_post_likes(request: PostRequest):
    max_retries = 3
    
    for attempt in range(max_retries):
        try:
            # Get a proxy for this request
            proxy = proxy_rotator.get_next_proxy()
            
            # Initialize Instaloader with proxy
            L = create_instaloader_with_proxy(proxy)
            
            # Add delay to avoid being too aggressive
            if attempt > 0:
                time.sleep(random.uniform(1, 3))
            
            # Get post from shortcode
            post = instaloader.Post.from_shortcode(L.context, request.shortcode)
            
            # Get post data
            likes_count = post.likes
            comments_count = post.comments
            views_count = post.video_view_count if post.is_video else 0
            
            if not likes_count:
                raise HTTPException(status_code=404, detail="Post not found or has no likes.")
            
            # Get caption (optional)
            caption = post.caption if post.caption else None
            
            return LikesResponse(
                shortcode=request.shortcode,
                likes_count=likes_count,
                comments_count=comments_count,
                views_count=views_count,
                caption=caption
            )
            
        except instaloader.exceptions.InstaloaderException as e:
            if "rate limit" in str(e).lower() or "too many requests" in str(e).lower():
                # Mark current proxy as failed and try with a different one
                if proxy:
                    proxy_rotator.mark_proxy_failed(proxy)
                
                if attempt < max_retries - 1:
                    continue
                else:
                    raise HTTPException(
                        status_code=429,
                        detail="Rate limited on all available proxies. Please try again later."
                    )
            else:
                raise HTTPException(
                    status_code=400,
                    detail=f"Error fetching post data: {str(e)}"
                )
        except Exception as e:
            if attempt < max_retries - 1:
                # Try with different proxy on generic errors
                if proxy:
                    proxy_rotator.mark_proxy_failed(proxy)
                continue
            else:
                raise HTTPException(
                    status_code=500,
                    detail=f"Internal server error: {str(e)}"
                )
    
    raise HTTPException(
        status_code=500,
        detail="Failed to fetch data after all retry attempts"
    )

@app.get("/")
async def root():
    return {"message": "Welcome to Instagram Post Likes API. Use POST /get_likes with a shortcode."}

@app.get("/proxy_status")
async def proxy_status():
    """Endpoint to check proxy status"""
    return {
        "total_proxies": len(PROXY_LIST),
        "failed_proxies": len(proxy_rotator.failed_proxies),
        "available_proxies": len(PROXY_LIST) - len(proxy_rotator.failed_proxies)
    }