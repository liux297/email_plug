#!/bin/bash
# 自动从 Dify plugin daemon 获取最新的 REMOTE_INSTALL_KEY 并更新到 .env 文件
# 用法: Dify 重启后运行一次 ./update_key.sh

PLUGIN_DAEMON_URL="http://localhost:5003"
ENV_FILE="$(dirname "$0")/.env"

echo "正在从 ${PLUGIN_DAEMON_URL} 获取最新的调试密钥..."

# 尝试从 plugin daemon 获取当前 debug key
RESPONSE=$(curl -s "${PLUGIN_DAEMON_URL}/debug/key" 2>/dev/null)

if [ -z "$RESPONSE" ] || echo "$RESPONSE" | grep -q "404\|not found\|error"; then
    echo "无法通过 API 获取密钥。"
    echo ""
    echo "请手动获取："
    echo "  1. 打开浏览器访问: http://localhost:8008/console/api/plugins/debugging"
    echo "  2. 或访问 Dify 插件页面，点击调试插件，从页面中复制密钥"
    echo "  3. 然后手动更新 .env 文件中的 REMOTE_INSTALL_KEY"
    exit 1
fi

# 提取 key (根据 API 返回格式解析)
NEW_KEY=$(echo "$RESPONSE" | python3 -c "import sys,json; data=json.load(sys.stdin); print(data.get('key','') if isinstance(data,dict) else data)" 2>/dev/null)

if [ -z "$NEW_KEY" ]; then
    NEW_KEY=$(echo "$RESPONSE" | tr -d '"' | tr -d ' ')
fi

if [ -z "$NEW_KEY" ]; then
    echo "解析密钥失败。API 返回: $RESPONSE"
    exit 1
fi

# 更新 .env 文件
if [ -f "$ENV_FILE" ]; then
    OLD_KEY=$(grep "REMOTE_INSTALL_KEY" "$ENV_FILE" | cut -d'=' -f2)
    sed -i '' "s/REMOTE_INSTALL_KEY=.*/REMOTE_INSTALL_KEY=${NEW_KEY}/" "$ENV_FILE"
    echo "✅ 密钥已更新！"
    echo "   旧: ${OLD_KEY}"
    echo "   新: ${NEW_KEY}"
    echo ""
    echo "现在可以启动插件: python -m main"
else
    echo "❌ 未找到 .env 文件: $ENV_FILE"
    exit 1
fi
