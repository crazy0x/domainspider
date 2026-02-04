"""
任务参数验证和处理工具
"""
from datetime import datetime
from typing import Dict, List, Tuple, Any


class TaskParamValidator:
    """任务参数验证器"""
    
    # 必填字段
    REQUIRED_FIELDS = ['spider_name', 'domain', 'task_type']
    
    # 领域配置
    DOMAIN_SCHEMAS = {
        'ecommerce': {
            'required_levels': ['level_1'],
            'valid_task_types': ['category_list', 'product_list', 'product_detail', 'price_monitor'],
            'description': '电商网站爬虫'
        },
        'automotive': {
            'required_levels': ['level_1'],
            'valid_task_types': ['brand_list', 'series_list', 'model_list', 'model_detail', 'spec_crawl', 'image_crawl'],
            'description': '汽车网站爬虫'
        },
        'forum': {
            'required_levels': ['level_1'],
            'valid_task_types': ['topic_list', 'thread_list', 'thread_detail', 'user_profile'],
            'description': '论坛网站爬虫'
        },
        'appliance': {
            'required_levels': ['level_1'],
            'valid_task_types': ['category_list', 'product_list', 'product_detail'],
            'description': '电器官网爬虫'
        }
    }
    
    def validate(self, params: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """
        验证参数
        
        Args:
            params: 任务参数字典
            
        Returns:
            Tuple[bool, List[str]]: (是否有效, 错误信息列表)
        """
        errors = []
        
        # 检查必填字段
        for field in self.REQUIRED_FIELDS:
            if field not in params or not params[field]:
                errors.append(f"Missing required field: {field}")
        
        if errors:  # 如果基础字段都没有，直接返回
            return False, errors
        
        # 检查领域特定规则
        domain = params.get('domain')
        if domain not in self.DOMAIN_SCHEMAS:
            errors.append(f"Unsupported domain: {domain}. Supported: {list(self.DOMAIN_SCHEMAS.keys())}")
            return False, errors
        
        schema = self.DOMAIN_SCHEMAS[domain]
        
        # 检查任务类型
        task_type = params.get('task_type')
        if task_type not in schema['valid_task_types']:
            errors.append(f"Invalid task_type '{task_type}' for domain '{domain}'. Valid types: {schema['valid_task_types']}")
        
        # 检查层级参数
        for level in schema['required_levels']:
            if not params.get(level):
                errors.append(f"Missing required level parameter: {level}")
        
        # 检查分页参数
        page_start = params.get('page_start', 1)
        page_end = params.get('page_end', 1)
        
        if not isinstance(page_start, int) or page_start < 1:
            errors.append("page_start must be a positive integer")
        
        if not isinstance(page_end, int) or page_end < 1:
            errors.append("page_end must be a positive integer")
        
        if isinstance(page_start, int) and isinstance(page_end, int) and page_start > page_end:
            errors.append("page_start cannot be greater than page_end")
        
        # 检查批次大小
        batch_size = params.get('batch_size', 50)
        if not isinstance(batch_size, int) or batch_size < 1:
            errors.append("batch_size must be a positive integer")
        
        # 检查最大数量限制
        max_items = params.get('max_items')
        if max_items is not None and (not isinstance(max_items, int) or max_items < 1):
            errors.append("max_items must be a positive integer")
        
        return len(errors) == 0, errors
    
    def normalize_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        标准化参数
        
        Args:
            params: 原始参数
            
        Returns:
            Dict[str, Any]: 标准化后的参数
        """
        normalized = params.copy()
        
        # 设置默认值
        normalized.setdefault('date', datetime.now().strftime('%Y-%m-%d'))
        normalized.setdefault('mode', 'incremental')
        normalized.setdefault('page_start', 1)
        normalized.setdefault('page_end', 100)
        normalized.setdefault('batch_size', 50)
        normalized.setdefault('priority', 'normal')
        normalized.setdefault('timeout', 3600)
        
        # 生成任务ID
        if 'task_id' not in normalized:
            timestamp = int(datetime.now().timestamp())
            normalized['task_id'] = f"{normalized['spider_name']}_{normalized['date']}_{timestamp}"
        
        # 标准化字符串字段
        for field in ['spider_name', 'domain', 'task_type', 'mode', 'priority']:
            if field in normalized and isinstance(normalized[field], str):
                normalized[field] = normalized[field].lower().strip()
        
        # 处理过滤参数
        if 'filters' not in normalized:
            normalized['filters'] = {}
        
        return normalized


class TaskParamBuilder:
    """任务参数构建器"""
    
    def __init__(self, spider_name: str, domain: str):
        self.params = {
            'spider_name': spider_name,
            'domain': domain
        }
    
    def task_type(self, task_type: str):
        """设置任务类型"""
        self.params['task_type'] = task_type
        return self
    
    def level(self, level_1: str = None, level_2: str = None, level_3: str = None, level_4: str = None):
        """设置层级参数"""
        if level_1:
            self.params['level_1'] = level_1
        if level_2:
            self.params['level_2'] = level_2
        if level_3:
            self.params['level_3'] = level_3
        if level_4:
            self.params['level_4'] = level_4
        return self
    
    def pages(self, start: int = 1, end: int = 100, batch_size: int = 50):
        """设置分页参数"""
        self.params.update({
            'page_start': start,
            'page_end': end,
            'batch_size': batch_size
        })
        return self
    
    def filters(self, **filters):
        """设置过滤条件"""
        self.params['filters'] = filters
        return self
    
    def options(self, mode: str = 'incremental', priority: str = 'normal', max_items: int = None):
        """设置其他选项"""
        self.params.update({
            'mode': mode,
            'priority': priority
        })
        if max_items:
            self.params['max_items'] = max_items
        return self
    
    def build(self) -> Dict[str, Any]:
        """构建参数"""
        validator = TaskParamValidator()
        normalized = validator.normalize_params(self.params)
        
        is_valid, errors = validator.validate(normalized)
        if not is_valid:
            raise ValueError(f"Invalid parameters: {errors}")
        
        return normalized


# 便捷函数
def create_ecommerce_task(spider_name: str, category_1: str, category_2: str = None, **kwargs):
    """创建电商任务参数"""
    builder = TaskParamBuilder(spider_name, 'ecommerce')
    builder.level(category_1, category_2)
    
    if kwargs:
        if 'task_type' in kwargs:
            builder.task_type(kwargs.pop('task_type'))
        if 'pages' in kwargs:
            pages = kwargs.pop('pages')
            builder.pages(**pages)
        if 'filters' in kwargs:
            builder.filters(**kwargs.pop('filters'))
        if kwargs:  # 剩余参数作为选项
            builder.options(**kwargs)
    
    return builder.build()


def create_automotive_task(spider_name: str, brand: str, series: str = None, model: str = None, **kwargs):
    """创建汽车任务参数"""
    builder = TaskParamBuilder(spider_name, 'automotive')
    builder.level(brand, series, model)
    
    if kwargs:
        if 'task_type' in kwargs:
            builder.task_type(kwargs.pop('task_type'))
        if 'pages' in kwargs:
            pages = kwargs.pop('pages')
            builder.pages(**pages)
        if 'filters' in kwargs:
            builder.filters(**kwargs.pop('filters'))
        if kwargs:
            builder.options(**kwargs)
    
    return builder.build()


def create_forum_task(spider_name: str, topic: str, subtopic: str = None, **kwargs):
    """创建论坛任务参数"""
    builder = TaskParamBuilder(spider_name, 'forum')
    builder.level(topic, subtopic)
    
    if kwargs:
        if 'task_type' in kwargs:
            builder.task_type(kwargs.pop('task_type'))
        if 'pages' in kwargs:
            pages = kwargs.pop('pages')
            builder.pages(**pages)
        if 'filters' in kwargs:
            builder.filters(**kwargs.pop('filters'))
        if kwargs:
            builder.options(**kwargs)
    
    return builder.build()


# 使用示例
if __name__ == "__main__":
    # 电商任务示例
    ecommerce_params = create_ecommerce_task(
        spider_name='jd',
        category_1='手机',
        category_2='智能手机',
        task_type='product_list',
        pages={'start': 1, 'end': 50},
        filters={'price_min': 1000, 'price_max': 5000}
    )
    print("电商任务参数:", ecommerce_params)
    
    # 汽车任务示例
    auto_params = create_automotive_task(
        spider_name='autohome',
        brand='奔驰',
        series='C级',
        task_type='model_list'
    )
    print("汽车任务参数:", auto_params)
