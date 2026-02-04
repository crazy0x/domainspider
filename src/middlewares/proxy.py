"""
代理池中间件
"""
import random
import requests
import time
from scrapy.downloadermiddlewares.retry import RetryMiddleware


class ProxyPoolMiddleware:
    """代理池中间件"""
    
    def __init__(self, proxy_api_url, proxy_enabled=True):
        self.proxy_api_url = proxy_api_url
        self.proxy_enabled = proxy_enabled
        self.proxy_pool = []
        self.failed_proxies = set()
        self.last_refresh = 0
        self.refresh_interval = 300  # 5分钟刷新一次代理池
        
        if self.proxy_enabled:
            self.refresh_proxies()
    
    @classmethod
    def from_crawler(cls, crawler):
        settings = crawler.settings
        return cls(
            proxy_api_url=settings.get('PROXY_API_URL'),
            proxy_enabled=settings.getbool('PROXY_ENABLED', True)
        )
    
    def refresh_proxies(self):
        """从代理服务获取 IP 池"""
        if not self.proxy_enabled:
            return
        
        try:
            resp = requests.get(self.proxy_api_url, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                
                # 适配不同的代理API格式
                if isinstance(data, list):
                    self.proxy_pool = data
                elif isinstance(data, dict):
                    if 'proxies' in data:
                        self.proxy_pool = data['proxies']
                    elif 'proxy' in data:
                        # 单个代理格式
                        proxy = data['proxy']
                        if isinstance(proxy, str):
                            # "ip:port" 格式
                            ip, port = proxy.split(':')
                            self.proxy_pool = [{'ip': ip, 'port': port}]
                        else:
                            self.proxy_pool = [proxy]
                
                self.last_refresh = time.time()
                self.failed_proxies.clear()  # 清空失效代理记录
                
        except Exception as e:
            # 代理服务不可用时的日志
            pass
    
    def get_random_proxy(self):
        """获取随机可用代理"""
        if not self.proxy_enabled or not self.proxy_pool:
            return None
        
        # 检查是否需要刷新代理池
        if time.time() - self.last_refresh > self.refresh_interval:
            self.refresh_proxies()
        
        # 过滤掉失效的代理
        available_proxies = [
            proxy for proxy in self.proxy_pool 
            if self.format_proxy(proxy) not in self.failed_proxies
        ]
        
        if not available_proxies:
            # 如果没有可用代理，重新刷新
            self.refresh_proxies()
            available_proxies = self.proxy_pool
        
        if available_proxies:
            return random.choice(available_proxies)
        
        return None
    
    def format_proxy(self, proxy):
        """格式化代理为标准格式"""
        if isinstance(proxy, str):
            return f"http://{proxy}"
        elif isinstance(proxy, dict):
            ip = proxy.get('ip')
            port = proxy.get('port')
            if ip and port:
                return f"http://{ip}:{port}"
        return None
    
    def process_request(self, request, spider):
        """为每个请求分配代理"""
        if not self.proxy_enabled:
            return None
        
        proxy_data = self.get_random_proxy()
        if proxy_data:
            proxy_url = self.format_proxy(proxy_data)
            if proxy_url:
                request.meta['proxy'] = proxy_url
                spider.logger.debug(f"Using proxy: {proxy_url}")
        
        return None
    
    def process_exception(self, request, exception, spider):
        """代理失败时的处理"""
        if 'proxy' in request.meta:
            failed_proxy = request.meta['proxy']
            self.failed_proxies.add(failed_proxy)
            spider.logger.warning(f"Proxy failed: {failed_proxy}")
            
            # 移除失效代理的 meta，重新调度
            request.meta.pop('proxy', None)
            
        return request
    
    def process_response(self, request, response, spider):
        """处理响应"""
        # 如果响应状态码表示代理问题，标记代理失效
        if response.status in [407, 429]:  # Proxy Authentication Required, Too Many Requests
            if 'proxy' in request.meta:
                failed_proxy = request.meta['proxy']
                self.failed_proxies.add(failed_proxy)
                spider.logger.warning(f"Proxy blocked: {failed_proxy}")
        
        return response
