"""
限速中间件
"""
import time
from collections import defaultdict
from scrapy import signals
from urllib.parse import urlparse


class RateLimitMiddleware:
    """限速中间件"""
    
    def __init__(self, settings):
        # 全局默认配置
        self.global_rate_limit = settings.getint('RATE_LIMIT_GLOBAL', 10)  # 全局默认每秒请求数
        self.global_burst = settings.getint('RATE_LIMIT_GLOBAL_BURST', 20)  # 全局默认突发请求数
        
        # 按域名/IP的配置
        self.domain_limits = settings.getdict('RATE_LIMIT_DOMAINS', {})
        self.ip_limits = settings.getdict('RATE_LIMIT_IPS', {})
        
        # 限速计数器
        self.counters = defaultdict(lambda: {
            'tokens': 0,
            'last_refresh': time.time()
        })
        
        # 动态调整开关
        self.dynamic_adjust = settings.getbool('RATE_LIMIT_DYNAMIC', True)
        
        # 代理切换时重置限速
        self.proxy_reset = settings.getbool('RATE_LIMIT_PROXY_RESET', True)
        
        # 重试请求不影响限速
        self.retry_ignore = settings.getbool('RATE_LIMIT_RETRY_IGNORE', True)
        
        # 最后使用的代理
        self.last_proxy = None
    
    @classmethod
    def from_crawler(cls, crawler):
        middleware = cls(crawler.settings)
        
        # 连接信号
        crawler.signals.connect(middleware.spider_closed, signal=signals.spider_closed)
        
        return middleware
    
    def get_identifier(self, request):
        """获取请求的标识符（域名/IP）"""
        # 优先使用IP
        if 'ip_address' in request.meta:
            return request.meta['ip_address']
        
        # 解析域名
        parsed = urlparse(request.url)
        domain = parsed.netloc
        
        # 如果没有域名，使用IP
        if not domain and 'proxy' in request.meta:
            proxy = request.meta['proxy']
            parsed_proxy = urlparse(proxy)
            domain = parsed_proxy.netloc
        
        return domain
    
    def get_rate_limit(self, identifier):
        """获取标识符对应的速率限制"""
        # 优先使用IP配置
        if identifier in self.ip_limits:
            return self.ip_limits[identifier]
        
        # 然后使用域名配置
        if identifier in self.domain_limits:
            return self.domain_limits[identifier]
        
        # 使用全局默认配置
        return {
            'rate': self.global_rate_limit,
            'burst': self.global_burst
        }
    
    def update_tokens(self, counter, rate, burst):
        """更新令牌桶"""
        now = time.time()
        elapsed = now - counter['last_refresh']
        
        # 如果是初始状态（tokens=0），设置为burst
        if counter['tokens'] == 0:
            counter['tokens'] = burst
        else:
            # 计算新的令牌数
            new_tokens = counter['tokens'] + elapsed * rate
            counter['tokens'] = min(new_tokens, burst)
        
        counter['last_refresh'] = now
        
        return counter
    
    def check_rate_limit(self, request):
        """检查请求是否超过速率限制"""
        # 重试请求不影响限速
        if self.retry_ignore and request.meta.get('retry_times', 0) > 0:
            return False
        
        identifier = self.get_identifier(request)
        if not identifier:
            return False
        
        # 获取速率限制
        limit = self.get_rate_limit(identifier)
        rate = limit.get('rate', self.global_rate_limit)
        burst = limit.get('burst', self.global_burst)
        
        # 获取当前计数器状态
        current_counter = self.counters[identifier]
        # 创建临时计数器用于计算，不修改原始计数器
        temp_counter = {
            'tokens': current_counter['tokens'],
            'last_refresh': current_counter['last_refresh']
        }
        
        # 更新临时令牌桶
        temp_counter = self.update_tokens(temp_counter, rate, burst)
        
        # 检查是否有足够的令牌
        if temp_counter['tokens'] >= 1:
            return False
        else:
            return True
    
    def process_request(self, request, spider):
        """处理请求前的限速检查"""
        # 检查代理是否切换
        if self.proxy_reset and 'proxy' in request.meta:
            current_proxy = request.meta['proxy']
            if current_proxy != self.last_proxy:
                # 代理切换，重置所有计数器
                self.counters.clear()
                self.last_proxy = current_proxy
                spider.logger.debug(f"Proxy changed, reset rate limit counters")
        
        # 重试请求不影响限速
        if self.retry_ignore and request.meta.get('retry_times', 0) > 0:
            return None
        
        # 检查速率限制
        if self.check_rate_limit(request):
            identifier = self.get_identifier(request)
            spider.logger.warning(f"Rate limit exceeded for {identifier}")
            
            # 可以选择延迟请求或返回None让调度器处理
            # 这里选择返回None，让调度器决定如何处理
            return None
        
        # 消耗令牌
        identifier = self.get_identifier(request)
        if identifier:
            limit = self.get_rate_limit(identifier)
            rate = limit.get('rate', self.global_rate_limit)
            burst = limit.get('burst', self.global_burst)
            
            # 获取或创建计数器
            counter = self.counters[identifier]
            
            # 更新令牌桶
            counter = self.update_tokens(counter, rate, burst)
            
            # 消耗令牌
            if counter['tokens'] >= 1:
                counter['tokens'] -= 1
        
        return None
    
    def process_response(self, request, response, spider):
        """处理响应"""
        # 动态调整速率限制（根据响应状态码）
        if self.dynamic_adjust and response.status == 429:
            identifier = self.get_identifier(request)
            if identifier:
                limit = self.get_rate_limit(identifier)
                # 降低速率限制
                new_rate = max(limit.get('rate', self.global_rate_limit) * 0.8, 1)
                new_burst = max(limit.get('burst', self.global_burst) * 0.8, 1)
                
                if identifier in self.domain_limits:
                    self.domain_limits[identifier]['rate'] = new_rate
                    self.domain_limits[identifier]['burst'] = new_burst
                elif identifier in self.ip_limits:
                    self.ip_limits[identifier]['rate'] = new_rate
                    self.ip_limits[identifier]['burst'] = new_burst
                
                spider.logger.warning(f"Rate limit adjusted for {identifier}: rate={new_rate}, burst={new_burst}")
        
        return response
    
    def spider_closed(self, spider):
        """爬虫关闭时清理资源"""
        self.counters.clear()
        self.last_proxy = None
    
    def adjust_rate_limit(self, identifier, rate, burst):
        """动态调整速率限制"""
        if identifier in self.domain_limits:
            self.domain_limits[identifier]['rate'] = rate
            self.domain_limits[identifier]['burst'] = burst
        elif identifier in self.ip_limits:
            self.ip_limits[identifier]['rate'] = rate
            self.ip_limits[identifier]['burst'] = burst
        else:
            # 为新的标识符添加配置
            self.domain_limits[identifier] = {'rate': rate, 'burst': burst}
        
        # 重置计数器
        if identifier in self.counters:
            self.counters[identifier]['tokens'] = burst
            self.counters[identifier]['last_refresh'] = time.time()
    
    def reset_rate_limit(self, identifier=None):
        """重置速率限制"""
        if identifier:
            if identifier in self.counters:
                limit = self.get_rate_limit(identifier)
                self.counters[identifier]['tokens'] = limit.get('burst', self.global_burst)
                self.counters[identifier]['last_refresh'] = time.time()
        else:
            # 重置所有计数器
            for counter in self.counters.values():
                counter['tokens'] = self.global_burst
                counter['last_refresh'] = time.time()
