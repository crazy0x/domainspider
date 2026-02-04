#!/bin/bash
# 启动 Scrapyd 服务

echo "🚀 启动 Scrapyd 服务..."

# 确保日志目录存在
mkdir -p logs

# 加载环境变量（如果存在 .env 文件）
if [ -f .env ]; then
    echo "📝 加载环境变量..."
    export $(cat .env | grep -v '^#' | xargs)
fi

# 检查是否已经在运行
if curl -s http://localhost:6800/daemonstatus.json > /dev/null 2>&1; then
    echo "⚠️  Scrapyd 已经在运行"
    echo "📊 状态:"
    curl -s http://localhost:6800/daemonstatus.json | python -m json.tool
    exit 0
fi

# 后台启动 Scrapyd
echo "🔧 在后台启动 Scrapyd..."
nohup scrapyd > logs/scrapyd.log 2>&1 &

# 等待启动
sleep 2

# 检查是否启动成功
if curl -s http://localhost:6800/daemonstatus.json > /dev/null 2>&1; then
    echo "✅ Scrapyd 启动成功！"
    echo "📡 访问: http://localhost:6800"
    echo "📋 查看日志: tail -f logs/scrapyd.log"
    echo ""
    echo "🎯 下一步:"
    echo "   1. 部署爬虫: ./deploy.sh"
    echo "   2. 停止服务: ./stop_scrapyd.sh"
else
    echo "❌ Scrapyd 启动失败"
    echo "📋 查看日志: tail logs/scrapyd.log"
    exit 1
fi
