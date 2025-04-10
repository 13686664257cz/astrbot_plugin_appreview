from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from typing import Optional
import asyncio


class ApifoxModel:
    def __init__(self, approve: bool, flag: str, reason: Optional[str] = None) -> None:
        self.approve = approve
        self.flag = flag
        self.reason = reason

@register("astrbot_plugin_appreview", "qiqi", "一个可以通过关键词来同意或拒绝进入群聊的插件", "1.2.0")
class AppReviewPlugin(Star):
    def __init__(self, context: Context, config=None):
        super().__init__(context)
        # 默认配置
        self.config = {
            "accept_keywords": ["给了", "一键三连了", "三连了"],
            "reject_keywords": ["拒绝", "不同意", "reject", "deny"],
            "auto_accept": False,  # 是否自动同意所有申请
            "auto_reject": False,  # 是否自动拒绝所有申请
            "reject_reason": "申请被拒绝",  # 拒绝理由
            "delay_seconds": 0  # 延迟处理时间（秒）
        }
        
        # 如果传入了配置，则使用传入的配置
        if config:
            for key, value in config.items():
                if key in self.config:
                    self.config[key] = value
            logger.info(f"群聊申请审核插件配置加载成功: {self.config}")
        else:
            # 否则从context加载配置
            self.load_config()
        
        # Monkey patch AstrBotMessage类，确保所有实例都有session_id属性
        from astrbot.core.platform.astrbot_message import AstrBotMessage
        original_init = AstrBotMessage.__init__
        
        def patched_init(self, *args, **kwargs):
            original_init(self, *args, **kwargs)
            if not hasattr(self, "session_id") or not self.session_id:
                self.session_id = "unknown_session"
        
        # 应用monkey patch
        AstrBotMessage.__init__ = patched_init
        logger.info("已应用AstrBotMessage的monkey patch，确保session_id属性存在")
    
    def load_config(self):
        """加载配置"""
        try:
            user_config = self.context.get_config()
            if user_config:
                for key, value in user_config.items():
                    if key in self.config:
                        self.config[key] = value
            logger.info(f"群聊申请审核插件配置加载成功: {self.config}")
        except Exception as e:
            logger.error(f"群聊申请审核插件配置加载失败: {e}")
    
    def set_session_id(self, event):
        """设置session_id属性"""
        if not hasattr(event, "message_obj") or not hasattr(event.message_obj, "raw_message"):
            return
            
        raw_message = event.message_obj.raw_message
        if not isinstance(raw_message, dict):
            return
            
        # 如果没有session_id属性，则根据请求类型添加
        if not hasattr(event.message_obj, "session_id") or not event.message_obj.session_id:
            if "group_id" in raw_message and raw_message["group_id"]:
                event.message_obj.session_id = str(raw_message["group_id"])
            elif "user_id" in raw_message and raw_message["user_id"]:
                event.message_obj.session_id = str(raw_message["user_id"])
            else:
                # 如果无法确定session_id，使用一个默认值
                event.message_obj.session_id = "unknown_session"
    
    @filter.event_message_type(filter.EventMessageType.ALL)
    async def handle_group_request(self, event: AstrMessageEvent):
        """处理群聊申请事件"""
        # 检查是否为请求事件
        if not hasattr(event, "message_obj") or not hasattr(event.message_obj, "raw_message"):
            return
            
        raw_message = event.message_obj.raw_message
        if not raw_message or not isinstance(raw_message, dict):
            return
        
        # 检查是否为群组请求事件
        if raw_message.get("post_type") != "request":
            return
        
        # 确保message_obj有session_id属性
        self.set_session_id(event)
        
        # 处理加群请求
        if raw_message.get("request_type") == "group" and raw_message.get("sub_type") == "add":
            await self.process_group_join_request(event, raw_message)
    
    async def process_group_join_request(self, event: AstrMessageEvent, request_data):
        """处理加群请求"""
        flag = request_data.get("flag", "")
        user_id = request_data.get("user_id", "")
        comment = request_data.get("comment", "")
        group_id = request_data.get("group_id", "")
        
        logger.info(f"收到加群请求: 用户ID={user_id}, 群ID={group_id}, 验证信息={comment}")
        
        # 获取延迟时间
        delay_seconds = self.config.get("delay_seconds", 0)
        
        # 自动处理逻辑
        if self.config["auto_accept"]:
            if delay_seconds > 0:
                logger.info(f"将在 {delay_seconds} 秒后自动同意用户 {user_id} 加入群 {group_id} 的请求")
                await asyncio.sleep(delay_seconds)
            await self.approve_request(event, flag, True)
            logger.info(f"自动同意用户 {user_id} 加入群 {group_id} 的请求")
            return
        
        if self.config["auto_reject"]:
            if delay_seconds > 0:
                logger.info(f"将在 {delay_seconds} 秒后自动拒绝用户 {user_id} 加入群 {group_id} 的请求")
                await asyncio.sleep(delay_seconds)
            await self.approve_request(event, flag, False, self.config["reject_reason"])
            logger.info(f"自动拒绝用户 {user_id} 加入群 {group_id} 的请求")
            return
        
        # 根据关键词处理，优先检查拒绝关键词
        # 先检查是否包含拒绝关键词
        for keyword in self.config["reject_keywords"]:
            if keyword.lower() in comment.lower():
                if delay_seconds > 0:
                    logger.info(f"将在 {delay_seconds} 秒后根据关键词 '{keyword}' 拒绝用户 {user_id} 加入群 {group_id} 的请求")
                    await asyncio.sleep(delay_seconds)
                await self.approve_request(event, flag, False, self.config["reject_reason"])
                logger.info(f"根据关键词 '{keyword}' 拒绝用户 {user_id} 加入群 {group_id} 的请求")
                return
        
        # 再检查是否包含接受关键词
        for keyword in self.config["accept_keywords"]:
            if keyword.lower() in comment.lower():
                if delay_seconds > 0:
                    logger.info(f"将在 {delay_seconds} 秒后根据关键词 '{keyword}' 同意用户 {user_id} 加入群 {group_id} 的请求")
                    await asyncio.sleep(delay_seconds)
                await self.approve_request(event, flag, True)
                logger.info(f"根据关键词 '{keyword}' 同意用户 {user_id} 加入群 {group_id} 的请求")
                return
        
        # 如果没有匹配到关键词，不做任何处理，等待手动审核
        logger.info(f"用户 {user_id} 加入群 {group_id} 的请求未匹配到关键词，等待手动审核")
        return
    
    async def approve_request(self, event: AstrMessageEvent, flag, approve=True, reason=""):
        """同意或拒绝请求"""
        try:
            # 确保message_obj有session_id属性
            self.set_session_id(event)
            
            # 检查是否为aiocqhttp平台
            if event.get_platform_name() == "aiocqhttp":
                # 使用NapCat API格式
                from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import AiocqhttpMessageEvent
                assert isinstance(event, AiocqhttpMessageEvent)
                client = event.bot
                
                # 创建ApifoxModel实例
                api_model = ApifoxModel(
                    approve=approve,
                    flag=flag,
                    reason=reason
                )
                
                # 调用NapCat API
                payloads = {
                    "flag": api_model.flag,
                    "sub_type": "add",
                    "approve": api_model.approve,
                    "reason": api_model.reason if api_model.reason else ""
                }
                
                await client.call_action('set_group_add_request', **payloads)
                return True
            # 兼容其他平台的处理方式
            elif event.bot and hasattr(event.bot, "call_action"):
                await event.bot.call_action(
                    "set_group_add_request",
                    flag=flag,
                    sub_type="add",
                    approve=approve,
                    reason=reason
                )
                return True
            return False
        except Exception as e:
            logger.error(f"处理群聊申请失败: {e}")
            return False
    
    async def terminate(self):
        """插件被卸载/停用时调用"""
        logger.info("群聊申请审核插件已停用")
