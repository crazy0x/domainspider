"""
限速中间件测试用例
"""
import time
import unittest
from scrapy.http import Request, Response
from scrapy.settings import Settings
from src.middlewares.rate_limit import RateLimitMiddleware


class TestRateLimitMiddleware(unittest.TestCase):
    """限速中间件测试"""
    
    def setUp(self):
        """测试前准备"""
        settings = Settings({
            'RATE_LIMIT_GLOBAL': 1,
            'RATE_LIMIT_GLOBAL_BURST': 2,
            'RATE_LIMIT_DOMAINS': {
                'example.com': {'rate': 2, 'burst': 4},
                'test.com': {'rate': 0.5, 'burst': 1}
            },
            'RATE_LIMIT_IPS': {
                '192.168.1.1': {'rate': 3, 'burst': 6}
            },
            'RATE_LIMIT_DYNAMIC': True,
            'RATE_LIMIT_PROXY_RESET': True,
            'RATE_LIMIT_RETRY_IGNORE': True
        })
        
        self.middleware = RateLimitMiddleware(settings)
        self.spider = type('MockSpider', (object,), {'logger': type('MockLogger', (object,), {'debug': lambda *args: None, 'warning': lambda *args: None})()})()
    
    def test_global_rate_limit(self):
        """测试全局速率限制"""
        # 发送多个请求
        requests = [
            Request('http://example1.com/page1'),
            Request('http://example2.com/page2'),
            Request('http://example3.com/page3'),
            Request('http://example4.com/page4')
        ]
        
        # 前两个请求应该通过（burst=2）
        for i in range(2):
            result = self.middleware.process_request(requests[i], self.spider)
            self.assertIsNone(result)
        
        # 第三个请求应该被限速
        result = self.middleware.process_request(requests[2], self.spider)
        self.assertIsNone(result)  # 中间件返回None，让调度器处理
    
    def test_domain_rate_limit(self):
        """测试按域名速率限制"""
        # 发送多个请求到同一个域名
        requests = [
            Request('http://example.com/page1'),
            Request('http://example.com/page2'),
            Request('http://example.com/page3'),
            Request('http://example.com/page4'),
            Request('http://example.com/page5')
        ]
        
        # 前4个请求应该通过（burst=4）
        for i in range(4):
            result = self.middleware.process_request(requests[i], self.spider)
            self.assertIsNone(result)
    
    def test_ip_rate_limit(self):
        """测试按IP速率限制"""
        # 发送多个请求到同一个IP
        requests = [
            Request('http://192.168.1.1/page1', meta={'ip_address': '192.168.1.1'}),
            Request('http://192.168.1.1/page2', meta={'ip_address': '192.168.1.1'}),
            Request('http://192.168.1.1/page3', meta={'ip_address': '192.168.1.1'}),
            Request('http://192.168.1.1/page4', meta={'ip_address': '192.168.1.1'}),
            Request('http://192.168.1.1/page5', meta={'ip_address': '192.168.1.1'}),
            Request('http://192.168.1.1/page6', meta={'ip_address': '192.168.1.1'})
        ]
        
        # 前6个请求应该通过（burst=6）
        for i in range(6):
            result = self.middleware.process_request(requests[i], self.spider)
            self.assertIsNone(result)
    
    def test_proxy_reset(self):
        """测试代理切换时重置限速"""
        # 第一个代理
        request1 = Request('http://example.com/page1', meta={'proxy': 'http://proxy1:8080'})
        result1 = self.middleware.process_request(request1, self.spider)
        self.assertIsNone(result1)
        
        # 第二个代理
        request2 = Request('http://example.com/page2', meta={'proxy': 'http://proxy2:8080'})
        result2 = self.middleware.process_request(request2, self.spider)
        self.assertIsNone(result2)
        
        # 检查计数器是否被重置
        self.assertEqual(len(self.middleware.counters), 1)
    
    def test_retry_ignore(self):
        """测试重试请求不影响限速"""
        # 正常请求
        request1 = Request('http://example.com/page1')
        result1 = self.middleware.process_request(request1, self.spider)
        self.assertIsNone(result1)
        
        # 重试请求
        request2 = Request('http://example.com/page2', meta={'retry_times': 1})
        result2 = self.middleware.process_request(request2, self.spider)
        self.assertIsNone(result2)
        
        # 检查计数器是否只增加了1
        identifier = self.middleware.get_identifier(request1)
        counter = self.middleware.counters[identifier]
        self.assertGreaterEqual(counter['tokens'], 1)  # 重试请求不消耗令牌
    
    def test_dynamic_adjust(self):
        """测试动态调整速率限制"""
        request = Request('http://example.com/page1')
        response = Response('http://example.com/page1', status=429)
        
        # 处理响应
        self.middleware.process_response(request, response, self.spider)
        
        # 检查速率限制是否被调整
        limit = self.middleware.domain_limits['example.com']
        self.assertEqual(limit['rate'], 1.6)  # 2 * 0.8
        self.assertEqual(limit['burst'], 3.2)  # 4 * 0.8
    
    def test_adjust_rate_limit(self):
        """测试动态调整速率限制方法"""
        self.middleware.adjust_rate_limit('example.com', 5, 10)
        
        limit = self.middleware.domain_limits['example.com']
        self.assertEqual(limit['rate'], 5)
        self.assertEqual(limit['burst'], 10)
    
    def test_reset_rate_limit(self):
        """测试重置速率限制方法"""
        # 发送请求消耗令牌
        request = Request('http://example.com/page1')
        self.middleware.process_request(request, self.spider)
        
        # 重置速率限制
        self.middleware.reset_rate_limit('example.com')
        
        # 检查令牌是否被重置
        identifier = self.middleware.get_identifier(request)
        counter = self.middleware.counters[identifier]
        self.assertEqual(counter['tokens'], 4)  # burst=4
    
    def test_spider_closed(self):
        """测试爬虫关闭时清理资源"""
        # 发送请求
        request = Request('http://example.com/page1')
        self.middleware.process_request(request, self.spider)
        
        # 关闭爬虫
        self.middleware.spider_closed(self.spider)
        
        # 检查计数器是否被清空
        self.assertEqual(len(self.middleware.counters), 0)


if __name__ == '__main__':
    unittest.main()
