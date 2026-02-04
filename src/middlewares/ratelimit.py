"""
统一限速中间件
支持按域名/IP进行请求频率限制，支持动态调整策略
与代理池、重试机制联动
"""
import time
import threading
from collections import defaultdict, deque
from urllib.parse import urlparse
from typing import Dict, Optional, Tuple, Any
from dataclasses import dataclass, field
import logging

logger = logging.getLogger(__name__)


@dataclass
class RateLimitConfig:
    """限速配置"""
    # 每秒最大请求数
    requests_per_second: float = 1.0
    # 每分钟最大请求数
    requests_per_minute: float = 30.0
    # 突发请求容量（令牌桶容量）
    burst_size: int = 5
    # 冷却时间（秒）- 触发限流后的等待时间
    cooldown_seconds: float = 1.0
    # 是否启用动态调整
    dynamic_adjust: bool = True
    # 动态调整因子
    adjust_factor: float = 0.8
    # 代理独立限速（每个代理单独计算）
    per_proxy_limit: bool = True


@dataclass
class RateLimitState:
    """限速状态"""
    # 令牌桶当前令牌数
    tokens: float = field(default=0.0)
    # 上次更新时间
    last_update: float = field(default_factory=time.time)
    # 请求历史（用于滑动窗口）
    request_history: deque = field(default_factory=lambda: deque(maxlen=1000))
    # 当前延迟时间
    current_delay: float = field(default=0.0)
    # 连续成功次数
    success_count: int = field(default=0)
    # 连续失败次数
    failure_count: int = field(default=0)
    # 当前使用的代理
    current_proxy: Optional[str] = field(default=None)
    # 代理切换时间
    proxy_switch_time: float = field(default=0.0)
    # 锁
    lock: threading.Lock = field(default_factory=threading.Lock)


class TokenBucket:
    """令牌桶限流器"""
    
    def __init__(self, rate: float, capacity: int):
        """
        :param rate: 令牌产生速率（每秒）
        :param capacity: 桶容量
        """
        self.rate = rate
        self.capacity = capacity
        self.tokens = capacity
        self.last_update = time.time()
        self.lock = threading.Lock()
    
    def acquire(self, tokens: int = 1, timeout: Optional[float] = None) -> Tuple[bool, float]:
        """
        尝试获取令牌
        :param tokens: 需要的令牌数
        :param timeout: 最大等待时间
        :return: (是否成功, 需要等待的时间)
        """
        with self.lock:
            now = time.time()
            # 计算新产生的令牌
            elapsed = now - self.last_update
            self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
            self.last_update = now
            
            if self.tokens >= tokens:
                self.tokens -= tokens
                return True, 0.0

            # 计算需要等待的时间
            if self.rate <= 0:
                # 速率为0，无法获取令牌
                return False, float('inf')

            wait_time = (tokens - self.tokens) / self.rate

            if timeout is not None and wait_time > timeout:
                return False, wait_time

            return True, wait_time
    
    def update_rate(self, new_rate: float):
        """动态更新速率"""
        with self.lock:
            now = time.time()
            elapsed = now - self.last_update
            self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
            self.last_update = now
            self.rate = new_rate
    
    def reset(self):
        """重置令牌桶"""
        with self.lock:
            self.tokens = self.capacity
            self.last_update = time.time()


class SlidingWindow:
    """滑动窗口限流器"""
    
    def __init__(self, window_size: int, max_requests: int):
        """
        :param window_size: 窗口大小（秒）
        :param max_requests: 窗口内最大请求数
        """
        self.window_size = window_size
        self.max_requests = max_requests
        self.requests = deque()
        self.lock = threading.Lock()
    
    def allow_request(self) -> Tuple[bool, float]:
        """
        检查是否允许请求
        :return: (是否允许, 需要等待的时间)
        """
        with self.lock:
            now = time.time()
            
            # 清理过期请求
            while self.requests and self.requests[0] < now - self.window_size:
                self.requests.popleft()
            
            if len(self.requests) < self.max_requests:
                self.requests.append(now)
                return True, 0.0
            
            # 计算需要等待的时间
            wait_time = self.requests[0] + self.window_size - now
            return False, max(0, wait_time)
    
    def record_request(self):
        """记录一次请求"""
        with self.lock:
            self.requests.append(time.time())
    
    def get_current_count(self) -> int:
        """获取当前窗口内的请求数"""
        with self.lock:
            now = time.time()
            while self.requests and self.requests[0] < now - self.window_size:
                self.requests.popleft()
            return len(self.requests)
    
    def reset(self):
        """重置窗口"""
        with self.lock:
            self.requests.clear()


class RateLimitManager:
    """限速管理器 - 管理所有域名/IP的限速状态"""
    
    def __init__(self):
        # 域名 -> 限速配置
        self.domain_configs: Dict[str, RateLimitConfig] = {}
        # 域名 -> 令牌桶
        self.domain_buckets: Dict[str, TokenBucket] = {}
        # 域名 -> 滑动窗口（每分钟）
        self.domain_windows: Dict[str, SlidingWindow] = {}
        # 域名+代理 -> 限速状态
        self.proxy_buckets: Dict[str, TokenBucket] = {}
        # 全局默认配置
        self.default_config = RateLimitConfig()
        # 全局锁
        self.lock = threading.RLock()
        
        # 统计信息
        self.stats = {
            'total_requests': 0,
            'throttled_requests': 0,
            'total_wait_time': 0.0,
        }
    
    def set_domain_config(self, domain: str, config: RateLimitConfig):
        """设置特定域名的限速配置"""
        with self.lock:
            self.domain_configs[domain] = config
            # 重新创建限速器
            self.domain_buckets[domain] = TokenBucket(
                rate=config.requests_per_second,
                capacity=config.burst_size
            )
            self.domain_windows[domain] = SlidingWindow(
                window_size=60,
                max_requests=int(config.requests_per_minute)
            )
    
    def get_domain_config(self, domain: str) -> RateLimitConfig:
        """获取域名的限速配置"""
        with self.lock:
            return self.domain_configs.get(domain, self.default_config)
    
    def _get_bucket_key(self, domain: str, proxy: Optional[str] = None) -> str:
        """获取桶的键"""
        if proxy:
            return f"{domain}::{proxy}"
        return domain
    
    def acquire(self, domain: str, proxy: Optional[str] = None) -> Tuple[bool, float]:
        """
        尝试获取请求许可
        :param domain: 目标域名
        :param proxy: 使用的代理
        :return: (是否允许, 需要等待的时间)
        """
        with self.lock:
            config = self.get_domain_config(domain)
            
            # 检查是否需要按代理独立限速
            if config.per_proxy_limit and proxy:
                bucket_key = self._get_bucket_key(domain, proxy)
                if bucket_key not in self.proxy_buckets:
                    self.proxy_buckets[bucket_key] = TokenBucket(
                        rate=config.requests_per_second,
                        capacity=config.burst_size
                    )
                bucket = self.proxy_buckets[bucket_key]
            else:
                if domain not in self.domain_buckets:
                    self.domain_buckets[domain] = TokenBucket(
                        rate=config.requests_per_second,
                        capacity=config.burst_size
                    )
                bucket = self.domain_buckets[domain]
            
            # 获取令牌
            success, wait_time = bucket.acquire()
            
            # 更新统计
            self.stats['total_requests'] += 1
            if wait_time > 0:
                self.stats['throttled_requests'] += 1
                self.stats['total_wait_time'] += wait_time
            
            return success, wait_time
    
    def update_rate(self, domain: str, new_rate: float):
        """动态更新域名的限速速率"""
        with self.lock:
            if domain in self.domain_buckets:
                self.domain_buckets[domain].update_rate(new_rate)
            
            # 更新配置
            if domain in self.domain_configs:
                self.domain_configs[domain].requests_per_second = new_rate
    
    def on_proxy_switch(self, domain: str, old_proxy: Optional[str], new_proxy: Optional[str]):
        """代理切换时的处理"""
        config = self.get_domain_config(domain)
        if not config.per_proxy_limit:
            return
        
        with self.lock:
            # 为新代理创建新的令牌桶
            if new_proxy:
                bucket_key = self._get_bucket_key(domain, new_proxy)
                self.proxy_buckets[bucket_key] = TokenBucket(
                    rate=config.requests_per_second,
                    capacity=config.burst_size
                )
            
            logger.debug(f"Rate limit: Proxy switched for {domain} from {old_proxy} to {new_proxy}")
    
    def on_retry(self, domain: str, proxy: Optional[str], error_type: str):
        """重试时的处理 - 可以调整限速策略"""
        config = self.get_domain_config(domain)
        if not config.dynamic_adjust:
            return
        
        with self.lock:
            # 根据错误类型调整限速
            if error_type == 'rate_limit':
                # 被限流了，降低速率
                current_rate = config.requests_per_second
                new_rate = current_rate * config.adjust_factor
                self.update_rate(domain, new_rate)
                logger.warning(f"Rate limit: Reduced rate for {domain} to {new_rate:.2f}/s due to rate limiting")
            elif error_type == 'timeout':
                # 超时，稍微降低速率
                current_rate = config.requests_per_second
                new_rate = current_rate * 0.9
                self.update_rate(domain, new_rate)
    
    def on_success(self, domain: str, proxy: Optional[str]):
        """请求成功时的处理 - 可以逐步提高速率"""
        config = self.get_domain_config(domain)
        if not config.dynamic_adjust:
            return
        
        # 可以在这里实现成功多次后逐步提高速率的逻辑
        pass
    
    def reset_domain(self, domain: str):
        """重置域名的限速状态"""
        with self.lock:
            if domain in self.domain_buckets:
                self.domain_buckets[domain].reset()
            if domain in self.domain_windows:
                self.domain_windows[domain].reset()
            
            # 清理该域名的代理桶
            keys_to_remove = [k for k in self.proxy_buckets.keys() if k.startswith(f"{domain}::")]
            for key in keys_to_remove:
                del self.proxy_buckets[key]
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        with self.lock:
            total = self.stats['total_requests']
            throttled = self.stats['throttled_requests']
            return {
                'total_requests': total,
                'throttled_requests': throttled,
                'throttle_rate': throttled / total if total > 0 else 0,
                'total_wait_time': self.stats['total_wait_time'],
                'avg_wait_time': self.stats['total_wait_time'] / throttled if throttled > 0 else 0,
                'domain_count': len(self.domain_buckets),
                'proxy_bucket_count': len(self.proxy_buckets),
            }


class RateLimitMiddleware:
    """
    统一限速中间件
    
    功能特性：
    1. 支持按域名/IP进行请求频率限制
    2. 支持动态调整限速策略
    3. 与代理池联动（代理切换时重置/独立计算）
    4. 与重试机制联动（根据错误类型调整策略）
    5. 支持令牌桶和滑动窗口算法
    """
    
    def __init__(self, crawler):
        self.crawler = crawler
        self.settings = crawler.settings
        
        # 初始化限速管理器
        self.rate_manager = RateLimitManager()
        
        # 读取配置
        self.enabled = self.settings.getbool('RATELIMIT_ENABLED', True)
        self.default_rps = self.settings.getfloat('RATELIMIT_DEFAULT_RPS', 1.0)
        self.default_rpm = self.settings.getfloat('RATELIMIT_DEFAULT_RPM', 30.0)
        self.burst_size = self.settings.getint('RATELIMIT_BURST_SIZE', 5)
        self.per_proxy_limit = self.settings.getbool('RATELIMIT_PER_PROXY', True)
        self.dynamic_adjust = self.settings.getbool('RATELIMIT_DYNAMIC_ADJUST', True)
        
        # 加载域名特定配置
        self._load_domain_configs()
        
        # 记录每个请求使用的代理（用于检测代理切换）
        self.request_proxies: Dict[int, Optional[str]] = {}
        
        crawler.logger.info(f"RateLimitMiddleware initialized: enabled={self.enabled}, "
                           f"default_rps={self.default_rps}, per_proxy={self.per_proxy_limit}")
    
    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler)
    
    def _load_domain_configs(self):
        """加载域名特定的限速配置"""
        # 从设置中读取域名配置
        domain_configs = self.settings.getdict('RATELIMIT_DOMAIN_CONFIGS', {})
        
        for domain, config_dict in domain_configs.items():
            config = RateLimitConfig(
                requests_per_second=config_dict.get('rps', self.default_rps),
                requests_per_minute=config_dict.get('rpm', self.default_rpm),
                burst_size=config_dict.get('burst', self.burst_size),
                dynamic_adjust=config_dict.get('dynamic', self.dynamic_adjust),
                per_proxy_limit=config_dict.get('per_proxy', self.per_proxy_limit)
            )
            self.rate_manager.set_domain_config(domain, config)
            self.crawler.logger.debug(f"Loaded rate limit config for {domain}: {config}")
    
    def _get_domain(self, request) -> str:
        """从请求中提取域名"""
        return urlparse(request.url).netloc
    
    def _get_proxy(self, request) -> Optional[str]:
        """从请求中获取代理"""
        return request.meta.get('proxy')
    
    def process_request(self, request, spider):
        """
        处理请求 - 进行限速控制
        这是核心方法，在请求发送前进行限流判断
        """
        if not self.enabled:
            return None
        
        # 如果请求标记为跳过限速
        if request.meta.get('skip_ratelimit', False):
            return None
        
        domain = self._get_domain(request)
        proxy = self._get_proxy(request)
        
        # 检查是否需要等待
        success, wait_time = self.rate_manager.acquire(domain, proxy)
        
        if wait_time > 0:
            spider.logger.debug(f"Rate limit: Waiting {wait_time:.2f}s for {domain}")
            
            # 使用 Scrapy 的延迟机制
            request.meta['download_delay'] = wait_time
            
            # 记录统计
            self.crawler.stats.inc_value('ratelimit/delayed')
            self.crawler.stats.inc_value(f'ratelimit/delayed/{domain}')
        
        # 记录请求使用的代理（用于后续检测代理切换）
        request.meta['_ratelimit_domain'] = domain
        request.meta['_ratelimit_proxy'] = proxy
        
        # 统计
        self.crawler.stats.inc_value('ratelimit/requests')
        self.crawler.stats.inc_value(f'ratelimit/requests/{domain}')
        
        return None
    
    def process_response(self, request, response, spider):
        """
        处理响应 - 根据响应调整策略
        """
        if not self.enabled:
            return response
        
        domain = request.meta.get('_ratelimit_domain')
        proxy = self._get_proxy(request)
        
        if not domain:
            return response
        
        # 检测代理是否切换
        old_proxy = request.meta.get('_ratelimit_proxy')
        if old_proxy != proxy:
            self.rate_manager.on_proxy_switch(domain, old_proxy, proxy)
            request.meta['_ratelimit_proxy'] = proxy
        
        # 根据响应状态调整策略
        if response.status == 429:  # Too Many Requests
            self.rate_manager.on_retry(domain, proxy, 'rate_limit')
            self.crawler.stats.inc_value('ratelimit/triggered_429')
            spider.logger.warning(f"Rate limit triggered (429) for {domain}")
        elif response.status == 503:  # Service Unavailable
            self.rate_manager.on_retry(domain, proxy, 'server_error')
        else:
            # 成功请求
            self.rate_manager.on_success(domain, proxy)
        
        return response
    
    def process_exception(self, request, exception, spider):
        """
        处理异常 - 根据异常类型调整策略
        """
        if not self.enabled:
            return None
        
        domain = request.meta.get('_ratelimit_domain')
        proxy = self._get_proxy(request)
        
        if not domain:
            return None
        
        # 检测代理是否切换
        old_proxy = request.meta.get('_ratelimit_proxy')
        if old_proxy != proxy:
            self.rate_manager.on_proxy_switch(domain, old_proxy, proxy)
        
        # 根据异常类型调整
        error_msg = str(exception).lower()
        if 'timeout' in error_msg:
            self.rate_manager.on_retry(domain, proxy, 'timeout')
        elif 'connection' in error_msg:
            self.rate_manager.on_retry(domain, proxy, 'connection')
        
        return None
    
    def spider_opened(self, spider):
        """爬虫开始时的处理"""
        spider.logger.info(f"RateLimitMiddleware activated for spider: {spider.name}")

        # 可以在这里加载爬虫特定的配置
        spider_specific_config = getattr(spider, 'ratelimit_config', None)
        if spider_specific_config and isinstance(spider_specific_config, dict):
            for domain, config_dict in spider_specific_config.items():
                config = RateLimitConfig(**config_dict)
                self.rate_manager.set_domain_config(domain, config)
                spider.logger.info(f"Loaded spider-specific rate limit config for {domain}")
    
    def spider_closed(self, spider):
        """爬虫结束时的处理"""
        stats = self.rate_manager.get_stats()
        spider.logger.info("=" * 50)
        spider.logger.info("RATE LIMIT STATISTICS")
        spider.logger.info("=" * 50)
        spider.logger.info(f"Total requests: {stats['total_requests']}")
        spider.logger.info(f"Throttled requests: {stats['throttled_requests']}")
        spider.logger.info(f"Throttle rate: {stats['throttle_rate']:.2%}")
        spider.logger.info(f"Total wait time: {stats['total_wait_time']:.2f}s")
        spider.logger.info(f"Avg wait time: {stats['avg_wait_time']:.2f}s")
        
        # 记录到 Scrapy stats
        for key, value in stats.items():
            self.crawler.stats.set_value(f'ratelimit/{key}', value)


# 为了与重试中间件联动，提供辅助函数
def get_rate_manager(crawler) -> Optional[RateLimitManager]:
    """
    从 crawler 获取限速管理器（用于其他中间件联动）
    """
    # 获取中间件实例
    middlewares = crawler.engine.downloader.middleware.middlewares
    for mw in middlewares:
        if isinstance(mw, RateLimitMiddleware):
            return mw.rate_manager
    return None
