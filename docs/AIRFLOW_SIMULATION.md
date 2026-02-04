# Airflow 工作流模拟

在实际部署 Airflow 之前，可以使用这些脚本模拟 Airflow DAG 的完整工作流。

## 🎯 模拟的工作流

```
1. 创建任务记录 (INSERT INTO crawl_tasks)
   ↓
2. 调度 Scrapyd 爬虫 (POST /schedule.json)
   ↓
3. 监控任务进度 (SELECT FROM crawl_tasks)
   ↓
4. 查看爬取结果 (SELECT FROM crawl_items)
   ↓
5. 处理数据 (UPDATE crawl_items SET processed=TRUE)
   ↓
6. 任务总结
```

## 📝 使用方法

### 方法 1: Python 脚本（推荐）⭐

```bash
# 运行完整工作流模拟
python scripts/simulate_airflow.py
```

**输出示例**：
```
============================================================
🚀 模拟 Airflow DAG 工作流
============================================================

📡 连接数据库...
✅ 数据库连接成功

============================================================
步骤 1: 创建爬取任务记录
============================================================
任务 ID: haier_list_20231125_213000
✅ 任务记录已创建

============================================================
步骤 2: 调度 Scrapyd 爬虫
============================================================
✅ Scrapyd 正在运行
正在调度爬虫...
✅ 爬虫已调度
Job ID: abc123def456...

============================================================
步骤 3: 监控任务进度
============================================================
⏳ 状态: running | 已爬取: 45 条 | 耗时: 23s
✅ 任务完成！
   已爬取: 45 条数据
   耗时: 25 秒

============================================================
步骤 4: 查看爬取结果
============================================================
总数据: 45 条
已处理: 0 条
未处理: 45 条

最新爬取的 5 条数据:
1. 14套嵌入式全自动洗碗机 EYBW14586BBU1
   https://www.haier.com/kitchen_appliances/xwj/20241106_252178.shtml
...

============================================================
步骤 5: 模拟数据处理
============================================================
未处理数据: 45 条
正在处理数据...
✅ 已处理 45 条数据

============================================================
任务完成总结
============================================================
任务 ID: haier_list_20231125_213000
爬虫: haier_list
状态: completed
爬取数据: 45 条
耗时: 25 秒
输出文件: /tmp/scrapy_output/haier_list_20231125_213000.jsonl

✅ 完整工作流执行成功！
```

### 方法 2: Bash 脚本

```bash
# 完整工作流（带详细输出）
./scripts/simulate_airflow.sh

# 快速测试（简化版）
./scripts/test_workflow.sh

# 指定爬虫和页数
./scripts/test_workflow.sh haier_list 5
```

### 方法 3: 手动 curl 命令

#### 1. 创建任务记录

```bash
TASK_ID="haier_list_$(date +%Y%m%d_%H%M%S)"

psql -h 192.168.50.153 -p 5432 -U postgres -d domain_spider -c "
INSERT INTO crawl_tasks (task_id, spider_name, domain, params, status)
VALUES ('$TASK_ID', 'haier_list', 'appliance', 
        '{\"level_1\": \"kitchen_appliances\", \"page_start\": 1, \"page_end\": 3}'::jsonb, 
        'pending')
"
```

#### 2. 调度爬虫

```bash
curl http://localhost:6800/schedule.json \
  -d project=domainspider \
  -d spider=haier_list \
  -d task_id=$TASK_ID \
  -d level_1=kitchen_appliances \
  -d page_start=1 \
  -d page_end=3
```

**响应**：
```json
{
  "status": "ok",
  "jobid": "abc123def456...",
  "node_name": "node-name"
}
```

#### 3. 查询任务状态

```bash
# 查询数据库
psql -h 192.168.50.153 -p 5432 -U postgres -d domain_spider -c "
SELECT task_id, status, items_scraped, 
       EXTRACT(EPOCH FROM (NOW() - started_at))::int as duration
FROM crawl_tasks 
WHERE task_id = '$TASK_ID'
"

# 查询 Scrapyd
curl http://localhost:6800/listjobs.json?project=domainspider
```

#### 4. 查看爬取数据

```bash
psql -h 192.168.50.153 -p 5432 -U postgres -d domain_spider -c "
SELECT COUNT(*) as total, 
       COUNT(CASE WHEN processed THEN 1 END) as processed
FROM crawl_items 
WHERE task_id = '$TASK_ID'
"
```

#### 5. 处理数据

```bash
psql -h 192.168.50.153 -p 5432 -U postgres -d domain_spider -c "
UPDATE crawl_items 
SET processed = TRUE, processed_at = NOW()
WHERE task_id = '$TASK_ID' AND processed = FALSE
"
```

## 🔍 查看结果

### 查看数据库状态

```bash
python scripts/check_db.py
```

### 查看 Scrapyd 日志

```bash
# 列出所有日志
ls -lh logs/domainspider/haier_list/

# 查看最新日志
tail -f logs/domainspider/haier_list/*.log
```

### 查看输出文件

```bash
# 列出输出文件
ls -lh /tmp/scrapy_output/

# 查看文件内容
cat /tmp/scrapy_output/haier_list_*.jsonl | jq .
```

## 📊 Scrapyd API 完整示例

### 查看服务状态

```bash
curl http://localhost:6800/daemonstatus.json
```

### 列出所有爬虫

```bash
curl http://localhost:6800/listspiders.json?project=domainspider
```

### 查看任务列表

```bash
curl http://localhost:6800/listjobs.json?project=domainspider | jq .
```

**响应**：
```json
{
  "status": "ok",
  "pending": [],
  "running": [
    {
      "id": "abc123...",
      "spider": "haier_list",
      "start_time": "2023-11-25 21:30:00"
    }
  ],
  "finished": [
    {
      "id": "def456...",
      "spider": "haier_list",
      "start_time": "2023-11-25 20:00:00",
      "end_time": "2023-11-25 20:05:00"
    }
  ]
}
```

### 取消任务

```bash
curl http://localhost:6800/cancel.json \
  -d project=domainspider \
  -d job=abc123def456...
```

## 🎯 与真实 Airflow 的对应关系

| 模拟脚本步骤 | Airflow DAG 任务 | 说明 |
|------------|----------------|------|
| 步骤 1: 创建任务记录 | `PythonOperator` | 在数据库中创建任务 |
| 步骤 2: 调度爬虫 | `SimpleHttpOperator` | 调用 Scrapyd API |
| 步骤 3: 监控进度 | `PythonSensor` | 轮询数据库检查状态 |
| 步骤 4: 查看结果 | `PostgresOperator` | 查询爬取结果 |
| 步骤 5: 处理数据 | `PythonOperator` | 数据清洗和转换 |
| 步骤 6: 总结 | `PythonOperator` | 记录统计信息 |

## 💡 实际 Airflow DAG 示例

```python
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.providers.http.operators.http import SimpleHttpOperator
from airflow.providers.postgres.operators.postgres import PostgresOperator
from datetime import datetime, timedelta

with DAG(
    'haier_crawl_pipeline',
    schedule_interval='@daily',
    start_date=datetime(2023, 11, 1),
) as dag:
    
    # 步骤 1: 创建任务
    create_task = PythonOperator(
        task_id='create_task',
        python_callable=create_crawl_task,
    )
    
    # 步骤 2: 调度爬虫
    schedule_spider = SimpleHttpOperator(
        task_id='schedule_spider',
        http_conn_id='scrapyd',
        endpoint='/schedule.json',
        method='POST',
        data={'project': 'domainspider', 'spider': 'haier_list', ...},
    )
    
    # 步骤 3: 监控进度
    monitor = PythonOperator(
        task_id='monitor_progress',
        python_callable=monitor_task,
    )
    
    # 步骤 4-5: 处理数据
    process = PythonOperator(
        task_id='process_data',
        python_callable=process_crawled_data,
    )
    
    # 任务流
    create_task >> schedule_spider >> monitor >> process
```

## 🚀 下一步

1. **测试模拟脚本**：确保所有步骤正常工作
2. **调整参数**：根据实际需求修改爬虫参数
3. **部署 Airflow**：在另一个项目中实现真实的 DAG
4. **监控告警**：添加失败通知和重试逻辑

## 📝 注意事项

1. **数据库连接**：确保 PostgreSQL 可访问
2. **Scrapyd 服务**：必须先启动 Scrapyd
3. **网络连接**：Airflow 服务器需要能访问 Scrapyd 和数据库
4. **定期清理**：使用 `cleanup_old_data()` 函数清理旧数据


┌─────────────────────────────────────────────────┐
│              Airflow (调度器)                    │
│  - 创建任务                                      │
│  - 调用 Scrapyd API                              │
└─────────────────┬───────────────────────────────┘
                  │
                  ↓ HTTP POST /schedule.json
┌─────────────────────────────────────────────────┐
│              Scrapyd (爬虫服务器)                │
│                                                  │
│  ┌────────────────────────────────────┐         │
│  │  SQLite (dbs/default.db)           │         │
│  │  - 任务队列                         │         │
│  │  - job_id: abc123                  │         │
│  │  - status: running                 │         │
│  └────────────────────────────────────┘         │
│                  │                               │
│                  ↓ 启动爬虫进程                  │
│  ┌────────────────────────────────────┐         │
│  │  Scrapy Spider (haier)             │         │
│  │  - 爬取数据                         │         │
│  │  - 通过 Pipeline 写入 PostgreSQL    │         │
│  └────────────────────────────────────┘         │
└─────────────────┬───────────────────────────────┘
                  │
                  ↓ 爬虫数据通过 Pipeline 写入
┌─────────────────────────────────────────────────┐
│          PostgreSQL (业务数据库)                 │
│                                                  │
│  ┌────────────────────────────────────┐         │
│  │  crawl_tasks 表                    │         │
│  │  - task_id: haier_20231125         │         │
│  │  - status: running                 │         │
│  │  - items_scraped: 100              │         │
│  └────────────────────────────────────┘         │
│                                                  │
│  ┌────────────────────────────────────┐         │
│  │  crawl_items 表                    │         │
│  │  - url: https://...                │         │
│  │  - title: 海尔冰箱                  │         │
│  │  - content: {...}                  │         │
│  └────────────────────────────────────┘         │
└─────────────────────────────────────────────────┘