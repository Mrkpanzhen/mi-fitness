"""常量与配置。"""

from datetime import timedelta, timezone

# region 时区
# 小米健康接口按中国标准时间（UTC+8）切分自然日，且中国自 1991 年起不再使用夏令时，
# 因此固定偏移即可，无需依赖 IANA 时区数据库（Windows 默认不包含）。
CN_TZ = timezone(timedelta(hours=8), name="Asia/Shanghai")
# endregion


# region 小米账号 OAuth 端点
XIAOMI_LOGIN_URL = "https://account.xiaomi.com/pass/serviceLogin"
XIAOMI_LOGIN_AUTH_URL = "https://account.xiaomi.com/pass/serviceLoginAuth2"
XIAOMI_PREFERENCE_URL = "https://account.xiaomi.com/pass/preference"
XIAOMI_PHONE_INFO_URL = "https://account.xiaomi.com/pass/phoneInfo"
XIAOMI_SEND_TICKET_URL = "https://account.xiaomi.com/pass/sendServiceLoginTicket"
XIAOMI_TICKET_AUTH_URL = "https://account.xiaomi.com/pass/serviceLoginTicketAuth"
XIAOMI_QR_LOGIN_URL = "https://account.xiaomi.com/longPolling/loginUrl"
# endregion

# region 服务 SID（serviceLogin 的 sid 参数）
SERVICE_SID_HEALTH = "miothealth"
# endregion

# region STS (安全令牌交换) 端点
STS_HEALTH_URL = "https://sts-hlth.io.mi.com/healthapp/sts"
# endregion

# region API 基础 URL
HEALTH_API_BASE = "https://hlth.io.mi.com"
# endregion

# region 亲友 API 路径
RELATIVES_LIST_PATH = "/app/v1/relatives/get_relative_list"
RELATIVES_LATEST_DATA_PATH = "/app/v1/relatives/get_latest_data"
RELATIVES_AGGREGATED_DATA_PATH = "/app/v1/relatives/get_aggregated_data"
RELATIVES_FITNESS_DATA_PATH = "/app/v1/relatives/get_fitness_data"
RELATIVES_VERIFY_USER_PATH = "/app/v1/relatives/verify_userinfo_by_id"
RELATIVES_SEND_INVITE_PATH = "/app/v1/relatives/send_invite"
RELATIVES_OPERATE_INVITE_PATH = "/app/v1/relatives/operate_invite"
RELATIVES_DELETE_PATH = "/app/v1/relatives/delete_relative"
RELATIVES_GET_SHARED_TYPES_PATH = "/app/v1/relatives/get_shared_data_types"
RELATIVES_GET_APPLIED_SHARED_TYPES_PATH = "/app/v1/relatives/get_applied_shared_data_types"
RELATIVES_GET_FAMILY_MEMBER_PATH = "/app/v1/relatives/get_family_member"
RELATIVES_GET_INVITE_ID_PATH = "/app/v1/relatives/get_invite_unique_id"
RELATIVES_GET_TOPIC_SUBS_PATH = "/app/v1/relatives/get_topic_subscriptions"
# endregion

# region 消息 API 路径
MESSAGE_GET_LIST_PATH = "/app/v1/message/get_msg_list"
MESSAGE_CHECK_NEW_PATH = "/app/v1/message/check_new_msg"
MESSAGE_MODULE_RELATIVES = 1
# endregion

# region 业务错误码
ERR_NOT_RELATIVES = -4002001
ERR_NOT_SHARED_DATA_TYPE = -4002004
ERR_DEVICE_UNTRUST = 70016
# endregion

# region 数据类型 key（用于 get_aggregated_data / get_fitness_data 请求）
DATA_KEY_GOAL = "goal"
DATA_KEY_HEART_RATE = "heart_rate"
DATA_KEY_SLEEP = "sleep"
DATA_KEY_BLOOD_PRESSURE = "blood_pressure"
DATA_KEY_STEPS = "steps"
DATA_KEY_CALORIES = "calories"
DATA_KEY_VALID_STAND = "valid_stand"
DATA_KEY_INTENSITY = "intensity"
DATA_KEY_WEIGHT = "weight"
DATA_KEY_SPO2 = "spo2"
DATA_TAG_DAILY_REPORT = "daily_report"

# 全部受支持的数据类型（顺序即公开 API 中的展示顺序）。
DATA_KEYS: tuple[str, ...] = (
    DATA_KEY_GOAL,
    DATA_KEY_HEART_RATE,
    DATA_KEY_SLEEP,
    DATA_KEY_BLOOD_PRESSURE,
    DATA_KEY_STEPS,
    DATA_KEY_CALORIES,
    DATA_KEY_VALID_STAND,
    DATA_KEY_INTENSITY,
    DATA_KEY_WEIGHT,
    DATA_KEY_SPO2,
)
# endregion

# region 可共享数据类型（send_invite 的 auth_data 全量）
ALL_SHARED_DATA_TYPES: tuple[str, ...] = DATA_KEYS
# endregion

# region verify_userinfo_by_id 的 verify_type 枚举
VERIFY_TYPE_XIAOMI_ID = 1
# endregion

# region HTTP 公共 Header
DEFAULT_USER_AGENT = "Android-12-3.53.1-vivo-V2284A"
DEFAULT_LOGIN_USER_AGENT = (
    "Dalvik/2.1.0 (Linux; U; Android 12; V2284A Build/ab8c0d1.1) "
    "APP/mi.health APPV/353001 MK/VjIyODRB "
    "SDKV/5.3.0.release.68 CPN/com.mi.health PassportSDK/"
)
APP_NAME = "com.mi.health"
REGION_TAG = "cn"
# endregion
