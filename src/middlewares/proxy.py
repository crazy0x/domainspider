"""
代理池中间件
与限速中间件联动，支持代理切换时通知限速管理器
"""
import random
import requests
import time
from scrapy.downloadermiddlewares.retry import RetryMiddleware


class ProxyPoolMiddleware:
    """代理池中间件 - 增强版，支持与限速中间件联动"""
    
    def __init__(self, crawler, proxy_api_url, proxy_enabled=True, notify_ratelimit=True):
        self.crawler = crawler
        self.proxy_api_url = proxy_api_url
        self.proxy_enabled = proxy_enabled
        self.notify_ratelimit = notify_ratelimit
        self.proxy_pool = []
        self.failed_proxies = set()
        self.last_refresh = 0
        self.refresh_interval = 300  # 5分钟刷新一次代理池
        
        # 代理使用统计
        self.proxy_stats = {}
        
        if self.proxy_enabled:
            self.refresh_proxies()
    
    @classmethod
    def from_crawler(cls, crawler):
        settings = crawler.settings
        return cls(
            crawler=crawler,
            proxy_api_url=settings.get('PROXY_API_URL'),
            proxy_enabled=settings.getbool('PROXY_ENABLED', True),
            notify_ratelimit=settings.getbool('PROXY_NOTIFY_RATELIMIT', True)
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
    
    def _get_domain(self, request):
        """从请求中提取域名"""
        from urllib.parse import urlparse
        return urlparse(request.url).netloc
    
    def _notify_ratelimit_proxy_switch(self, domain, old_proxy, new_proxy):
        """通知限速中间件代理已切换"""
        if not self.notify_ratelimit:
            return
        
        try:
            # 尝试获取限速管理器并通知代理切换
            from .ratelimit import get_rate_manager
            rate_manager = get_rate_manager(self.crawler)
            if rate_manager:
                rate_manager.on_proxy_switch(domain, old_proxy, new_proxy)
        except Exception:
            # 如果限速中间件未启用，忽略错误
            pass
    
    def process_request(self, request, spider):
        """为每个请求分配代理"""
        if not self.proxy_enabled:
            return None
        
        # 记录之前的代理（用于检测切换）
        old_proxy = request.meta.get('proxy')
        
        # 如果请求已经标记了代理切换，跳过分配
        if request.meta.get('_proxy_switched', False):
            return None
        
        proxy_data = self.get_random_proxy()
        if proxy_data:
            proxy_url = self.format_proxy(proxy_data)
            if proxy_url:
                request.meta['proxy'] = proxy_url
                
                # 检测代理是否切换
                if old_proxy != proxy_url:
                    domain = self._get_domain(request)
                    self._notify_ratelimit_proxy_switch(domain, old_proxy, proxy_url)
                    request.meta['_proxy_switched'] = True
                    spider.logger.debug(f"Proxy switched for {domain}: {old_proxy} -> {proxy_url}")
                
                # 更新代理统计
                if proxy_url not in self.proxy_stats:
                    self.proxy_stats[proxy_url] = {'requests': 0, 'errors': 0}
                self.proxy_stats[proxy_url]['requests'] += 1
                
                spider.logger.debug(f"Using proxy: {proxy_url}")
        
        return None
    
    def process_exception(self, request, exception, spider):
        """代理失败时的处理 - 与限速中间件联动"""
        if 'proxy' in request.meta:
            failed_proxy = request.meta['proxy']
            self.failed_proxies.add(failed_proxy)
            
            # 更新代理错误统计
            if failed_proxy in self.proxy_stats:
                self.proxy_stats[failed_proxy]['errors'] += 1
            
            spider.logger.warning(f"Proxy failed: {failed_proxy}, error: {exception}")
            
            # 通知限速中间件（代理失败可能是触发限流）
            if self.notify_ratelimit:
                try:
                    from .ratelimit import get_rate_manager
                    rate_manager = get_rate_manager(self.crawler)
                    if rate_manager:
                        domain = self._get_domain(request)
                        error_msg = str(exception).lower()
                        if 'timeout' in error_msg:
                            rate_manager.on_retry(domain, failed_proxy, 'timeout')
                        elif 'connection' in error_msg:
                            rate_manager.on_retry(domain, failed_proxy, 'connection')
                except Exception:
                    pass
            
            # 移除失效代理的 meta，重新调度
            old_proxy = request.meta.pop('proxy', None)
            
            # 清除代理切换标记，允许重新分配代理
            request.meta.pop('_proxy_switched', None)
            
            # 记录代理切换信息到请求meta，供重试中间件使用
            request.meta['_proxy_failed'] = old_proxy
            request.meta['_proxy_error'] = str(exception)
            
        return request
    
    def process_response(self, request, response, spider):
        """处理响应 - 与限速中间件联动"""
        # 如果响应状态码表示代理问题，标记代理失效
        if response.status in [407, 429]:  # Proxy Authentication Required, Too Many Requests
            if 'proxy' in request.meta:
                failed_proxy = request.meta['proxy']
                self.failed_proxies.add(failed_proxy)
                spider.logger.warning(f"Proxy blocked: {failed_proxy} (status: {response.status})")
                
                # 通知限速中间件（429表示触发限流）
                if self.notify_ratelimit and response.status == 429:
                    try:
                        from .ratelimit import get_rate_manager
                        rate_manager = get_rate_manager(self.crawler)
                        if rate_manager:
                            domain = self._get_domain(request)
                            rate_manager.on_retry(domain, failed_proxy, 'rate_limit')
                    except Exception:
                        pass
        
        # 检测代理是否切换（响应阶段）
        old_proxy = request.meta.get('_ratelimit_proxy')
        current_proxy = request.meta.get('proxy')
        if old_proxy != current_proxy and current_proxy:
            domain = self._get_domain(request)
            self._notify_ratelimit_proxy_switch(domain, old_proxy, current_proxy)
            request.meta['_ratelimit_proxy'] = current_proxy
        
        return response
