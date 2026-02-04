# DomainSpider 数据库设计

## 📊 核心表结构

### 1. 任务表 (crawl_tasks)

**用途**：Airflow 和 Scrapyd 之间的桥梁

```sql
CREATE TABLE crawl_tasks (
    -- 基础信息
    task_id VARCHAR(100) PRIMARY KEY,
    spider_name VARCHAR(50) NOT NULL,
    domain VARCHAR(50) NOT NULL,
    
    -- 任务参数（JSON）
    params JSONB NOT NULL,
    
    -- 状态管理
    status VARCHAR(20) NOT NULL,  -- pending, running, completed, failed
    
    -- Scrapyd 信息
    scrapyd_job_id VARCHAR(100),
    scrapyd_node VARCHAR(100),
    
    -- 进度信息
    items_scraped INTEGER DEFAULT 0,
    items_total INTEGER,
    progress_percent DECIMAL(5,2),
    
    -- 时间信息
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP,
    finished_at TIMESTAMP,
    
    -- 结果信息
    output_file VARCHAR(500),
    error_message TEXT,
    
    -- 索引
    INDEX idx_status (status),
    INDEX idx_spider (spider_name),
    INDEX idx_created (created_at)
);
```

### 2. 采集数据表 (crawl_items)

**用途**：存储爬取的原始数据

```sql
CREATE TABLE crawl_items (
    -- 主键
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- 关联任务
    task_id VARCHAR(100) NOT NULL REFERENCES crawl_tasks(task_id),
    
    -- 基础信息
    spider_name VARCHAR(50) NOT NULL,
    domain VARCHAR(50) NOT NULL,
    item_type VARCHAR(50),
    
    -- URL 和标题
    url TEXT NOT NULL,
    title TEXT,
    
    -- 内容（JSON）
    content JSONB,
    
    -- 元数据
    crawl_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    fingerprint VARCHAR(64),  -- URL 指纹，用于去重
    
    -- 处理状态
    processed BOOLEAN DEFAULT FALSE,
    processed_at TIMESTAMP,
    
    -- 索引
    INDEX idx_task (task_id),
    INDEX idx_url_hash (fingerprint),
    INDEX idx_processed (processed),
    INDEX idx_crawl_time (crawl_time),
    UNIQUE (task_id, fingerprint)  -- 同一任务内去重
);
```

### 3. 任务日志表 (crawl_logs)

**用途**：记录任务执行日志

```sql
CREATE TABLE crawl_logs (
    id BIGSERIAL PRIMARY KEY,
    task_id VARCHAR(100) NOT NULL REFERENCES crawl_tasks(task_id),
    
    level VARCHAR(10) NOT NULL,  -- INFO, WARNING, ERROR
    message TEXT NOT NULL,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    INDEX idx_task (task_id),
    INDEX idx_level (level)
);
```

## 🔄 数据流

### 阶段 1：Airflow 创建任务

```python
# Airflow DAG
task_id = create_crawl_task(
    spider_name='haier_list',
    domain='appliance',
    params={
        'level_1': 'kitchen_appliances',
        'page_start': 1,
        'page_end': 10
    }
)
# → INSERT INTO crawl_tasks (status='pending')
```

### 阶段 2：触发 Scrapyd

```python
# Airflow 调用 Scrapyd
response = requests.post(
    'http://scrapyd:6800/schedule.json',
    data={
        'project': 'domainspider',
        'spider': 'haier_list',
        'task_id': task_id,  # 传递 task_id
        **params
    }
)

# 更新任务状态
# → UPDATE crawl_tasks SET 
#     status='running', 
#     scrapyd_job_id=response['jobid'],
#     started_at=NOW()
```

### 阶段 3：Scrapy 写入数据

```python
# Scrapy Pipeline
class PostgreSQLPipeline:
    def process_item(self, item, spider):
        # 写入数据表
        conn.execute("""
            INSERT INTO crawl_items 
            (task_id, url, title, content, ...)
            VALUES (%s, %s, %s, %s, ...)
        """, (spider.task_id, item['url'], ...))
        
        # 更新任务进度
        conn.execute("""
            UPDATE crawl_tasks 
            SET items_scraped = items_scraped + 1
            WHERE task_id = %s
        """, (spider.task_id,))
```

### 阶段 4：Airflow 监控和处理

```python
# Airflow 监控任务
while True:
    task = get_task_status(task_id)
    
    if task['status'] == 'completed':
        # 读取数据进行后续处理
        items = get_crawl_items(task_id, processed=False)
        
        for item in items:
            # 数据清洗、转换
            cleaned_data = clean_data(item)
            
            # 存入最终数据库
            save_to_final_db(cleaned_data)
            
            # 标记为已处理
            mark_as_processed(item['id'])
        
        break
    
    time.sleep(10)
```

## 📈 查询示例

### 查看任务进度

```sql
SELECT 
    task_id,
    spider_name,
    status,
    items_scraped,
    items_total,
    ROUND(items_scraped::DECIMAL / NULLIF(items_total, 0) * 100, 2) as progress,
    started_at,
    NOW() - started_at as duration
FROM crawl_tasks
WHERE status = 'running';
```

### 查看爬取数据

```sql
SELECT 
    t.task_id,
    t.spider_name,
    COUNT(i.id) as total_items,
    COUNT(CASE WHEN i.processed THEN 1 END) as processed_items
FROM crawl_tasks t
LEFT JOIN crawl_items i ON t.task_id = i.task_id
WHERE t.status = 'completed'
GROUP BY t.task_id, t.spider_name;
```

### 查看失败任务

```sql
SELECT 
    task_id,
    spider_name,
    error_message,
    finished_at
FROM crawl_tasks
WHERE status = 'failed'
ORDER BY finished_at DESC
LIMIT 10;
```

## 🎯 优势

1. **实时监控** - 随时查询任务进度
2. **数据持久化** - 不依赖临时文件
3. **易于追踪** - 完整的任务生命周期
4. **支持重试** - 失败任务可以重新处理
5. **数据去重** - 基于 fingerprint 去重
6. **分离关注点** - 原始数据 vs 处理后数据
