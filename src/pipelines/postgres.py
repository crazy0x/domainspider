"""
PostgreSQL 数据管道
将爬取数据直接写入 PostgreSQL
"""
import psycopg2
from psycopg2.extras import Json
from itemadapter import ItemAdapter
from datetime import datetime
import hashlib


class PostgreSQLPipeline:
    """
    PostgreSQL 输出管道
    
    功能：
    1. 写入爬取数据到 crawl_items 表
    2. 更新任务进度到 crawl_tasks 表
    3. 自动去重（基于 URL fingerprint）
    """
    
    def __init__(self, postgres_url):
        self.postgres_url = postgres_url
        self.conn = None
        self.cursor = None
    
    @classmethod
    def from_crawler(cls, crawler):
        return cls(
            postgres_url=crawler.settings.get('POSTGRES_URL', 
                'postgresql://localhost/domainspider')
        )
    
    def open_spider(self, spider):
        """爬虫开始时连接数据库"""
        try:
            self.conn = psycopg2.connect(self.postgres_url)
            self.cursor = self.conn.cursor()
            spider.logger.info("PostgreSQL connection established")
            
            # 确保任务记录存在
            self._ensure_task_exists(spider)
            
        except Exception as e:
            spider.logger.error(f"Failed to connect to PostgreSQL: {e}")
            raise
    
    def close_spider(self, spider):
        """爬虫结束时关闭连接"""
        if self.conn:
            # 更新任务状态为完成（在关闭 cursor 之前）
            self._update_task_status(spider, 'completed')
            
            if self.cursor:
                self.cursor.close()
            
            self.conn.close()
            spider.logger.info("PostgreSQL connection closed")
    
    def process_item(self, item, spider):
        """处理单个 item"""
        try:
            adapter = ItemAdapter(item)
            
            # 计算 URL 指纹
            fingerprint = self._calculate_fingerprint(adapter.get('url'))
            
            # 插入数据（如果不存在）
            self.cursor.execute("""
                INSERT INTO crawl_items (
                    task_id, spider_name, domain, item_type,
                    url, title, content, fingerprint, crawl_time
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s
                )
                ON CONFLICT (task_id, fingerprint) DO NOTHING
                RETURNING id
            """, (
                getattr(spider, 'task_id', 'unknown'),
                adapter.get('spider_name'),
                adapter.get('domain'),
                adapter.get('item_type'),
                adapter.get('url'),
                adapter.get('title'),
                Json(adapter.get('content', {})),
                fingerprint,
                adapter.get('crawl_time', datetime.now())
            ))
            
            result = self.cursor.fetchone()
            
            if result:
                # 新插入的数据，更新任务进度
                self._update_task_progress(spider)
                spider.logger.debug(f"Item saved to PostgreSQL: {adapter.get('url')}")
            else:
                spider.logger.debug(f"Item already exists (skipped): {adapter.get('url')}")
            
            self.conn.commit()
            
        except Exception as e:
            self.conn.rollback()
            spider.logger.error(f"Error saving item to PostgreSQL: {e}")
            spider.logger.error(f"Item: {adapter.asdict()}")
        
        return item
    
    def _ensure_task_exists(self, spider):
        """确保任务记录存在"""
        task_id = getattr(spider, 'task_id', 'unknown')
        
        self.cursor.execute("""
            INSERT INTO crawl_tasks (
                task_id, spider_name, domain, status, params, created_at, started_at
            ) VALUES (
                %s, %s, %s, 'running', %s, NOW(), NOW()
            )
            ON CONFLICT (task_id) DO UPDATE
            SET status = 'running', started_at = COALESCE(crawl_tasks.started_at, NOW())
        """, (
            task_id,
            spider.name,
            getattr(spider, 'domain', 'unknown'),
            Json(self._get_spider_params(spider))
        ))
        
        self.conn.commit()
    
    def _update_task_progress(self, spider):
        """更新任务进度"""
        task_id = getattr(spider, 'task_id', 'unknown')
        
        self.cursor.execute("""
            UPDATE crawl_tasks
            SET items_scraped = items_scraped + 1
            WHERE task_id = %s
        """, (task_id,))
    
    def _update_task_status(self, spider, status):
        """更新任务状态"""
        task_id = getattr(spider, 'task_id', 'unknown')
        
        # 获取统计信息
        stats = spider.crawler.stats.get_stats()
        
        # 创建新的 cursor 用于更新
        cursor = self.conn.cursor()
        cursor.execute("""
            UPDATE crawl_tasks
            SET 
                status = %s,
                finished_at = NOW(),
                output_file = %s
            WHERE task_id = %s
        """, (
            status,
            stats.get('output/file_path'),
            task_id
        ))
        
        self.conn.commit()
        cursor.close()
    
    def _get_spider_params(self, spider):
        """获取爬虫参数"""
        params = {}
        
        # 常见参数
        for attr in ['level_1', 'level_2', 'page_start', 'page_end', 
                     'task_type', 'product_urls']:
            if hasattr(spider, attr):
                params[attr] = getattr(spider, attr)
        
        return params
    
    def _calculate_fingerprint(self, url):
        """计算 URL 指纹"""
        if not url:
            return None
        return hashlib.sha256(url.encode('utf-8')).hexdigest()


class PostgreSQLTaskPipeline:
    """
    PostgreSQL 任务管道
    
    只负责更新任务状态，不保存数据
    适合与文件输出配合使用
    """
    
    def __init__(self, postgres_url):
        self.postgres_url = postgres_url
        self.conn = None
    
    @classmethod
    def from_crawler(cls, crawler):
        return cls(
            postgres_url=crawler.settings.get('POSTGRES_URL')
        )
    
    def open_spider(self, spider):
        """连接数据库并更新任务状态"""
        self.conn = psycopg2.connect(self.postgres_url)
        cursor = self.conn.cursor()
        
        task_id = getattr(spider, 'task_id', 'unknown')
        
        cursor.execute("""
            UPDATE crawl_tasks
            SET status = 'running', started_at = NOW()
            WHERE task_id = %s
        """, (task_id,))
        
        self.conn.commit()
        cursor.close()
    
    def close_spider(self, spider):
        """更新任务完成状态"""
        cursor = self.conn.cursor()
        task_id = getattr(spider, 'task_id', 'unknown')
        stats = spider.crawler.stats.get_stats()
        
        cursor.execute("""
            UPDATE crawl_tasks
            SET 
                status = 'completed',
                finished_at = NOW(),
                items_scraped = %s,
                output_file = %s
            WHERE task_id = %s
        """, (
            stats.get('item_scraped_count', 0),
            stats.get('output/file_path'),
            task_id
        ))
        
        self.conn.commit()
        cursor.close()
        self.conn.close()
    
    def process_item(self, item, spider):
        """不处理 item，直接返回"""
        return item
