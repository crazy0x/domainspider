"""
数据验证管道
"""
from itemadapter import ItemAdapter
from scrapy.exceptions import DropItem


class BasicValidationPipeline:
    """
    基础数据验证管道
    只做最基本的验证，复杂验证留给 Airflow
    """
    
    def process_item(self, item, spider):
        """验证 item"""
        adapter = ItemAdapter(item)
        
        # 基础字段验证
        if not adapter.get('url'):
            raise DropItem(f"Missing URL in item: {item}")
        
        # URL 格式验证
        url = adapter.get('url')
        if not self.is_valid_url(url):
            raise DropItem(f"Invalid URL format: {url}")
        
        # 内容长度验证（防止空内容）
        content = adapter.get('content', '')
        if isinstance(content, str) and len(content.strip()) == 0:
            spider.logger.warning(f"Empty content for URL: {url}")
        
        # 标题验证
        title = adapter.get('title', '')
        if isinstance(title, str) and len(title.strip()) == 0:
            spider.logger.warning(f"Empty title for URL: {url}")
        
        # 设置验证状态
        adapter['status'] = 'validated'
        
        spider.logger.debug(f"Item validated: {url}")
        return item
    
    def is_valid_url(self, url):
        """验证 URL 格式"""
        if not url or not isinstance(url, str):
            return False
        
        url = url.strip()
        return url.startswith(('http://', 'https://')) and len(url) > 10
