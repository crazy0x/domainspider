"""
增量爬取工具
用于支持增量更新和去重
"""
import psycopg2
import hashlib
from typing import List, Set


class IncrementalHelper:
    """增量爬取辅助类"""
    
    def __init__(self, postgres_url: str):
        self.postgres_url = postgres_url
        self.conn = None
    
    def connect(self):
        """连接数据库"""
        if not self.conn:
            self.conn = psycopg2.connect(self.postgres_url)
    
    def close(self):
        """关闭连接"""
        if self.conn:
            self.conn.close()
            self.conn = None
    
    def get_existing_urls(self, spider_name: str, days: int = 30) -> Set[str]:
        """
        获取已爬取的URL集合
        
        Args:
            spider_name: 爬虫名称
            days: 查询最近N天的数据
        
        Returns:
            URL集合
        """
        self.connect()
        cursor = self.conn.cursor()
        
        cursor.execute("""
            SELECT DISTINCT url
            FROM crawl_items
            WHERE spider_name = %s
              AND crawl_time > NOW() - INTERVAL '%s days'
        """, (spider_name, days))
        
        urls = {row[0] for row in cursor.fetchall()}
        cursor.close()
        
        return urls
    
    def get_urls_to_update(self, spider_name: str, all_urls: List[str], 
                          days_threshold: int = 7) -> List[str]:
        """
        获取需要更新的URL列表
        
        Args:
            spider_name: 爬虫名称
            all_urls: 所有URL列表
            days_threshold: 超过N天未更新的URL需要重新爬取
        
        Returns:
            需要爬取的URL列表
        """
        self.connect()
        cursor = self.conn.cursor()
        
        # 计算URL指纹
        url_fingerprints = {
            self._calculate_fingerprint(url): url 
            for url in all_urls
        }
        
        # 查询已存在且最近更新的URL
        placeholders = ','.join(['%s'] * len(url_fingerprints))
        cursor.execute(f"""
            SELECT fingerprint, MAX(crawl_time) as last_crawl
            FROM crawl_items
            WHERE spider_name = %s
              AND fingerprint IN ({placeholders})
            GROUP BY fingerprint
        """, (spider_name, *url_fingerprints.keys()))
        
        # 找出需要更新的URL
        recent_fingerprints = set()
        for fingerprint, last_crawl in cursor.fetchall():
            # 如果最近更新过，跳过
            from datetime import datetime, timedelta
            if last_crawl and (datetime.now() - last_crawl).days < days_threshold:
                recent_fingerprints.add(fingerprint)
        
        cursor.close()
        
        # 返回需要爬取的URL
        urls_to_crawl = [
            url for fp, url in url_fingerprints.items()
            if fp not in recent_fingerprints
        ]
        
        return urls_to_crawl
    
    def is_url_exists(self, url: str, spider_name: str = None) -> bool:
        """
        检查URL是否已存在
        
        Args:
            url: URL
            spider_name: 爬虫名称（可选）
        
        Returns:
            是否存在
        """
        self.connect()
        cursor = self.conn.cursor()
        
        fingerprint = self._calculate_fingerprint(url)
        
        if spider_name:
            cursor.execute("""
                SELECT 1 FROM crawl_items
                WHERE fingerprint = %s AND spider_name = %s
                LIMIT 1
            """, (fingerprint, spider_name))
        else:
            cursor.execute("""
                SELECT 1 FROM crawl_items
                WHERE fingerprint = %s
                LIMIT 1
            """, (fingerprint,))
        
        exists = cursor.fetchone() is not None
        cursor.close()
        
        return exists
    
    def get_stale_urls(self, spider_name: str, days: int = 30) -> List[dict]:
        """
        获取过期的URL（超过N天未更新）
        
        Args:
            spider_name: 爬虫名称
            days: 天数阈值
        
        Returns:
            过期URL列表，包含url和最后爬取时间
        """
        self.connect()
        cursor = self.conn.cursor()
        
        cursor.execute("""
            SELECT url, MAX(crawl_time) as last_crawl
            FROM crawl_items
            WHERE spider_name = %s
            GROUP BY url
            HAVING MAX(crawl_time) < NOW() - INTERVAL '%s days'
            ORDER BY last_crawl ASC
        """, (spider_name, days))
        
        stale_urls = [
            {'url': row[0], 'last_crawl': row[1]}
            for row in cursor.fetchall()
        ]
        
        cursor.close()
        
        return stale_urls
    
    def _calculate_fingerprint(self, url: str) -> str:
        """计算URL指纹"""
        return hashlib.sha256(url.encode('utf-8')).hexdigest()
    
    def __enter__(self):
        """上下文管理器"""
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器"""
        self.close()


# 使用示例
"""
from src.utils.incremental import IncrementalHelper

# 1. 检查URL是否存在
with IncrementalHelper(POSTGRES_URL) as helper:
    if helper.is_url_exists(url, 'haier'):
        print("URL already crawled, skipping...")

# 2. 获取需要更新的URL
with IncrementalHelper(POSTGRES_URL) as helper:
    all_urls = ['url1', 'url2', 'url3']
    urls_to_crawl = helper.get_urls_to_update('haier', all_urls, days_threshold=7)
    print(f"Need to crawl {len(urls_to_crawl)} URLs")

# 3. 获取过期URL
with IncrementalHelper(POSTGRES_URL) as helper:
    stale_urls = helper.get_stale_urls('haier', days=30)
    print(f"Found {len(stale_urls)} stale URLs")
"""
