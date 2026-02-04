#!/bin/bash
# 停止 Scrapyd 服务

echo "🛑 停止 Scrapyd 服务..."

# 查找 Scrapyd 进程（只匹配实际的 scrapyd 命令）
PIDS=$(ps aux | grep -E 'scrapyd$|scrapyd ' | grep -v grep | awk '{print $2}')

if [ -z "$PIDS" ]; then
    echo "⚠️  Scrapyd 未运行"
    exit 0
fi

echo "📍 找到进程: $PIDS"

# 逐个停止进程
for PID in $PIDS; do
    echo "🔪 停止进程 $PID..."
    kill $PID
    
    sleep 1
    
    # 确认是否停止
    if ps -p $PID > /dev/null 2>&1; then
        echo "⚠️  进程 $PID 未停止，强制终止..."
        kill -9 $PID
    fi
done

echo "✅ Scrapyd 已停止"
