"""
DomainSpider 基础爬虫类
采用最小化抽象 + 可选 Mixin 的设计理念
"""
import scrapy
import time
from datetime import datetime
from urllib.parse import urljoin, urlparse
from typing import Optional, Dict, Any

from src.items.base import BaseItem


class BaseSpider(scrapy.Spider):
    """
    最小化基础爬虫类
    
    只提供必要的通用功能：
    1. 参数标准化处理
    2. 任务ID生成
    3. Item创建辅助
    4. 基础统计
    
    不强制任何抽象方法，子类根据需要自由实现
    """
    
    # 领域分类，子类设置（可选）
    domain = None
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # 标准化参数处理（都是可选的）
        self.mode = getattr(self, 'mode', 'incremental')
        self.date = getattr(self, 'date', datetime.now().strftime('%Y-%m-%d'))
        self.page_start = int(getattr(self, 'page_start', 1))
        self.page_end = int(getattr(self, 'page_end', 100))
        
        # 生成任务 ID
        timestamp = int(time.time())
        self.task_id = getattr(self, 'task_id', f"{self.name}_{self.date}_{timestamp}")
        
        # 基础日志
        self.logger.info(f"Spider initialized: {self.name}")
        self.logger.info(f"Task ID: {self.task_id}")
        self.logger.info(f"Domain: {self.domain}")
    
    def create_item(self, **kwargs) -> BaseItem:
        """
        创建标准 Item
        
        自动填充 spider_name, domain, task_id, crawl_time
        """
        item = BaseItem()
        
        # 自动设置基础字段
        item['spider_name'] = self.name
        item['domain'] = self.domain
        item['task_id'] = self.task_id
        
        # 设置传入的字段
        for key, value in kwargs.items():
            item[key] = value
        
        return item
    
    def closed(self, reason):
        """爬虫关闭时记录统计信息"""
        self.logger.info(f"Spider {self.name} closed: {reason}")
        
        stats = self.crawler.stats
        self.logger.info(f"Items scraped: {stats.get_value('item_scraped_count', 0)}")
        self.logger.info(f"Requests: {stats.get_value('downloader/request_count', 0)}")
        self.logger.info(f"Responses: {stats.get_value('downloader/response_count', 0)}")


# ============================================================================
# 可选的 Mixin 类 - 按需使用
# ============================================================================

class TextExtractorMixin:
    """文本提取工具 Mixin"""
    
    def extract_text(self, selector, default=''):
        """安全提取单个文本"""
        if selector:
            text = selector.get()
            return text.strip() if text else default
        return default
    
    def extract_texts(self, selector):
        """提取多个文本"""
        if selector:
            return [text.strip() for text in selector.getall() if text.strip()]
        return []
    
    def clean_text(self, text: str) -> str:
        """清理文本（去除多余空白）"""
        if not text:
            return ""
        return ' '.join(text.split())


class URLHelperMixin:
    """URL 处理工具 Mixin"""
    
    def build_absolute_url(self, response, url):
        """构建绝对URL"""
        if not url:
            return None
        return urljoin(response.url, url)
    
    def is_valid_url(self, url):
        """验证URL有效性"""
        if not url:
            return False
        parsed = urlparse(url)
        return bool(parsed.netloc and parsed.scheme)


# ============================================================================
# 使用示例（仅供参考）
# ============================================================================

# 示例1：最简单的爬虫（只用 BaseSpider）
class MinimalSpider(BaseSpider):
    name = 'minimal'
    domain = 'test'
    
    def start_requests(self):
        yield scrapy.Request('https://example.com', callback=self.parse)
    
    def parse(self, response):
        yield self.create_item(
            url=response.url,
            title='Test',
            content={'data': 'example'}
        )


# 示例2：使用 Mixin 的爬虫
class MySpider(BaseSpider, TextExtractorMixin, URLHelperMixin):
    name = 'my_spider'
    domain = 'test'
    
    def parse(self, response):
        # 使用 TextExtractorMixin 的方法
        title = self.extract_text(response.css('h1::text'))
        
        # 使用 URLHelperMixin 的方法
        detail_url = self.build_absolute_url(response, '/product/123')
        
        yield self.create_item(url=response.url, title=title)


# 示例3：Playwright 爬虫（完全自定义翻页逻辑）
class MyPlaywrightSpider(BaseSpider, URLHelperMixin):
    name = 'my_pw'
    domain = 'test'
    
    custom_settings = {
        'DOWNLOAD_HANDLERS': {
            "http": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
        }
    }
    
    def start_requests(self):
        yield scrapy.Request(
            'https://example.com',
            meta={'playwright': True},
            callback=self.parse
        )
    
    async def parse(self, response):
        # 完全自定义的翻页逻辑
        page = response.meta['playwright_page']
        
        # 提取数据
        items = response.css('.item')
        for item in items:
            yield self.create_item(
                url=response.url,
                title=self.extract_text(item.css('h2::text'))
            )
        
        # 自定义翻页：点击下一页按钮
        next_button = await page.query_selector('a.next')
        if next_button:
            await next_button.click()
            await page.wait_for_selector('.item')
            # 继续处理...
        yield self.create_item(url=response.url, title='...')
