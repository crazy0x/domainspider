# DomainSpider 目录结构

## 📁 完整目录树

```
domainspider/
├── config/                          # 配置文件
│   ├── __init__.py
│   ├── base.py                      # YAML 配置加载器
│   └── base.yaml                    # 全局配置（Scrapy 默认使用）
│
├── src/                             # 源代码
│   ├── __init__.py
│   │
│   ├── items/                       # 数据模型
│   │   ├── __init__.py
│   │   └── base.py                  # BaseItem 定义
│   │
│   ├── spiders/                     # 爬虫目录
│   │   ├── __init__.py
│   │   ├── base.py                  # 基础爬虫类（最小化抽象 + Mixin）
│   │   │
│   │   ├── ecommerce/               # 电商领域
│   │   │   └── __init__.py
│   │   │
│   │   ├── fashion/                 # 时尚领域
│   │   │   └── __init__.py
│   │   │
│   │   ├── automotive/              # 汽车领域
│   │   │   └── __init__.py
│   │   │
│   │   ├── forum/                   # 论坛领域
│   │   │   └── __init__.py
│   │   │
│   │   └── appliance/               # 电器领域 ⭐
│   │       ├── __init__.py
│   │       ├── README.md            # 电器领域说明文档
│   │       │
│   │       ├── haier/               # 海尔品牌 ⭐
│   │       │   ├── __init__.py
│   │       │   ├── config.py        # 海尔专属配置
│   │       │   ├── crawl.py         # 海尔爬虫入口（包含列表和详情爬虫）
│   │       │
│   │       └── midea/               # 美的品牌（待开发）
│   │           └── __init__.py
│   │       
│   ├── middlewares/                 # 中间件
│   │   ├── __init__.py
│   │   ├── useragent.py             # UA 轮换
│   │   ├── proxy.py                 # 代理池
│   │   ├── retry.py                 # 智能重试
│   │   └── monitor.py               # 监控中间件
│   │
│   ├── pipelines/                   # 数据管道
│   │   ├── __init__.py
│   │   ├── validation.py            # 数据验证
│   │   ├── postgres.py              # PostgreSQL存储（采集数据写入、任务进度更新）
│   │   └── output.py                # 文件输出
│   │
│   ├── utils/                       # 工具函数
│   │   ├── __init__.py
│   │   ├── config.py                # 配置管理器
│   │   ├── params.py                # 参数验证和构建 ⭐
│   │   └── status.py                # 任务状态管理 ⭐
│   │
│   └── extensions/                  # 扩展组件
│       └── __init__.py
│
├── docs/                            # 文档
│   ├── REFACTOR_GUIDE.md            # 重构指南
│   └── (其他文档)
│
├── logs/                            # 日志目录
├── data/                            # 数据目录
├── .venv/                           # 虚拟环境
│
├── scrapy.cfg                       # Scrapy 项目配置
├── requirements.txt                 # 依赖列表
├── .env.example                     # 环境变量示例
├── .gitignore                       # Git 忽略配置
│
└── README.md                        # 项目说明
```

## 🎯 关键目录说明

### 1. 爬虫组织结构

```
spiders/
├── base.py                    # 基础类（最小化抽象）
│   ├── BaseSpider            # 最小基类
│   ├── TextExtractorMixin    # 文本提取工具
│   ├── URLHelperMixin        # URL 处理工具
│   ├── PaginationMixin       # 翻页辅助
│   └── ErrorHandlerMixin     # 错误处理
│
└── {domain}/                  # 领域目录
    └── {brand}/               # 品牌目录
        ├── __init__.py        # 导出爬虫类
        ├── config.py          # 品牌配置
        ├── list.py            # 列表爬虫
        ├── detail.py          # 详情爬虫
        └── (其他).py          # 其他爬虫
```

### 2. 配置层次

```
config/
├── base.yaml              # 全局基础配置
│   ├── scrapy 配置
│   ├── 中间件配置
│   ├── Pipeline 配置
│   └── Playwright 配置
│
├── {env}.yaml             # 环境特定配置
│   └── extends: base.yaml # 继承基础配置
│
└── spiders.yaml           # 爬虫业务配置
    ├── domains            # 领域定义
    └── spiders            # 爬虫配置
```

### 3. 工具函数

```
utils/
├── config.py              # YAML 配置管理
│   ├── ConfigManager
│   ├── get_spider_config()
│   └── get_domain_config()
│
├── params.py              # 参数验证
│   ├── TaskParamValidator
│   ├── TaskParamBuilder
│   └── create_xxx_task()
│
└── status.py              # 状态管理
    ├── TaskStatusManager
    └── TaskProgress
```

## 🚀 使用示例

### 运行爬虫

```bash
# 海尔列表爬虫
scrapy crawl haier_list \
  -a task_type=product_list \
  -a level_1=kitchen_appliances \
  -a page_start=1 \
  -a page_end=5

# 海尔详情爬虫
scrapy crawl haier_detail \
  -a product_urls="https://www.haier.com/..."
```

### 导入使用

```python
# 导入爬虫
from src.spiders.appliance.haier import HaierListSpider

# 导入配置
from src.spiders.appliance.haier.config import HAIER_CATEGORIES

# 导入工具
from src.utils.params import create_appliance_task
from src.utils.status import TaskStatusManager
```

## 📝 设计原则

### 1. 按领域分类
- 每个领域一个目录（ecommerce, automotive, forum, appliance）
- 领域内按品牌组织

### 2. 按品牌组织
- 每个品牌一个独立目录
- 品牌内包含多个爬虫和共享配置

### 3. 最小化抽象
- BaseSpider 只提供必要功能
- 通过 Mixin 提供可选工具
- 不强制抽象方法

### 4. 配置分离
- 框架配置在 `config/`
- 品牌配置在 `spiders/{domain}/{brand}/config.py`
- 爬虫逻辑在 `spiders/{domain}/{brand}/*.py`

## 🔗 相关文档

- [海尔爬虫使用指南](docs/HAIER_SPIDER_GUIDE.md)
- [电器领域说明](src/spiders/appliance/README.md)
- [重构总结](REFACTORING_SUMMARY.md)
- [BaseSpider 源码](src/spiders/base.py)
