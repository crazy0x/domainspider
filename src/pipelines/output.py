"""
数据输出管道
输出数据供 Airflow 处理
"""
import json
import os
from datetime import datetime
from itemadapter import ItemAdapter


class FileOutputPipeline:
    """
    文件输出管道
    将数据输出为 JSONL 格式，供 Airflow 处理
    """
    
    def __init__(self, output_dir, output_format='jsonlines'):
        self.output_dir = output_dir
        self.output_format = output_format
        self.files = {}
        
        # 确保输出目录存在
        os.makedirs(output_dir, exist_ok=True)
    
    @classmethod
    def from_crawler(cls, crawler):
        settings = crawler.settings
        return cls(
            output_dir=settings.get('OUTPUT_DIR', '/tmp/scrapy_output'),
            output_format=settings.get('OUTPUT_FORMAT', 'jsonlines')
        )
    
    def open_spider(self, spider):
        """爬虫开始时创建输出文件"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"{spider.name}_{timestamp}.jsonl"
        filepath = os.path.join(self.output_dir, filename)
        
        self.files[spider.name] = open(filepath, 'w', encoding='utf-8')
        spider.logger.info(f"Output file created: {filepath}")
        
        # 记录输出文件路径到 spider meta
        spider.output_file = filepath
    
    def close_spider(self, spider):
        """爬虫结束时关闭文件"""
        if spider.name in self.files:
            self.files[spider.name].close()
            spider.logger.info(f"Output file closed: {spider.output_file}")
            
            # 记录文件信息到统计
            file_size = os.path.getsize(spider.output_file)
            spider.crawler.stats.set_value('output/file_path', spider.output_file)
            spider.crawler.stats.set_value('output/file_size', file_size)
    
    def process_item(self, item, spider):
        """处理单个 item"""
        if spider.name not in self.files:
            spider.logger.error(f"No output file for spider: {spider.name}")
            return item
        
        # 转换为字典
        item_dict = ItemAdapter(item).asdict()
        
        # 写入文件
        line = json.dumps(item_dict, ensure_ascii=False, separators=(',', ':'))
        self.files[spider.name].write(line + '\n')
        self.files[spider.name].flush()  # 立即写入磁盘
        
        spider.logger.debug(f"Item written to output file: {item_dict.get('url', 'unknown')}")
        return item


class JsonOutputPipeline:
    """
    JSON 输出管道
    将所有数据收集后输出为单个 JSON 文件
    """
    
    def __init__(self, output_dir):
        self.output_dir = output_dir
        self.items = {}
        
        os.makedirs(output_dir, exist_ok=True)
    
    @classmethod
    def from_crawler(cls, crawler):
        settings = crawler.settings
        return cls(
            output_dir=settings.get('OUTPUT_DIR', '/tmp/scrapy_output')
        )
    
    def open_spider(self, spider):
        """初始化 items 列表"""
        self.items[spider.name] = []
    
    def close_spider(self, spider):
        """爬虫结束时输出 JSON 文件"""
        if spider.name not in self.items:
            return
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"{spider.name}_{timestamp}.json"
        filepath = os.path.join(self.output_dir, filename)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(self.items[spider.name], f, ensure_ascii=False, indent=2)
        
        spider.logger.info(f"JSON output file created: {filepath}")
        spider.output_file = filepath
        
        # 记录统计
        spider.crawler.stats.set_value('output/file_path', filepath)
        spider.crawler.stats.set_value('output/items_count', len(self.items[spider.name]))
    
    def process_item(self, item, spider):
        """收集 item"""
        if spider.name not in self.items:
            self.items[spider.name] = []
        
        item_dict = ItemAdapter(item).asdict()
        self.items[spider.name].append(item_dict)
        
        return item


class CSVOutputPipeline:
    """
    CSV 输出管道
    输出为 CSV 格式
    """
    
    def __init__(self, output_dir):
        self.output_dir = output_dir
        self.files = {}
        self.writers = {}
        
        os.makedirs(output_dir, exist_ok=True)
    
    @classmethod
    def from_crawler(cls, crawler):
        settings = crawler.settings
        return cls(
            output_dir=settings.get('OUTPUT_DIR', '/tmp/scrapy_output')
        )
    
    def open_spider(self, spider):
        """创建 CSV 文件"""
        import csv
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"{spider.name}_{timestamp}.csv"
        filepath = os.path.join(self.output_dir, filename)
        
        self.files[spider.name] = open(filepath, 'w', newline='', encoding='utf-8')
        self.writers[spider.name] = csv.writer(self.files[spider.name])
        
        spider.logger.info(f"CSV output file created: {filepath}")
        spider.output_file = filepath
        
        # 写入表头（第一个 item 时写入）
        self.header_written = False
    
    def close_spider(self, spider):
        """关闭 CSV 文件"""
        if spider.name in self.files:
            self.files[spider.name].close()
            spider.logger.info(f"CSV output file closed: {spider.output_file}")
    
    def process_item(self, item, spider):
        """写入 CSV"""
        if spider.name not in self.writers:
            return item
        
        item_dict = ItemAdapter(item).asdict()
        
        # 写入表头
        if not self.header_written:
            self.writers[spider.name].writerow(item_dict.keys())
            self.header_written = True
        
        # 写入数据行
        self.writers[spider.name].writerow(item_dict.values())
        self.files[spider.name].flush()
        
        return item
