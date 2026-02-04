"""
基础数据模型定义
"""
import scrapy
from itemadapter import ItemAdapter
from datetime import datetime
import uuid


class BaseItem(scrapy.Item):
    """
    所有 Item 的基类
    包含通用字段和方法
    """
    # 通用字段
    id = scrapy.Field()                    # 唯一标识
    url = scrapy.Field()                   # 源URL
    title = scrapy.Field()                 # 标题
    content = scrapy.Field()               # 内容
    item_type = scrapy.Field()             # Item 类型（如 product_link, product_detail）
    
    # 元数据字段
    spider_name = scrapy.Field()           # 爬虫名称
    domain = scrapy.Field()                # 领域分类
    crawl_time = scrapy.Field()            # 采集时间
    task_id = scrapy.Field()               # 任务ID
    
    # 状态字段
    status = scrapy.Field()                # 状态：raw, processed, error
    fingerprint = scrapy.Field()           # 数据指纹
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 自动设置基础字段
        self.setdefault('id', str(uuid.uuid4()))
        self.setdefault('crawl_time', datetime.now().isoformat())
        self.setdefault('status', 'raw')
    
    def to_dict(self):
        """转换为字典"""
        return ItemAdapter(self).asdict()
    
    def validate(self):
        """基础验证"""
        adapter = ItemAdapter(self)
        
        # 必填字段检查
        required_fields = ['url', 'spider_name']
        for field in required_fields:
            if not adapter.get(field):
                raise ValueError(f"Required field '{field}' is missing")
        
        return True
