"""
任务状态管理工具
"""
import json
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime
from typing import Dict, Any, Optional, List


class TaskStatusManager:
    """任务状态管理器 - 基于 PostgreSQL"""
    
    def __init__(self, postgres_url: str):
        self.postgres_url = postgres_url
        self._conn = None
    
    @property
    def conn(self):
        """获取数据库连接（懒加载）"""
        if self._conn is None or self._conn.closed:
            self._conn = psycopg2.connect(self.postgres_url, cursor_factory=RealDictCursor)
        return self._conn
    
    def create_task(self, task_id: str, spider_name: str, params: Dict[str, Any], airflow_run_id: str = None):
        """创建新任务记录"""
        with self.conn.cursor() as cur:
            cur.execute("""
                INSERT INTO spider_tasks (
                    task_id, spider_name, status, params, airflow_run_id, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (task_id) DO UPDATE SET
                    status = 'pending',
                    params = EXCLUDED.params,
                    airflow_run_id = EXCLUDED.airflow_run_id,
                    updated_at = CURRENT_TIMESTAMP
            """, (
                task_id, spider_name, 'pending', 
                json.dumps(params), airflow_run_id, datetime.now()
            ))
        self.conn.commit()
    
    def update_task_status(self, task_id: str, status: str, **kwargs):
        """更新任务状态"""
        
        # 构建更新字段
        update_fields = ['status = %s', 'updated_at = %s']
        update_values = [status, datetime.now()]
        
        # 动态添加其他字段
        field_mapping = {
            'items_count': 'items_count',
            'error_message': 'error_message', 
            'output_location': 'output_location',
            'started_at': 'started_at',
            'finished_at': 'finished_at'
        }
        
        for key, value in kwargs.items():
            if key in field_mapping and value is not None:
                update_fields.append(f'{field_mapping[key]} = %s')
                update_values.append(value)
        
        # 执行更新
        with self.conn.cursor() as cur:
            sql = f"""
                UPDATE spider_tasks 
                SET {', '.join(update_fields)}
                WHERE task_id = %s
            """
            update_values.append(task_id)
            cur.execute(sql, update_values)
        
        self.conn.commit()
    
    def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """获取任务状态"""
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT task_id, spider_name, status, params, items_count, 
                       error_message, output_location, started_at, finished_at,
                       created_at, updated_at, airflow_run_id
                FROM spider_tasks 
                WHERE task_id = %s
            """, (task_id,))
            
            result = cur.fetchone()
            if result:
                # 转换为普通字典并处理日期格式
                task_info = dict(result)
                
                # 解析 JSON 参数
                if task_info['params']:
                    task_info['params'] = json.loads(task_info['params'])
                
                # 格式化日期
                for date_field in ['started_at', 'finished_at', 'created_at', 'updated_at']:
                    if task_info[date_field]:
                        task_info[date_field] = task_info[date_field].isoformat()
                
                return task_info
        
        return None
    
    def get_tasks_by_status(self, status: str, limit: int = 100) -> List[Dict[str, Any]]:
        """根据状态获取任务列表"""
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT task_id, spider_name, status, created_at, updated_at
                FROM spider_tasks 
                WHERE status = %s
                ORDER BY created_at DESC
                LIMIT %s
            """, (status, limit))
            
            results = cur.fetchall()
            return [dict(row) for row in results]
    
    def get_spider_stats(self, spider_name: str, date_from: str = None) -> Dict[str, Any]:
        """获取爬虫统计信息"""
        with self.conn.cursor() as cur:
            where_clause = "WHERE spider_name = %s"
            params = [spider_name]
            
            if date_from:
                where_clause += " AND created_at >= %s"
                params.append(date_from)
            
            cur.execute(f"""
                SELECT 
                    status,
                    COUNT(*) as count,
                    SUM(COALESCE(items_count, 0)) as total_items
                FROM spider_tasks 
                {where_clause}
                GROUP BY status
            """, params)
            
            results = cur.fetchall()
            
            stats = {
                'spider_name': spider_name,
                'by_status': {},
                'total_tasks': 0,
                'total_items': 0
            }
            
            for row in results:
                stats['by_status'][row['status']] = {
                    'count': row['count'],
                    'items': row['total_items']
                }
                stats['total_tasks'] += row['count']
                stats['total_items'] += row['total_items']
            
            return stats
    
    def cleanup_old_tasks(self, days: int = 30):
        """清理旧任务记录"""
        with self.conn.cursor() as cur:
            cur.execute("""
                DELETE FROM spider_tasks 
                WHERE created_at < CURRENT_TIMESTAMP - INTERVAL '%s days'
                AND status IN ('completed', 'failed')
            """, (days,))
            
            deleted_count = cur.rowcount
        
        self.conn.commit()
        return deleted_count
    
    def close(self):
        """关闭数据库连接"""
        if self._conn and not self._conn.closed:
            self._conn.close()


class TaskProgress:
    """任务进度跟踪器"""
    
    def __init__(self, task_id: str, status_manager: TaskStatusManager):
        self.task_id = task_id
        self.status_manager = status_manager
        self.start_time = datetime.now()
    
    def start(self, spider_name: str):
        """标记任务开始"""
        self.status_manager.update_task_status(
            self.task_id, 
            'running',
            started_at=self.start_time
        )
    
    def update_progress(self, items_count: int, message: str = None):
        """更新进度"""
        # 这里可以扩展为更详细的进度跟踪
        pass
    
    def complete(self, items_count: int, output_location: str = None):
        """标记任务完成"""
        self.status_manager.update_task_status(
            self.task_id,
            'completed',
            items_count=items_count,
            output_location=output_location,
            finished_at=datetime.now()
        )
    
    def fail(self, error_message: str):
        """标记任务失败"""
        self.status_manager.update_task_status(
            self.task_id,
            'failed', 
            error_message=error_message,
            finished_at=datetime.now()
        )
    
    def timeout(self):
        """标记任务超时"""
        self.status_manager.update_task_status(
            self.task_id,
            'timeout',
            error_message='Task execution timeout',
            finished_at=datetime.now()
        )


# 数据库初始化脚本
def init_database(postgres_url: str):
    """初始化数据库表"""
    
    conn = psycopg2.connect(postgres_url)
    
    with conn.cursor() as cur:
        # 创建任务表
        cur.execute("""
            CREATE TABLE IF NOT EXISTS spider_tasks (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                task_id VARCHAR(200) NOT NULL UNIQUE,
                spider_name VARCHAR(100) NOT NULL,
                status VARCHAR(50) NOT NULL DEFAULT 'pending',
                params JSONB,
                items_count INTEGER DEFAULT 0,
                output_location TEXT,
                error_message TEXT,
                airflow_run_id VARCHAR(200),
                started_at TIMESTAMP,
                finished_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        
        # 创建索引
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_spider_tasks_task_id ON spider_tasks(task_id);
            CREATE INDEX IF NOT EXISTS idx_spider_tasks_spider_name ON spider_tasks(spider_name);
            CREATE INDEX IF NOT EXISTS idx_spider_tasks_status ON spider_tasks(status);
            CREATE INDEX IF NOT EXISTS idx_spider_tasks_created_at ON spider_tasks(created_at);
        """)
        
        # 创建更新时间触发器
        cur.execute("""
            CREATE OR REPLACE FUNCTION update_updated_at_column()
            RETURNS TRIGGER AS $$
            BEGIN
                NEW.updated_at = CURRENT_TIMESTAMP;
                RETURN NEW;
            END;
            $$ language 'plpgsql';
        """)
        
        cur.execute("""
            DROP TRIGGER IF EXISTS update_spider_tasks_updated_at ON spider_tasks;
            CREATE TRIGGER update_spider_tasks_updated_at
                BEFORE UPDATE ON spider_tasks
                FOR EACH ROW
                EXECUTE FUNCTION update_updated_at_column();
        """)
    
    conn.commit()
    conn.close()


if __name__ == "__main__":
    # 测试代码
    postgres_url = "postgresql://postgres:password@localhost:5432/domainspider"
    
    # 初始化数据库
    init_database(postgres_url)
    
    # 测试状态管理
    manager = TaskStatusManager(postgres_url)
    
    # 创建测试任务
    test_params = {
        'spider_name': 'jd',
        'domain': 'ecommerce',
        'task_type': 'product_list',
        'level_1': '手机'
    }
    
    task_id = 'test_task_123'
    manager.create_task(task_id, 'jd', test_params)
    
    # 更新状态
    manager.update_task_status(task_id, 'running', started_at=datetime.now())
    manager.update_task_status(task_id, 'completed', items_count=100, finished_at=datetime.now())
    
    # 查询状态
    status = manager.get_task_status(task_id)
    print("任务状态:", status)
    
    manager.close()
