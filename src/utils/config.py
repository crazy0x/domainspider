"""
配置工具函数
提供便捷的配置访问方法
"""
import os
from pathlib import Path
from config.base import load_yaml_config


class ConfigManager:
    """配置管理器"""
    
    def __init__(self):
        self._config = None
        self.reload()
    
    def reload(self):
        """重新加载配置"""
        env = os.getenv('SCRAPY_ENV', 'base')
        self._config = load_yaml_config(env)
    
    def get(self, key, default=None):
        """获取配置值，支持点号分隔的嵌套键"""
        keys = key.split('.')
        value = self._config
        
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        
        return value
    
    
    @property
    def config(self):
        """获取完整配置"""
        return self._config


# 全局配置管理器实例
config_manager = ConfigManager()


def get_config(key, default=None):
    """获取配置值的便捷函数"""
    return config_manager.get(key, default)


def reload_config():
    """重新加载配置的便捷函数"""
    config_manager.reload()


def get_output_path(spider_name, format='jsonlines'):
    """生成输出文件路径"""
    from datetime import datetime
    
    output_dir = get_config('output.dir', '/tmp/scrapy_output')
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    # 确保输出目录存在
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    
    # 根据格式生成文件扩展名
    extensions = {
        'jsonlines': 'jsonl',
        'json': 'json',
        'csv': 'csv'
    }
    
    ext = extensions.get(format, 'jsonl')
    filename = f"{spider_name}_{timestamp}.{ext}"
    
    return Path(output_dir) / filename
