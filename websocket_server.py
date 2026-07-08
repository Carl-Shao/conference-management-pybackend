import asyncio
import websockets
import json
import redis
from config import Config

class SubtitleWebSocketServer:
    """
    字幕WebSocket服务器，用于实时推送ASR识别结果到前端
    """
    def __init__(self):
        self.clients = set()  # 存储所有连接的客户端
        self.redis_client = None
        self.pubsub = None

    def init_redis(self):
        """初始化Redis连接"""
        try:
            self.redis_client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
            self.redis_client.ping()
            print("✅ WebSocket服务器Redis连接成功")
            return True
        except Exception as e:
            print(f"❌ WebSocket服务器Redis连接失败：{e}")
            return False

    async def register_client(self, websocket, meeting_id):
        """注册客户端并订阅特定会议的字幕频道"""
        client_info = {
            'websocket': websocket,
            'meeting_id': meeting_id
        }
        self.clients.add(client_info)
        print(f"👥 客户端已连接：会议{meeting_id}")

        # 订阅对应会议的字幕频道
        if self.pubsub:
            channel_name = f"subtitle:{meeting_id}"
            self.pubsub.subscribe(channel_name)

    async def unregister_client(self, websocket):
        """注销客户端"""
        # 找到并移除客户端
        client_to_remove = None
        for client in self.clients:
            if client['websocket'] == websocket:
                client_to_remove = client
                break

        if client_to_remove:
            self.clients.remove(client_to_remove)
            meeting_id = client_to_remove['meeting_id']
            print(f"👋 客户端已断开：会议{meeting_id}")

            # 取消订阅
            if self.pubsub:
                channel_name = f"subtitle:{meeting_id}"
                self.pubsub.unsubscribe(channel_name)

    async def handle_client(self, websocket, path):
        """处理客户端连接"""
        # 从路径中解析会议ID
        # 假设路径格式为 /subtitle/{meeting_id}
        try:
            path_parts = path.strip('/').split('/')
            if len(path_parts) >= 2 and path_parts[0] == 'subtitle':
                meeting_id = path_parts[1]
            else:
                print("⚠️ 无效的WebSocket路径，无法解析会议ID")
                return
        except Exception as e:
            print(f"⚠️ 解析会议ID失败：{e}")
            return

        await self.register_client(websocket, meeting_id)

        try:
            # 保持连接
            await websocket.wait_closed()
        finally:
            await self.unregister_client(websocket)

    async def start_server(self, host='localhost', port=8765):
        """启动WebSocket服务器"""
        if not self.init_redis():
            print("❌ WebSocket服务器初始化失败")
            return

        # 启动Redis发布/订阅监听
        self.pubsub = self.redis_client.pubsub()

        # 启动WebSocket服务器
        server = await websockets.serve(self.handle_client, host, port)
        print(f"🌐 WebSocket服务器启动于 ws://{host}:{port}")

        # 启动Redis消息监听协程
        asyncio.create_task(self.listen_redis_messages())

        return server

    async def listen_redis_messages(self):
        """监听Redis发布的消息并转发给相关客户端"""
        if not self.pubsub:
            return

        async for message in self.pubsub.listen():
            if message['type'] == 'message':
                try:
                    # 解析Redis消息
                    data = json.loads(message['data'])
                    meeting_id = data.get('meetingId')

                    # 找到订阅此会议的客户端并发送消息
                    for client in self.clients.copy():  # 使用copy防止迭代时修改集合
                        if client['meeting_id'] == meeting_id:
                            try:
                                await client['websocket'].send(json.dumps(data))
                                print(f"📤 字幕已发送到会议{meeting_id}的客户端")
                            except websockets.exceptions.ConnectionClosed:
                                # 如果连接已关闭，移除客户端
                                await self.unregister_client(client['websocket'])
                            except Exception as e:
                                print(f"❌ 发送消息失败：{e}")

                except json.JSONDecodeError:
                    print("⚠️ 无法解析Redis消息")
                except Exception as e:
                    print(f"❌ 处理Redis消息时出错：{e}")

# 全局实例
subtitle_server = SubtitleWebSocketServer()

async def main():
    """主函数，启动WebSocket服务器"""
    await subtitle_server.start_server()

    # 保持服务器运行
    while True:
        await asyncio.sleep(3600)  # 每小时循环一次

if __name__ == "__main__":
    asyncio.run(main())