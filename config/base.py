"""
DomainSpider YAML 配置加载器
将 YAML 配置转换为 Scrapy 设置
"""
import os
import yaml
import re
from pathlib import Path


def load_yaml_config(config_name='base'):
    """
    加载 YAML 配置文件
    支持环境变量替换和配置继承
    """
    config_dir = Path(__file__).parent
    config_file = config_dir / f"{config_name}.yaml"
    
    if not config_file.exists():
        raise FileNotFoundError(f"Config file not found: {config_file}")
    
    with open(config_file, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    
    # 处理配置继承
    if 'extends' in config:
        base_config_name = config['extends'].replace('.yaml', '')
        base_config = load_yaml_config(base_config_name)
        config = merge_configs(base_config, config)
        del config['extends']
    
    # 处理环境变量替换
    config = substitute_env_vars(config)
    
    return config


def merge_configs(base_config, override_config):
    """递归合并配置"""
    result = base_config.copy()
    
    for key, value in override_config.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = merge_configs(result[key], value)
        else:
            result[key] = value
    
    return result


def substitute_env_vars(obj):
    """递归替换环境变量"""
    if isinstance(obj, dict):
        return {key: substitute_env_vars(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [substitute_env_vars(item) for item in obj]
    elif isinstance(obj, str):
        # 支持 ${VAR:default} 格式
        pattern = r'\$\{([^}:]+)(?::([^}]*))?\}'
        
        def replace_var(match):
            var_name = match.group(1)
            default_value = match.group(2) or ''
            return os.getenv(var_name, default_value)
        
        return re.sub(pattern, replace_var, obj)
    else:
        return obj


def yaml_to_scrapy_settings(config):
    """将 YAML 配置转换为 Scrapy 设置格式"""
    settings = {}
    
    # Scrapy 基础配置
    if 'scrapy' in config:
        scrapy_config = config['scrapy']
        settings['BOT_NAME'] = scrapy_config.get('bot_name', 'domainspider')
        settings['SPIDER_MODULES'] = scrapy_config.get('spider_modules', ['src.spiders'])
        settings['NEWSPIDER_MODULE'] = scrapy_config.get('newspider_module', 'src.spiders')
        settings['ROBOTSTXT_OBEY'] = scrapy_config.get('robotstxt_obey', False)
    
    # 并发配置
    if 'concurrency' in config:
        concurrency = config['concurrency']
        settings['CONCURRENT_REQUESTS'] = concurrency.get('concurrent_requests', 32)
        settings['CONCURRENT_REQUESTS_PER_DOMAIN'] = concurrency.get('concurrent_requests_per_domain', 16)
        settings['DOWNLOAD_DELAY'] = concurrency.get('download_delay', 1)
        settings['RANDOMIZE_DOWNLOAD_DELAY'] = concurrency.get('randomize_download_delay', 0.5)
    
    # 超时配置
    if 'timeout' in config:
        timeout = config['timeout']
        settings['DOWNLOAD_TIMEOUT'] = timeout.get('download_timeout', 30)
        settings['RETRY_TIMES'] = timeout.get('retry_times', 3)
        settings['RETRY_HTTP_CODES'] = timeout.get('retry_http_codes', [500, 502, 503, 504, 408, 429])
    
    # 中间件配置
    if 'middlewares' in config:
        middlewares = config['middlewares']
        if 'downloader' in middlewares:
            settings['DOWNLOADER_MIDDLEWARES'] = middlewares['downloader']
    
    # 管道配置
    if 'pipelines' in config:
        pipelines = config['pipelines']
        if 'item' in pipelines:
            settings['ITEM_PIPELINES'] = pipelines['item']
    
    # Redis 配置
    if 'redis' in config:
        redis_config = config['redis']
        settings['REDIS_URL'] = redis_config.get('url', 'redis://localhost:6379')
        
        # 只在配置了值时才设置（避免设置为 None）
        if redis_config.get('dupefilter_class'):
            settings['DUPEFILTER_CLASS'] = redis_config.get('dupefilter_class')
        if redis_config.get('scheduler'):
            settings['SCHEDULER'] = redis_config.get('scheduler')
            settings['SCHEDULER_PERSIST'] = redis_config.get('scheduler_persist', True)
        
        if 'bloom_params' in redis_config:
            bloom_params = redis_config['bloom_params']
            settings['REDIS_BLOOM_PARAMS'] = {
                'redis_url': settings['REDIS_URL'],
                'hash_number': bloom_params.get('hash_number', 6),
                'bit': bloom_params.get('bit', 30),
            }
    
    # 代理配置
    if 'proxy' in config:
        proxy_config = config['proxy']
        settings['PROXY_API_URL'] = proxy_config.get('api_url', 'http://localhost:5010/get')
        settings['PROXY_ENABLED'] = str(proxy_config.get('enabled', True)).lower() == 'true'
    
    # 输出配置
    if 'output' in config:
        output_config = config['output']
        settings['OUTPUT_DIR'] = output_config.get('dir', '/tmp/scrapy_output')
        settings['OUTPUT_FORMAT'] = output_config.get('format', 'jsonlines')
    
    # PostgreSQL 配置
    if 'postgres' in config:
        postgres_config = config['postgres']
        settings['POSTGRES_URL'] = postgres_config.get('url', 'postgresql://localhost/domainspider')
    
    # 日志配置
    if 'logging' in config:
        logging_config = config['logging']
        settings['LOG_LEVEL'] = logging_config.get('level', 'INFO')
        settings['LOG_FILE'] = logging_config.get('file', 'logs/scrapy.log')
    
    # 监控配置
    if 'monitoring' in config:
        monitoring = config['monitoring']
        if monitoring.get('stats_class'):
            settings['STATS_CLASS'] = monitoring.get('stats_class')
        settings['TELNETCONSOLE_ENABLED'] = monitoring.get('telnetconsole_enabled', False)
    
    # 扩展配置
    if 'extensions' in config:
        settings['EXTENSIONS'] = config['extensions']
    
    # 其他配置
    settings['REQUEST_FINGERPRINTER_IMPLEMENTATION'] = config.get('request_fingerprinter_implementation', '2.7')
    
    # AutoThrottle 配置
    if 'autothrottle' in config:
        autothrottle = config['autothrottle']
        settings['AUTOTHROTTLE_ENABLED'] = autothrottle.get('enabled', True)
        settings['AUTOTHROTTLE_START_DELAY'] = autothrottle.get('start_delay', 1)
        settings['AUTOTHROTTLE_MAX_DELAY'] = autothrottle.get('max_delay', 60)
        settings['AUTOTHROTTLE_TARGET_CONCURRENCY'] = autothrottle.get('target_concurrency', 2.0)
        settings['AUTOTHROTTLE_DEBUG'] = autothrottle.get('debug', False)
    
    # 缓存配置
    if 'httpcache' in config:
        httpcache = config['httpcache']
        settings['HTTPCACHE_ENABLED'] = httpcache.get('enabled', False)
        settings['HTTPCACHE_EXPIRATION_SECS'] = httpcache.get('expiration_secs', 3600)
        settings['HTTPCACHE_DIR'] = httpcache.get('dir', 'httpcache')
    
    # 任务配置
    if 'task' in config:
        task_config = config['task']
        settings['TASK_ID_FORMAT'] = task_config.get('id_format', '{spider_name}_{date}_{timestamp}')
        settings['BATCH_SIZE'] = task_config.get('batch_size', 1000)
    
    return settings


# 获取环境配置名称
ENV = os.getenv('SCRAPY_ENV', 'base')

# 加载配置
try:
    config = load_yaml_config(ENV)
    scrapy_settings = yaml_to_scrapy_settings(config)
    
    # 将配置导入到当前模块
    globals().update(scrapy_settings)
    
    # 保存原始配置供其他模块使用
    YAML_CONFIG = config
    
except Exception as e:
    print(f"Error loading YAML config: {e}")
    # 如果 YAML 加载失败，使用默认配置
    BOT_NAME = 'domainspider'
    SPIDER_MODULES = ['src.spiders']
