"""
智能重试中间件
与限速中间件联动，根据错误类型调整限速策略
"""
import time
from urllib.parse import urlparse
from scrapy.downloadermiddlewares.retry import RetryMiddleware
from scrapy.utils.response import response_status_message


class SmartRetryMiddleware(RetryMiddleware):
    """
    智能重试中间件 - 增强版，与限速中间件联动
    基于不同错误类型采用不同的重试策略，并通知限速管理器
    """

    def __init__(self, crawler):
        # 注意：RetryMiddleware的__init__只接受settings参数
        # 我们需要手动调用父类初始化
        settings = crawler.settings
        super().__init__(settings)

        self.crawler = crawler
        self.settings = settings

        # 从父类获取异常类型（如果父类没有设置，使用默认值）
        if not hasattr(self, 'EXCEPTIONS_TO_RETRY'):
            from scrapy.core.downloader.handlers.http11 import TunnelError
            from twisted.internet.error import (
                TimeoutError, DNSLookupError, ConnectionRefusedError,
                ConnectionDone, ConnectError, ConnectionLost, TCPTimedOutError
            )
            self.EXCEPTIONS_TO_RETRY = (
                TimeoutError, DNSLookupError, ConnectionRefusedError,
                ConnectionDone, ConnectError, ConnectionLost, TCPTimedOutError,
                TunnelError, Exception
            )

        # 不同错误类型的重试间隔（秒）
        self.retry_delays = {
            'timeout': [1, 3, 5],           # 超时错误
            'connection': [2, 5, 10],       # 连接错误
            'server_error': [1, 2, 4],      # 服务器错误
            'rate_limit': [10, 30, 60],     # 频率限制
            'default': [1, 2, 3],           # 默认
        }

        # 状态码分类
        self.timeout_codes = [408, 504]
        self.server_error_codes = [500, 502, 503]
        self.rate_limit_codes = [429]
        self.connection_errors = ['timeout', 'connection']

        # 是否与限速中间件联动
        self.sync_with_ratelimit = settings.getbool('RETRY_SYNC_RATELIMIT', True)
    
    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler)
    
    def _get_domain(self, request):
        """从请求中提取域名"""
        return urlparse(request.url).netloc

    def _notify_ratelimit(self, request, error_type):
        """通知限速中间件"""
        if not self.sync_with_ratelimit:
            return

        try:
            from .ratelimit import get_rate_manager
            rate_manager = get_rate_manager(self.crawler)
            if rate_manager:
                domain = self._get_domain(request)
                proxy = request.meta.get('proxy')
                rate_manager.on_retry(domain, proxy, error_type)
        except Exception:
            # 如果限速中间件未启用，忽略错误
            pass

    def get_error_type(self, request, response=None, exception=None):
        """判断错误类型"""
        if response:
            status = response.status
            if status in self.timeout_codes:
                return 'timeout'
            elif status in self.server_error_codes:
                return 'server_error'
            elif status in self.rate_limit_codes:
                return 'rate_limit'

        if exception:
            error_msg = str(exception).lower()
            if any(err in error_msg for err in self.connection_errors):
                return 'connection'

        return 'default'
    
    def get_retry_delay(self, error_type, retry_times):
        """获取重试延迟时间"""
        delays = self.retry_delays.get(error_type, self.retry_delays['default'])
        
        if retry_times < len(delays):
            return delays[retry_times]
        else:
            # 超出预定义次数，使用指数退避
            return min(delays[-1] * (2 ** (retry_times - len(delays))), 60)
    
    def process_response(self, request, response, spider):
        """处理响应重试 - 与限速中间件联动"""
        if request.meta.get('dont_retry', False):
            return response

        if response.status in self.retry_http_codes:
            reason = response_status_message(response.status)
            error_type = self.get_error_type(request, response=response)

            # 通知限速中间件
            self._notify_ratelimit(request, error_type)

            return self._retry_with_delay(request, reason, spider, error_type) or response

        return response

    def process_exception(self, request, exception, spider):
        """处理异常重试 - 与限速中间件联动"""
        if isinstance(exception, self.EXCEPTIONS_TO_RETRY) and not request.meta.get('dont_retry', False):
            error_type = self.get_error_type(request, exception=exception)

            # 通知限速中间件
            self._notify_ratelimit(request, error_type)

            return self._retry_with_delay(request, exception, spider, error_type)
    
    def _retry_with_delay(self, request, reason, spider, error_type):
        """带延迟的重试 - 增强版，支持代理切换和限速联动"""
        retries = request.meta.get('retry_times', 0) + 1

        if retries <= self.max_retry_times:
            # 计算延迟时间
            delay = self.get_retry_delay(error_type, retries - 1)

            # 如果是频率限制错误，增加额外延迟
            if error_type == 'rate_limit':
                delay = max(delay, 10)  # 至少等待10秒

            spider.logger.debug(
                f"Retrying {request.url} (failed {retries} times, {error_type}): {reason}"
            )
            spider.logger.debug(f"Retry delay: {delay}s")

            # 设置延迟
            if delay > 0:
                time.sleep(delay)

            # 更新重试次数
            retryreq = request.copy()
            retryreq.meta['retry_times'] = retries
            retryreq.dont_filter = True

            # 记录错误类型到meta，供其他中间件使用
            retryreq.meta['_retry_error_type'] = error_type
            retryreq.meta['_retry_count'] = retries

            # 如果是代理相关错误，清除代理标记以便重新分配
            if error_type in ['rate_limit', 'timeout', 'connection']:
                old_proxy = retryreq.meta.get('proxy')
                if old_proxy:
                    spider.logger.debug(f"Clearing proxy {old_proxy} for retry due to {error_type}")
                    retryreq.meta.pop('proxy', None)
                    retryreq.meta.pop('_proxy_switched', None)
                    retryreq.meta['_proxy_cleared_for_retry'] = old_proxy

            # 记录统计
            spider.crawler.stats.inc_value('retry/count')
            spider.crawler.stats.inc_value(f'retry/reason_count/{error_type}')

            return retryreq
        else:
            spider.logger.error(
                f"Gave up retrying {request.url} (failed {retries} times): {reason}"
            )
            spider.crawler.stats.inc_value('retry/max_reached')
            spider.crawler.stats.inc_value(f'retry/max_reached/{error_type}')
