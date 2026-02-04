"""
限速中间件测试用例
测试 TokenBucket、SlidingWindow、RateLimitManager 和 RateLimitMiddleware 的功能
"""
import time
import threading
import unittest
from unittest.mock import Mock, MagicMock, patch
from urllib.parse import urlparse

import sys
sys.path.insert(0, '/Users/lifenghua/Codes/domainspider_seed')

from src.middlewares.ratelimit import (
    TokenBucket,
    SlidingWindow,
    RateLimitManager,
    RateLimitConfig,
    RateLimitMiddleware,
)


class TestTokenBucket(unittest.TestCase):
    """测试令牌桶限流器"""

    def test_initial_tokens(self):
        """测试初始令牌数等于容量"""
        bucket = TokenBucket(rate=1.0, capacity=5)
        # 初始应该有5个令牌
        success, wait_time = bucket.acquire(tokens=5)
        self.assertTrue(success)
        self.assertEqual(wait_time, 0.0)

    def test_token_consumption(self):
        """测试令牌消耗"""
        bucket = TokenBucket(rate=1.0, capacity=5)
        # 消耗3个令牌
        success, _ = bucket.acquire(tokens=3)
        self.assertTrue(success)

        # 再消耗3个，应该成功（剩余2+新产生的）
        success, wait_time = bucket.acquire(tokens=3)
        self.assertTrue(success)
        self.assertGreaterEqual(wait_time, 0)

    def test_token_regeneration(self):
        """测试令牌再生"""
        bucket = TokenBucket(rate=10.0, capacity=5)
        # 消耗所有令牌
        bucket.acquire(tokens=5)

        # 等待一段时间让令牌再生
        time.sleep(0.3)  # 应该产生约3个令牌

        # 应该能获取到令牌
        success, wait_time = bucket.acquire(tokens=2)
        self.assertTrue(success)
        self.assertEqual(wait_time, 0.0)

    def test_rate_update(self):
        """测试动态更新速率"""
        bucket = TokenBucket(rate=1.0, capacity=5)
        bucket.update_rate(2.0)

        # 消耗所有令牌
        bucket.acquire(tokens=5)

        # 新速率应该生效
        time.sleep(0.6)  # 在2.0 rate下应该产生1.2个令牌
        success, _ = bucket.acquire(tokens=1)
        self.assertTrue(success)

    def test_reset(self):
        """测试重置"""
        bucket = TokenBucket(rate=1.0, capacity=5)
        # 消耗所有令牌
        bucket.acquire(tokens=5)

        # 重置
        bucket.reset()

        # 应该能立即获取5个令牌
        success, _ = bucket.acquire(tokens=5)
        self.assertTrue(success)

    def test_thread_safety(self):
        """测试线程安全"""
        bucket = TokenBucket(rate=100.0, capacity=100)
        results = []

        def acquire_tokens():
            for _ in range(10):
                success, _ = bucket.acquire(tokens=1)
                results.append(success)
                time.sleep(0.01)

        threads = [threading.Thread(target=acquire_tokens) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # 所有请求都应该成功
        self.assertTrue(all(results))


class TestSlidingWindow(unittest.TestCase):
    """测试滑动窗口限流器"""

    def test_window_limit(self):
        """测试窗口限制"""
        window = SlidingWindow(window_size=1, max_requests=3)

        # 前3个请求应该成功
        for _ in range(3):
            allowed, _ = window.allow_request()
            self.assertTrue(allowed)

        # 第4个请求应该被限制
        allowed, wait_time = window.allow_request()
        self.assertFalse(allowed)
        self.assertGreater(wait_time, 0)

    def test_window_sliding(self):
        """测试窗口滑动"""
        window = SlidingWindow(window_size=0.5, max_requests=2)

        # 2个请求
        window.allow_request()
        window.allow_request()

        # 第3个应该被限制
        allowed, _ = window.allow_request()
        self.assertFalse(allowed)

        # 等待窗口滑动
        time.sleep(0.6)

        # 现在应该允许
        allowed, _ = window.allow_request()
        self.assertTrue(allowed)

    def test_current_count(self):
        """测试当前计数"""
        window = SlidingWindow(window_size=1, max_requests=5)

        self.assertEqual(window.get_current_count(), 0)

        window.record_request()
        self.assertEqual(window.get_current_count(), 1)

        window.record_request()
        self.assertEqual(window.get_current_count(), 2)

    def test_reset(self):
        """测试重置"""
        window = SlidingWindow(window_size=1, max_requests=2)

        window.record_request()
        window.record_request()

        window.reset()

        self.assertEqual(window.get_current_count(), 0)
        allowed, _ = window.allow_request()
        self.assertTrue(allowed)


class TestRateLimitManager(unittest.TestCase):
    """测试限速管理器"""

    def setUp(self):
        self.manager = RateLimitManager()

    def test_default_config(self):
        """测试默认配置"""
        config = self.manager.get_domain_config('example.com')
        self.assertEqual(config.requests_per_second, 1.0)
        self.assertEqual(config.requests_per_minute, 30.0)

    def test_set_domain_config(self):
        """测试设置域名配置"""
        config = RateLimitConfig(
            requests_per_second=2.0,
            requests_per_minute=60.0,
            burst_size=10
        )
        self.manager.set_domain_config('example.com', config)

        retrieved = self.manager.get_domain_config('example.com')
        self.assertEqual(retrieved.requests_per_second, 2.0)
        self.assertEqual(retrieved.requests_per_minute, 60.0)

    def test_acquire(self):
        """测试获取许可"""
        # 设置较高的速率以便测试
        config = RateLimitConfig(requests_per_second=100.0, burst_size=100)
        self.manager.set_domain_config('example.com', config)

        success, wait_time = self.manager.acquire('example.com')
        self.assertTrue(success)
        self.assertEqual(wait_time, 0.0)

    def test_acquire_with_proxy(self):
        """测试带代理的获取许可"""
        config = RateLimitConfig(
            requests_per_second=100.0,
            burst_size=100,
            per_proxy_limit=True
        )
        self.manager.set_domain_config('example.com', config)

        # 不同代理应该独立计算
        success1, _ = self.manager.acquire('example.com', 'proxy1')
        success2, _ = self.manager.acquire('example.com', 'proxy2')

        self.assertTrue(success1)
        self.assertTrue(success2)

    def test_on_proxy_switch(self):
        """测试代理切换处理"""
        config = RateLimitConfig(per_proxy_limit=True)
        self.manager.set_domain_config('example.com', config)

        # 先使用一个代理
        self.manager.acquire('example.com', 'proxy1')

        # 切换代理
        self.manager.on_proxy_switch('example.com', 'proxy1', 'proxy2')

        # 新代理应该有独立的桶
        bucket_key = 'example.com::proxy2'
        self.assertIn(bucket_key, self.manager.proxy_buckets)

    def test_on_retry_rate_limit(self):
        """测试重试时触发限流的处理"""
        config = RateLimitConfig(
            requests_per_second=10.0,
            dynamic_adjust=True,
            adjust_factor=0.5
        )
        self.manager.set_domain_config('example.com', config)

        # 模拟触发限流
        self.manager.on_retry('example.com', None, 'rate_limit')

        # 速率应该降低
        new_config = self.manager.get_domain_config('example.com')
        self.assertEqual(new_config.requests_per_second, 5.0)

    def test_stats(self):
        """测试统计信息"""
        config = RateLimitConfig(requests_per_second=100.0, burst_size=100)
        self.manager.set_domain_config('example.com', config)

        # 产生一些请求
        for _ in range(5):
            self.manager.acquire('example.com')

        stats = self.manager.get_stats()
        self.assertEqual(stats['total_requests'], 5)
        self.assertEqual(stats['domain_count'], 1)

    def test_reset_domain(self):
        """测试重置域名"""
        config = RateLimitConfig(requests_per_second=100.0, burst_size=10)
        self.manager.set_domain_config('example.com', config)

        # 消耗一些令牌
        for _ in range(10):
            self.manager.acquire('example.com')

        # 重置
        self.manager.reset_domain('example.com')

        # 应该能再次获取
        success, _ = self.manager.acquire('example.com')
        self.assertTrue(success)


class TestRateLimitMiddleware(unittest.TestCase):
    """测试限速中间件"""

    def setUp(self):
        """设置测试环境"""
        self.crawler = Mock()
        self.crawler.settings = Mock()
        self.crawler.settings.getbool = Mock(return_value=True)
        self.crawler.settings.getfloat = Mock(return_value=1.0)
        self.crawler.settings.getint = Mock(return_value=5)
        self.crawler.settings.getdict = Mock(return_value={})
        self.crawler.logger = Mock()
        self.crawler.stats = Mock()

        self.spider = Mock()
        self.spider.logger = Mock()
        self.spider.name = 'test_spider'

    def test_init(self):
        """测试初始化"""
        middleware = RateLimitMiddleware(self.crawler)

        self.assertTrue(middleware.enabled)
        self.assertEqual(middleware.default_rps, 1.0)
        self.assertTrue(middleware.per_proxy_limit)

    def test_get_domain(self):
        """测试域名提取"""
        middleware = RateLimitMiddleware(self.crawler)

        request = Mock()
        request.url = 'https://example.com/path'

        domain = middleware._get_domain(request)
        self.assertEqual(domain, 'example.com')

    def test_process_request(self):
        """测试请求处理"""
        middleware = RateLimitMiddleware(self.crawler)

        request = Mock()
        request.url = 'https://example.com/path'
        request.meta = {}

        result = middleware.process_request(request, self.spider)

        # 应该返回None让请求继续
        self.assertIsNone(result)
        # 应该记录域名
        self.assertEqual(request.meta['_ratelimit_domain'], 'example.com')

    def test_process_request_skip(self):
        """测试跳过限速的请求"""
        middleware = RateLimitMiddleware(self.crawler)

        request = Mock()
        request.url = 'https://example.com/path'
        request.meta = {'skip_ratelimit': True}

        result = middleware.process_request(request, self.spider)

        self.assertIsNone(result)
        # 不应该记录限速信息
        self.assertNotIn('_ratelimit_domain', request.meta)

    def test_process_response_rate_limit(self):
        """测试处理429响应"""
        middleware = RateLimitMiddleware(self.crawler)

        request = Mock()
        request.url = 'https://example.com/path'
        request.meta = {'_ratelimit_domain': 'example.com'}

        response = Mock()
        response.status = 429

        result = middleware.process_response(request, response, self.spider)

        # 应该返回响应
        self.assertEqual(result, response)
        # 应该记录统计
        self.crawler.stats.inc_value.assert_called_with('ratelimit/triggered_429')

    def test_process_response_success(self):
        """测试处理成功响应"""
        middleware = RateLimitMiddleware(self.crawler)

        request = Mock()
        request.url = 'https://example.com/path'
        request.meta = {'_ratelimit_domain': 'example.com'}

        response = Mock()
        response.status = 200

        result = middleware.process_response(request, response, self.spider)

        self.assertEqual(result, response)

    def test_process_exception(self):
        """测试处理异常"""
        middleware = RateLimitMiddleware(self.crawler)

        request = Mock()
        request.url = 'https://example.com/path'
        request.meta = {'_ratelimit_domain': 'example.com'}

        exception = Exception('Connection timeout')

        result = middleware.process_exception(request, exception, self.spider)

        # 应该返回None
        self.assertIsNone(result)

    def test_spider_opened(self):
        """测试爬虫开始"""
        middleware = RateLimitMiddleware(self.crawler)

        # 设置爬虫特定的配置
        self.spider.ratelimit_config = {
            'example.com': {
                'requests_per_second': 2.0,
                'requests_per_minute': 60.0,
            }
        }

        middleware.spider_opened(self.spider)

        self.spider.logger.info.assert_called()
        # 验证配置已加载
        config = middleware.rate_manager.get_domain_config('example.com')
        self.assertEqual(config.requests_per_second, 2.0)

    def test_spider_closed(self):
        """测试爬虫结束"""
        middleware = RateLimitMiddleware(self.crawler)

        # 先产生一些请求
        request = Mock()
        request.url = 'https://example.com/path'
        request.meta = {}
        middleware.process_request(request, self.spider)

        middleware.spider_closed(self.spider)

        # 应该输出统计信息
        self.spider.logger.info.assert_called()


class TestIntegration(unittest.TestCase):
    """集成测试"""

    def test_full_workflow(self):
        """测试完整工作流程"""
        manager = RateLimitManager()

        # 设置配置
        config = RateLimitConfig(
            requests_per_second=10.0,
            requests_per_minute=100.0,
            burst_size=5,
            per_proxy_limit=True
        )
        manager.set_domain_config('api.example.com', config)

        # 模拟多个代理的请求
        proxies = ['proxy1', 'proxy2', 'proxy3']

        for i in range(20):
            proxy = proxies[i % 3]
            success, wait_time = manager.acquire('api.example.com', proxy)

            # 前5个请求每个代理都应该成功（突发容量）
            if i < 15:
                self.assertTrue(success, f"Request {i} with {proxy} should succeed")

        # 检查统计
        stats = manager.get_stats()
        self.assertGreater(stats['total_requests'], 0)

    def test_dynamic_adjustment(self):
        """测试动态调整"""
        manager = RateLimitManager()

        config = RateLimitConfig(
            requests_per_second=10.0,
            dynamic_adjust=True,
            adjust_factor=0.8
        )
        manager.set_domain_config('example.com', config)

        initial_rate = manager.get_domain_config('example.com').requests_per_second

        # 模拟多次触发限流
        for _ in range(3):
            manager.on_retry('example.com', None, 'rate_limit')

        final_rate = manager.get_domain_config('example.com').requests_per_second

        # 速率应该降低
        self.assertLess(final_rate, initial_rate)

    def test_concurrent_access(self):
        """测试并发访问"""
        manager = RateLimitManager()

        config = RateLimitConfig(
            requests_per_second=1000.0,
            burst_size=1000
        )
        manager.set_domain_config('example.com', config)

        results = []

        def make_requests():
            for _ in range(20):
                success, _ = manager.acquire('example.com')
                results.append(success)

        threads = [threading.Thread(target=make_requests) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # 所有请求都应该成功（因为速率和容量都很高）
        self.assertTrue(all(results))
        self.assertEqual(len(results), 100)


class TestEdgeCases(unittest.TestCase):
    """边界情况测试"""

    def test_zero_rate(self):
        """测试零速率"""
        bucket = TokenBucket(rate=0.0, capacity=5)

        # 消耗初始令牌
        success, _ = bucket.acquire(tokens=5)
        self.assertTrue(success)

        # 再请求应该失败（速率为0，无法再生令牌）
        success, wait_time = bucket.acquire(tokens=1)
        # 由于速率为0，返回失败和无限等待时间
        self.assertFalse(success)
        self.assertEqual(wait_time, float('inf'))

    def test_very_high_rate(self):
        """测试极高速率"""
        bucket = TokenBucket(rate=1000000.0, capacity=1000)

        # 应该能快速获取大量令牌
        for _ in range(100):
            success, _ = bucket.acquire(tokens=1)
            self.assertTrue(success)

    def test_empty_domain(self):
        """测试空域名"""
        manager = RateLimitManager()

        # 应该使用默认配置
        config = manager.get_domain_config('')
        self.assertIsNotNone(config)

    def test_none_proxy(self):
        """测试None代理"""
        manager = RateLimitManager()

        config = RateLimitConfig(per_proxy_limit=True)
        manager.set_domain_config('example.com', config)

        # None代理应该使用域名级别的桶
        success1, _ = manager.acquire('example.com', None)
        success2, _ = manager.acquire('example.com', None)

        self.assertTrue(success1)
        self.assertTrue(success2)


if __name__ == '__main__':
    unittest.main(verbosity=2)
