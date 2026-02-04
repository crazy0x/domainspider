"""
DomainSpider 打包配置
用于部署到 Scrapyd
"""
from setuptools import setup, find_packages

setup(
    name='domainspider',
    version='1.0.0',
    description='Multi-domain web scraping framework based on Scrapy',
    author='ShareCreators',
    author_email='your-email@example.com',
    url='https://github.com/yourusername/domainspider',
    
    # 包含所有 src 下的包
    packages=find_packages(),
    
    # 包含配置文件
    package_data={
        '': ['*.yaml', '*.yml', '*.cfg'],
    },
    
    # 入口点（Scrapy 项目）
    entry_points={
        'scrapy': ['settings = config.base']
    },
    
    # 依赖
    install_requires=[
        'scrapy>=2.8.0',
        'scrapy-playwright>=0.0.44',
        'playwright>=1.40.0',
        'PyYAML>=6.0',
        'redis>=4.5.0',
        'psycopg2-binary>=2.9.0',
        'minio>=7.1.0',
    ],
    
    # Python 版本要求
    python_requires='>=3.10',
    
    # 分类
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
        'Programming Language :: Python :: 3.12',
        'Framework :: Scrapy',
    ],
    
    # 包含非 Python 文件
    include_package_data=True,
    zip_safe=False,
)
