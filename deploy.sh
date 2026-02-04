#!/bin/bash
# DomainSpider 部署脚本

set -e

echo "🚀 开始部署 DomainSpider 到 Scrapyd..."

# 1. 检查 Scrapyd 是否运行
echo "📡 检查 Scrapyd 服务..."
if ! curl -s http://localhost:6800/daemonstatus.json > /dev/null; then
    echo "❌ Scrapyd 未运行，请先启动 Scrapyd"
    echo "   启动命令: scrapyd"
    exit 1
fi

echo "✅ Scrapyd 正在运行"

# 2. 打包项目
echo "📦 打包项目..."
python setup.py bdist_egg

# 3. 部署到 Scrapyd
echo "🚢 部署到 Scrapyd..."
SCRAPYD_URL=${SCRAPYD_URL:-http://localhost:6800}
PROJECT_NAME="domainspider"
VERSION=$(date +%Y%m%d_%H%M%S)

# 获取 egg 文件
EGG_FILE=$(ls -t dist/*.egg | head -1)

if [ -z "$EGG_FILE" ]; then
    echo "❌ 未找到 egg 文件"
    exit 1
fi

echo "📤 上传: $EGG_FILE"

curl $SCRAPYD_URL/addversion.json \
    -F project=$PROJECT_NAME \
    -F version=$VERSION \
    -F egg=@$EGG_FILE

echo ""
echo "✅ 部署完成！"
echo ""
echo "📋 可用的爬虫:"
curl -s $SCRAPYD_URL/listspiders.json?project=$PROJECT_NAME | python -m json.tool

echo ""
echo "🎯 测试运行爬虫:"
echo "   curl $SCRAPYD_URL/schedule.json -d project=$PROJECT_NAME -d spider=haier_list -d level_1=kitchen_appliances"
