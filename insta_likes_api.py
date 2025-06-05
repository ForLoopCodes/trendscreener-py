from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import instaloader
from typing import Optional, List
import random
import requests
import time
import logging
import sys
from datetime import datetime
import json

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('insta_api.log'),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)

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
        logger.info(f"Initialized ProxyRotator with {len(proxy_list)} proxies")
    
    def get_next_proxy(self):
        if len(self.failed_proxies) >= len(self.proxy_list):
            # Reset failed proxies if all have failed
            logger.warning("All proxies failed, resetting failed proxy list")
            self.failed_proxies.clear()
        
        available_proxies = [p for i, p in enumerate(self.proxy_list) 
                           if i not in self.failed_proxies]
        
        if not available_proxies:
            logger.error("No available proxies found")
            return None
            
        selected_proxy = random.choice(available_proxies)
        proxy_index = self.proxy_list.index(selected_proxy)
        logger.info(f"Selected proxy {proxy_index}: {self._mask_proxy(selected_proxy)}")
        return selected_proxy
    
    def mark_proxy_failed(self, proxy):
        try:
            index = self.proxy_list.index(proxy)
            self.failed_proxies.add(index)
            logger.warning(f"Marked proxy {index} as failed: {self._mask_proxy(proxy)}")
            logger.info(f"Failed proxies count: {len(self.failed_proxies)}/{len(self.proxy_list)}")
        except ValueError:
            logger.error(f"Could not find proxy in list to mark as failed: {self._mask_proxy(proxy)}")
    
    def _mask_proxy(self, proxy):
        """Mask sensitive proxy information for logging"""
        if not proxy:
            return "None"
        masked = {}
        for key, value in proxy.items():
            if '@' in value:
                # Mask credentials
                parts = value.split('@')
                masked[key] = f"{parts[0].split('://')[0]}://***:***@{parts[1]}"
            else:
                masked[key] = value
        return str(masked)

proxy_rotator = ProxyRotator(PROXY_LIST)

def create_instaloader_with_proxy(proxy=None):
    """Create Instaloader instance with proxy configuration"""
    logger.debug("Creating Instaloader instance")
    L = instaloader.Instaloader()
    
    if proxy:
        logger.debug(f"Configuring Instaloader with proxy: {proxy_rotator._mask_proxy(proxy)}")
        # Configure session with proxy
        session = requests.Session()
        session.proxies.update(proxy)
        L._session = session
    else:
        logger.debug("Creating Instaloader without proxy")
    
    return L

@app.middleware("http")
async def log_requests(request, call_next):
    start_time = time.time()
    client_ip = request.client.host
    method = request.method
    url = str(request.url)
    
    logger.info(f"Incoming request: {method} {url} from {client_ip}")
    
    response = await call_next(request)
    
    process_time = time.time() - start_time
    logger.info(f"Request completed: {method} {url} - Status: {response.status_code} - Time: {process_time:.2f}s")
    
    return response

@app.post("/get_likes", response_model=LikesResponse)
async def get_post_likes(request: PostRequest):
    request_id = f"req_{int(time.time())}_{random.randint(1000, 9999)}"
    logger.info(f"[{request_id}] Starting request for shortcode: {request.shortcode}")
    
    max_retries = 3
    
    for attempt in range(max_retries):
        attempt_start = time.time()
        logger.info(f"[{request_id}] Attempt {attempt + 1}/{max_retries}")
        
        try:
            # Get a proxy for this request
            proxy = proxy_rotator.get_next_proxy()
            logger.info(f"[{request_id}] Using proxy: {proxy_rotator._mask_proxy(proxy) if proxy else 'Direct connection'}")
            
            # Initialize Instaloader with proxy
            L = create_instaloader_with_proxy(proxy)
            
            # Add delay to avoid being too aggressive
            if attempt > 0:
                delay = random.uniform(1, 3)
                logger.info(f"[{request_id}] Adding delay of {delay:.2f} seconds before retry")
                time.sleep(delay)
            
            logger.debug(f"[{request_id}] Fetching post data from Instagram")
            # Get post from shortcode
            post = instaloader.Post.from_shortcode(L.context, request.shortcode)
            
            # Get post data
            likes_count = post.likes
            comments_count = post.comments
            views_count = post.video_view_count if post.is_video else 0
            
            logger.info(f"[{request_id}] Successfully fetched post data:")
            logger.info(f"[{request_id}] - Likes: {likes_count}")
            logger.info(f"[{request_id}] - Comments: {comments_count}")
            logger.info(f"[{request_id}] - Views: {views_count}")
            logger.info(f"[{request_id}] - Is Video: {post.is_video}")
            
            if not likes_count:
                logger.warning(f"[{request_id}] Post found but has no likes")
                raise HTTPException(status_code=404, detail="Post not found or has no likes.")
            
            # Get caption (optional)
            caption = post.caption if post.caption else None
            if caption:
                logger.debug(f"[{request_id}] Caption length: {len(caption)} characters")
            
            attempt_time = time.time() - attempt_start
            logger.info(f"[{request_id}] Request completed successfully in {attempt_time:.2f} seconds")
            
            response = LikesResponse(
                shortcode=request.shortcode,
                likes_count=likes_count,
                comments_count=comments_count,
                views_count=views_count,
                caption=caption
            )
            
            logger.debug(f"[{request_id}] Response: {json.dumps(response.dict(), indent=2)}")
            return response
            
        except instaloader.exceptions.InstaloaderException as e:
            attempt_time = time.time() - attempt_start
            error_msg = str(e)
            logger.error(f"[{request_id}] InstaloaderException in attempt {attempt + 1}: {error_msg}")
            logger.error(f"[{request_id}] Attempt failed in {attempt_time:.2f} seconds")
            
            if "rate limit" in error_msg.lower() or "too many requests" in error_msg.lower():
                logger.warning(f"[{request_id}] Rate limit detected")
                # Mark current proxy as failed and try with a different one
                if proxy:
                    proxy_rotator.mark_proxy_failed(proxy)
                
                if attempt < max_retries - 1:
                    logger.info(f"[{request_id}] Will retry with different proxy")
                    continue
                else:
                    logger.error(f"[{request_id}] Rate limited on all available proxies")
                    raise HTTPException(
                        status_code=429,
                        detail="Rate limited on all available proxies. Please try again later."
                    )
            else:
                logger.error(f"[{request_id}] Other Instaloader error: {error_msg}")
                raise HTTPException(
                    status_code=400,
                    detail=f"Error fetching post data: {error_msg}"
                )
                
        except Exception as e:
            attempt_time = time.time() - attempt_start
            error_msg = str(e)
            logger.error(f"[{request_id}] Generic exception in attempt {attempt + 1}: {error_msg}")
            logger.error(f"[{request_id}] Attempt failed in {attempt_time:.2f} seconds")
            logger.exception(f"[{request_id}] Full exception details:")
            
            if attempt < max_retries - 1:
                # Try with different proxy on generic errors
                if proxy:
                    proxy_rotator.mark_proxy_failed(proxy)
                logger.info(f"[{request_id}] Will retry with different proxy")
                continue
            else:
                logger.error(f"[{request_id}] All retry attempts exhausted")
                raise HTTPException(
                    status_code=500,
                    detail=f"Internal server error: {error_msg}"
                )
    
    logger.error(f"[{request_id}] Failed to fetch data after all retry attempts")
    raise HTTPException(
        status_code=500,
        detail="Failed to fetch data after all retry attempts"
    )

@app.get("/")
async def root():
    logger.info("Root endpoint accessed")
    return {"message": "Welcome to Instagram Post Likes API. Use POST /get_likes with a shortcode."}

@app.get("/proxy_status")
async def proxy_status():
    """Endpoint to check proxy status"""
    logger.info("Proxy status endpoint accessed")
    status = {
        "total_proxies": len(PROXY_LIST),
        "failed_proxies": len(proxy_rotator.failed_proxies),
        "available_proxies": len(PROXY_LIST) - len(proxy_rotator.failed_proxies),
        "failed_proxy_indices": list(proxy_rotator.failed_proxies)
    }
    logger.info(f"Proxy status: {status}")
    return status

@app.get("/logs")
async def get_recent_logs():
    """Endpoint to get recent log entries"""
    try:
        with open('insta_api.log', 'r') as f:
            lines = f.readlines()
            # Return last 50 lines
            recent_logs = lines[-50:] if len(lines) > 50 else lines
            return {"logs": recent_logs}
    except FileNotFoundError:
        return {"logs": ["Log file not found"]}

# Log startup
logger.info("Instagram API starting up")
logger.info(f"Proxy configuration: {len(PROXY_LIST)} proxies loaded")

if __name__ == "__main__":
    import uvicorn
    logger.info("Starting uvicorn server")
    uvicorn.run(app, host="0.0.0.0", port=8000)