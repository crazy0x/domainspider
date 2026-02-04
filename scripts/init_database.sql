-- DomainSpider 数据库初始化脚本

-- 创建数据库（如果不存在）
CREATE DATABASE IF NOT EXISTS domain_spider;

\c domain_spider;

-- 1. 任务表
CREATE TABLE IF NOT EXISTS crawl_tasks (
    -- 基础信息
    task_id VARCHAR(100) PRIMARY KEY,
    spider_name VARCHAR(50) NOT NULL,
    domain VARCHAR(50) NOT NULL,
    
    -- 任务参数（JSON）
    params JSONB NOT NULL DEFAULT '{}'::jsonb,
    
    -- 状态管理
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    
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
    error_message TEXT
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_tasks_status ON crawl_tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_spider ON crawl_tasks(spider_name);
CREATE INDEX IF NOT EXISTS idx_tasks_created ON crawl_tasks(created_at);
CREATE INDEX IF NOT EXISTS idx_tasks_domain ON crawl_tasks(domain);

-- 2. 采集数据表
CREATE TABLE IF NOT EXISTS crawl_items (
    -- 主键
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- 关联任务
    task_id VARCHAR(100) NOT NULL,
    
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
    fingerprint VARCHAR(64),
    
    -- 处理状态
    processed BOOLEAN DEFAULT FALSE,
    processed_at TIMESTAMP,
    
    -- 外键
    FOREIGN KEY (task_id) REFERENCES crawl_tasks(task_id) ON DELETE CASCADE
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_items_task ON crawl_items(task_id);
CREATE INDEX IF NOT EXISTS idx_items_fingerprint ON crawl_items(fingerprint);
CREATE INDEX IF NOT EXISTS idx_items_processed ON crawl_items(processed);
CREATE INDEX IF NOT EXISTS idx_items_crawl_time ON crawl_items(crawl_time);
CREATE INDEX IF NOT EXISTS idx_items_spider ON crawl_items(spider_name);

-- 唯一约束（同一任务内 URL 去重）
CREATE UNIQUE INDEX IF NOT EXISTS idx_items_task_fingerprint 
ON crawl_items(task_id, fingerprint);

-- 3. 任务日志表
CREATE TABLE IF NOT EXISTS crawl_logs (
    id BIGSERIAL PRIMARY KEY,
    task_id VARCHAR(100) NOT NULL,
    
    level VARCHAR(10) NOT NULL,
    message TEXT NOT NULL,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- 外键
    FOREIGN KEY (task_id) REFERENCES crawl_tasks(task_id) ON DELETE CASCADE
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_logs_task ON crawl_logs(task_id);
CREATE INDEX IF NOT EXISTS idx_logs_level ON crawl_logs(level);
CREATE INDEX IF NOT EXISTS idx_logs_created ON crawl_logs(created_at);

-- 4. 创建视图：任务统计
CREATE OR REPLACE VIEW v_task_stats AS
SELECT 
    t.task_id,
    t.spider_name,
    t.domain,
    t.status,
    t.items_scraped,
    COUNT(i.id) as items_in_db,
    COUNT(CASE WHEN i.processed THEN 1 END) as items_processed,
    t.created_at,
    t.started_at,
    t.finished_at,
    EXTRACT(EPOCH FROM (COALESCE(t.finished_at, NOW()) - t.started_at)) as duration_seconds
FROM crawl_tasks t
LEFT JOIN crawl_items i ON t.task_id = i.task_id
GROUP BY t.task_id, t.spider_name, t.domain, t.status, t.items_scraped, 
         t.created_at, t.started_at, t.finished_at;

-- 5. 创建函数：清理旧数据
CREATE OR REPLACE FUNCTION cleanup_old_data(days_to_keep INTEGER DEFAULT 30)
RETURNS TABLE(deleted_tasks INTEGER, deleted_items INTEGER) AS $$
DECLARE
    tasks_deleted INTEGER;
    items_deleted INTEGER;
BEGIN
    -- 删除旧任务（级联删除 items 和 logs）
    DELETE FROM crawl_tasks
    WHERE finished_at < NOW() - (days_to_keep || ' days')::INTERVAL
    AND status IN ('completed', 'failed');
    
    GET DIAGNOSTICS tasks_deleted = ROW_COUNT;
    
    -- 删除孤立的 items（没有对应任务的）
    DELETE FROM crawl_items
    WHERE task_id NOT IN (SELECT task_id FROM crawl_tasks);
    
    GET DIAGNOSTICS items_deleted = ROW_COUNT;
    
    RETURN QUERY SELECT tasks_deleted, items_deleted;
END;
$$ LANGUAGE plpgsql;

-- 6. 插入示例数据（可选）
-- INSERT INTO crawl_tasks (task_id, spider_name, domain, params, status)
-- VALUES ('test_task_001', 'haier_list', 'appliance', '{"level_1": "kitchen_appliances"}'::jsonb, 'pending');

-- 完成
SELECT 'Database initialized successfully!' as message;
