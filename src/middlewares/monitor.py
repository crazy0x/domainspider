"""
监控中间件
"""
import time
from scrapy import signals


class MonitorMiddleware:
    """
    监控中间件
    收集请求响应统计信息
    """
    
    def __init__(self):
        self.start_time = time.time()
        self.request_count = 0
        self.response_count = 0
        self.error_count = 0
        
    @classmethod
    def from_crawler(cls, crawler):
        middleware = cls()
        
        # 连接信号
        crawler.signals.connect(middleware.spider_opened, signal=signals.spider_opened)
        crawler.signals.connect(middleware.spider_closed, signal=signals.spider_closed)
        
        return middleware
    
    def process_request(self, request, spider):
        """处理请求"""
        self.request_count += 1
        request.meta['request_start_time'] = time.time()
        
        # 记录请求统计
        spider.crawler.stats.inc_value('monitor/requests_total')
        spider.crawler.stats.inc_value(f'monitor/requests_by_domain/{request.url.split("/")[2]}')
        
        return None
    
    def process_response(self, request, response, spider):
        """处理响应"""
        self.response_count += 1
        
        # 计算请求耗时
        start_time = request.meta.get('request_start_time')
        if start_time:
            duration = time.time() - start_time
            spider.crawler.stats.set_value('monitor/avg_response_time', duration)
        
        # 记录响应统计
        spider.crawler.stats.inc_value('monitor/responses_total')
        spider.crawler.stats.inc_value(f'monitor/responses_by_status/{response.status}')
        
        # 记录响应大小
        content_length = len(response.body)
        spider.crawler.stats.inc_value('monitor/bytes_downloaded', content_length)
        
        return response
    
    def process_exception(self, request, exception, spider):
        """处理异常"""
        self.error_count += 1
        
        # 记录错误统计
        spider.crawler.stats.inc_value('monitor/errors_total')
        spider.crawler.stats.inc_value(f'monitor/errors_by_type/{type(exception).__name__}')
        
        return None
    
    def spider_opened(self, spider):
        """爬虫开始时"""
        spider.logger.info(f"Monitor middleware activated for spider: {spider.name}")
        spider.crawler.stats.set_value('monitor/spider_start_time', self.start_time)
    
    def spider_closed(self, spider):
        """爬虫结束时"""
        end_time = time.time()
        duration = end_time - self.start_time
        
        # 记录总体统计
        spider.crawler.stats.set_value('monitor/spider_end_time', end_time)
        spider.crawler.stats.set_value('monitor/spider_duration', duration)
        spider.crawler.stats.set_value('monitor/requests_per_second', self.request_count / duration if duration > 0 else 0)
        
        # 输出监控报告
        self.log_monitor_report(spider)
    
    def log_monitor_report(self, spider):
        """输出监控报告"""
        stats = spider.crawler.stats
        
        spider.logger.info("=" * 50)
        spider.logger.info("MONITOR REPORT")
        spider.logger.info("=" * 50)
        spider.logger.info(f"Spider: {spider.name}")
        spider.logger.info(f"Duration: {stats.get_value('monitor/spider_duration', 0):.2f}s")
        spider.logger.info(f"Requests: {stats.get_value('monitor/requests_total', 0)}")
        spider.logger.info(f"Responses: {stats.get_value('monitor/responses_total', 0)}")
        spider.logger.info(f"Errors: {stats.get_value('monitor/errors_total', 0)}")
        spider.logger.info(f"Items: {stats.get_value('item_scraped_count', 0)}")
        spider.logger.info(f"RPS: {stats.get_value('monitor/requests_per_second', 0):.2f}")
        spider.logger.info(f"Bytes Downloaded: {stats.get_value('monitor/bytes_downloaded', 0)}")
        spider.logger.info("=" * 50)
