"""
User-Agent 轮换中间件
"""
import random
from fake_useragent import UserAgent


class RandomUserAgentMiddleware:
    """随机 User-Agent 中间件"""
    
    def __init__(self):
        self.ua = UserAgent()
        
        # 预定义的 User-Agent 池（备用）
        self.user_agent_pool = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Safari/605.1.15',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        ]
    
    @classmethod
    def from_crawler(cls, crawler):
        return cls()
    
    def process_request(self, request, spider):
        """为每个请求设置随机 User-Agent"""
        try:
            # 尝试使用 fake_useragent
            ua = self.ua.random
        except Exception:
            # 如果失败，使用预定义的 UA 池
            ua = random.choice(self.user_agent_pool)
        
        request.headers['User-Agent'] = ua
        spider.logger.debug(f"Set User-Agent: {ua}")
        
        return None
