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

# Instagram credentials - replace with your actual credentials
INSTAGRAM_CREDENTIALS = [
    {"username": "forloopcodes", "password": "susguy69"},
    # Add more accounts as needed
]

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

class InstagramAccountManager:
    def __init__(self, credentials_list: List[dict]):
        self.credentials_list = credentials_list
        self.logged_in_accounts = {}
        self.failed_accounts = set()
        self.account_usage_count = {}
        logger.info(f"Initialized InstagramAccountManager with {len(credentials_list)} accounts")
    
    def get_available_account(self):
        """Get an available logged-in account or create a new session"""
        # Find account with least usage that's not failed
        available_accounts = [
            cred for i, cred in enumerate(self.credentials_list) 
            if i not in self.failed_accounts
        ]
        
        if not available_accounts:
            logger.warning("No available Instagram accounts")
            return None
            
        # Sort by usage count (least used first)
        available_accounts.sort(
            key=lambda x: self.account_usage_count.get(x['username'], 0)
        )
        
        selected_account = available_accounts[0]
        username = selected_account['username']
        
        # Increment usage count
        self.account_usage_count[username] = self.account_usage_count.get(username, 0) + 1
        
        logger.info(f"Selected Instagram account: {username} (usage: {self.account_usage_count[username]})")
        return selected_account
    
    def mark_account_failed(self, username):
        """Mark an account as failed"""
        for i, cred in enumerate(self.credentials_list):
            if cred['username'] == username:
                self.failed_accounts.add(i)
                logger.warning(f"Marked Instagram account {username} as failed")
                # Remove from logged in accounts
                if username in self.logged_in_accounts:
                    del self.logged_in_accounts[username]
                break
    
    def login_account(self, credentials, proxy=None):
        """Login to Instagram with given credentials"""
        username = credentials['username']
        password = credentials['password']
        
        # Check if already logged in
        if username in self.logged_in_accounts:
            logger.debug(f"Account {username} already logged in")
            return self.logged_in_accounts[username]
        
        try:
            logger.info(f"Attempting to login to Instagram account: {username}")
            L = instaloader.Instaloader()
            
            # Configure proxy if provided
            if proxy:
                logger.debug(f"Configuring login with proxy: {proxy_rotator._mask_proxy(proxy)}")
                session = requests.Session()
                session.proxies.update(proxy)
                L._session = session
            
            # Perform login
            L.login(username, password)
            logger.info(f"Successfully logged in to Instagram account: {username}")
            
            # Store logged in session
            self.logged_in_accounts[username] = L
            return L
            
        except instaloader.exceptions.BadCredentialsException:
            logger.error(f"Bad credentials for Instagram account: {username}")
            self.mark_account_failed(username)
            return None
        except instaloader.exceptions.ConnectionException as e:
            logger.error(f"Connection error during login for {username}: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Login failed for Instagram account {username}: {str(e)}")
            return None

instagram_account_manager = InstagramAccountManager(INSTAGRAM_CREDENTIALS)

def create_instaloader_with_proxy_and_login(proxy=None, use_login=True):
    """Create Instaloader instance with proxy configuration and optional login"""
    logger.debug("Creating Instaloader instance")
    
    if use_login:
        # Try to get an available account and login
        account_credentials = instagram_account_manager.get_available_account()
        if account_credentials:
            L = instagram_account_manager.login_account(account_credentials, proxy)
            if L:
                logger.info(f"Using logged-in account: {account_credentials['username']}")
                return L, account_credentials['username']
            else:
                logger.warning("Failed to login, falling back to anonymous access")
    
    # Fallback to anonymous Instaloader
    L = instaloader.Instaloader()
    
    if proxy:
        logger.debug(f"Configuring Instaloader with proxy: {proxy_rotator._mask_proxy(proxy)}")
        # Configure session with proxy
        session = requests.Session()
        session.proxies.update(proxy)
        L._session = session
    else:
        logger.debug("Creating Instaloader without proxy")
    
    return L, None

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

@app.get("/get_likes", response_model=LikesResponse)
async def get_post_likes_get(shortcode: str):
    """GET endpoint that works the same as POST /get_likes but with query parameters"""
    request_id = f"req_{int(time.time())}_{random.randint(1000, 9999)}"
    logger.info(f"[{request_id}] Starting GET request for shortcode: {shortcode}")
    
    max_retries = 3
    logged_username = None  # Track logged username for error handling
    
    for attempt in range(max_retries):
        attempt_start = time.time()
        logger.info(f"[{request_id}] Attempt {attempt + 1}/{max_retries}")
        
        try:
            # Get a proxy for this request
            proxy = proxy_rotator.get_next_proxy()
            logger.info(f"[{request_id}] Using proxy: {proxy_rotator._mask_proxy(proxy) if proxy else 'Direct connection'}")
            
            # Initialize Instaloader with proxy and login
            L, logged_username = create_instaloader_with_proxy_and_login(proxy)
            if logged_username:
                logger.info(f"[{request_id}] Using Instagram account: {logged_username}")
            
            # Add delay to avoid being too aggressive
            if attempt > 0:
                delay = random.uniform(1, 3)
                logger.info(f"[{request_id}] Adding delay of {delay:.2f} seconds before retry")
                time.sleep(delay)
            
            logger.debug(f"[{request_id}] Fetching post data from Instagram")
            # Get post from shortcode
            post = instaloader.Post.from_shortcode(L.context, shortcode)
            
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
                shortcode=shortcode,
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
              # Initialize Instaloader with proxy and login
            L, logged_username = create_instaloader_with_proxy_and_login(proxy)
            if logged_username:
                logger.info(f"[{request_id}] Using Instagram account: {logged_username}")
            
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
    return {
        "message": "Welcome to Instagram Post Likes API with Login Support",
        "endpoints": {
            "POST /get_likes": "Send shortcode in request body",
            "GET /get_likes?shortcode=YOUR_SHORTCODE": "Send shortcode as query parameter",
            "GET /proxy_status": "Check proxy health status",
            "GET /account_status": "Check Instagram account status",
            "GET /logs": "View recent log entries"
        },
        "features": [
            "Multiple proxy rotation",
            "Instagram account login support",
            "Automatic retry with different accounts/proxies",
            "Comprehensive logging and debugging"
        ]
    }

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

@app.get("/account_status")
async def account_status():
    """Endpoint to check Instagram account status"""
    logger.info("Account status endpoint accessed")
    status = {
        "total_accounts": len(INSTAGRAM_CREDENTIALS),
        "failed_accounts": len(instagram_account_manager.failed_accounts),
        "available_accounts": len(INSTAGRAM_CREDENTIALS) - len(instagram_account_manager.failed_accounts),
        "logged_in_accounts": len(instagram_account_manager.logged_in_accounts),
        "account_usage": instagram_account_manager.account_usage_count
    }
    logger.info(f"Account status: {status}")
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
logger.info(f"Instagram accounts: {len(INSTAGRAM_CREDENTIALS)} accounts configured")
logger.info("Features enabled: Proxy rotation, Account login, Comprehensive logging")

if __name__ == "__main__":
    import uvicorn
    logger.info("Starting uvicorn server")
    uvicorn.run(app, host="0.0.0.0", port=8000)