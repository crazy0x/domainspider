# DomainSpider 最佳实践

## 🎯 数据流推荐方案

### 方案：PostgreSQL + 文件双写（推荐）⭐

```
Scrapy 爬虫
    ├→ PostgreSQL Pipeline (实时状态 + 数据)
    └→ File Pipeline (备份 + Airflow 处理)
```

**为什么双写？**

1. **PostgreSQL** - 实时监控和查询
   - Airflow 查询任务状态
   - 实时进度追踪
   - 数据去重
   - 支持重试

2. **文件** - 数据备份和批处理
   - Airflow 批量处理数据
   - 数据备份
   - 调试方便
   - 解耦合

## 📊 配置示例

### 1. 启用双写 Pipeline

```yaml
# config/production.yaml
pipelines:
  item:
    "src.pipelines.validation.BasicValidationPipeline": 300
    "src.pipelines.postgres.PostgreSQLPipeline": 400      # 写 PG
    "src.pipelines.output.FileOutputPipeline": 800        # 写文件

# PostgreSQL 配置
postgres:
  url: "${POSTGRES_URL:postgresql://user:pass@localhost/domainspider}"
```

### 2. Airflow DAG 示例

```python
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.providers.http.operators.http import SimpleHttpOperator
from datetime import datetime, timedelta
import psycopg2

def create_task(**context):
    """创建爬取任务"""
    conn = psycopg2.connect(POSTGRES_URL)
    cursor = conn.cursor()
    
    task_id = f"haier_list_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
    cursor.execute("""
        INSERT INTO crawl_tasks (task_id, spider_name, domain, params, status)
        VALUES (%s, %s, %s, %s, 'pending')
    """, (
        task_id,
        'haier_list',
        'appliance',
        json.dumps({'level_1': 'kitchen_appliances', 'page_start': 1, 'page_end': 10})
    ))
    
    conn.commit()
    cursor.close()
    conn.close()
    
    # 传递给下游任务
    context['ti'].xcom_push(key='task_id', value=task_id)
    return task_id


def trigger_scrapyd(**context):
    """触发 Scrapyd 爬虫"""
    import requests
    
    task_id = context['ti'].xcom_pull(key='task_id')
    
    response = requests.post(
        'http://scrapyd:6800/schedule.json',
        data={
            'project': 'domainspider',
            'spider': 'haier_list',
            'task_id': task_id,
            'level_1': 'kitchen_appliances',
            'page_start': 1,
            'page_end': 10
        }
    )
    
    job_id = response.json()['jobid']
    
    # 更新任务记录
    conn = psycopg2.connect(POSTGRES_URL)
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE crawl_tasks
        SET scrapyd_job_id = %s, status = 'scheduled'
        WHERE task_id = %s
    """, (job_id, task_id))
    conn.commit()
    cursor.close()
    conn.close()


def monitor_task(**context):
    """监控任务进度"""
    import time
    
    task_id = context['ti'].xcom_pull(key='task_id')
    conn = psycopg2.connect(POSTGRES_URL)
    
    while True:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT status, items_scraped, finished_at
            FROM crawl_tasks
            WHERE task_id = %s
        """, (task_id,))
        
        result = cursor.fetchone()
        cursor.close()
        
        if not result:
            raise Exception(f"Task {task_id} not found")
        
        status, items_scraped, finished_at = result
        
        print(f"Task {task_id}: {status}, items: {items_scraped}")
        
        if status in ('completed', 'failed'):
            break
        
        time.sleep(10)
    
    conn.close()
    
    if status == 'failed':
        raise Exception(f"Task {task_id} failed")


def process_data(**context):
    """处理爬取的数据"""
    task_id = context['ti'].xcom_pull(key='task_id')
    conn = psycopg2.connect(POSTGRES_URL)
    cursor = conn.cursor()
    
    # 读取未处理的数据
    cursor.execute("""
        SELECT id, url, title, content
        FROM crawl_items
        WHERE task_id = %s AND processed = FALSE
    """, (task_id,))
    
    items = cursor.fetchall()
    
    for item_id, url, title, content in items:
        # 数据清洗和处理
        cleaned_data = clean_and_transform(url, title, content)
        
        # 存入最终数据库
        save_to_final_database(cleaned_data)
        
        # 标记为已处理
        cursor.execute("""
            UPDATE crawl_items
            SET processed = TRUE, processed_at = NOW()
            WHERE id = %s
        """, (item_id,))
    
    conn.commit()
    cursor.close()
    conn.close()
    
    print(f"Processed {len(items)} items")


# DAG 定义
with DAG(
    'haier_crawl_pipeline',
    default_args={
        'owner': 'airflow',
        'depends_on_past': False,
        'email_on_failure': True,
        'email_on_retry': False,
        'retries': 1,
        'retry_delay': timedelta(minutes=5),
    },
    description='海尔产品爬取管线',
    schedule_interval='0 2 * * *',  # 每天凌晨2点
    start_date=datetime(2023, 11, 1),
    catchup=False,
    tags=['crawl', 'haier', 'appliance'],
) as dag:
    
    # 任务1：创建爬取任务
    create = PythonOperator(
        task_id='create_task',
        python_callable=create_task,
    )
    
    # 任务2：触发 Scrapyd
    trigger = PythonOperator(
        task_id='trigger_scrapyd',
        python_callable=trigger_scrapyd,
    )
    
    # 任务3：监控进度
    monitor = PythonOperator(
        task_id='monitor_progress',
        python_callable=monitor_task,
        execution_timeout=timedelta(hours=2),
    )
    
    # 任务4：处理数据
    process = PythonOperator(
        task_id='process_data',
        python_callable=process_data,
    )
    
    # 任务流
    create >> trigger >> monitor >> process
```

## 🔍 查询示例

### 查看运行中的任务

```sql
SELECT * FROM v_task_stats
WHERE status = 'running'
ORDER BY started_at DESC;
```

### 查看今天的爬取统计

```sql
SELECT 
    spider_name,
    COUNT(*) as total_tasks,
    SUM(items_scraped) as total_items,
    AVG(duration_seconds) as avg_duration
FROM v_task_stats
WHERE DATE(created_at) = CURRENT_DATE
GROUP BY spider_name;
```

### 查看未处理的数据

```sql
SELECT 
    task_id,
    COUNT(*) as unprocessed_count
FROM crawl_items
WHERE processed = FALSE
GROUP BY task_id
ORDER BY unprocessed_count DESC;
```

## 🧹 维护任务

### 清理30天前的数据

```sql
SELECT * FROM cleanup_old_data(30);
```

### 定期清理（Airflow）

```python
# 在 Airflow 中添加清理任务
cleanup_task = PostgresOperator(
    task_id='cleanup_old_data',
    postgres_conn_id='domainspider_db',
    sql="SELECT cleanup_old_data(30);",
    dag=dag,
)
```

## 📈 监控指标

### Grafana Dashboard 查询

```sql
-- 每小时爬取量
SELECT 
    DATE_TRUNC('hour', crawl_time) as hour,
    COUNT(*) as items_count
FROM crawl_items
WHERE crawl_time > NOW() - INTERVAL '24 hours'
GROUP BY hour
ORDER BY hour;

-- 爬虫成功率
SELECT 
    spider_name,
    COUNT(CASE WHEN status = 'completed' THEN 1 END)::FLOAT / COUNT(*) * 100 as success_rate
FROM crawl_tasks
WHERE created_at > NOW() - INTERVAL '7 days'
GROUP BY spider_name;
```

## 🎯 总结

**推荐配置**：
- ✅ PostgreSQL Pipeline - 实时状态和数据
- ✅ File Pipeline - 数据备份
- ✅ Airflow 监控 PostgreSQL
- ✅ Airflow 处理文件或数据库数据

**优势**：
- 实时监控
- 数据持久化
- 支持重试
- 易于调试
- 性能良好
