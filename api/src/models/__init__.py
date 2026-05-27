# SQLAlchemy 메타데이터에 모든 모델을 등록.
# Celery 워커처럼 FastAPI lifespan 밖에서 실행되는 프로세스는
# 이 모듈을 임포트해 FK 참조 오류를 예방해야 한다.
from api.src.models.anomaly_event import AnomalyEvent  # noqa: F401
from api.src.models.audit_log import AuditLog  # noqa: F401
from api.src.models.budget_threshold import BudgetThreshold  # noqa: F401
from api.src.models.killswitch_state import KillswitchState  # noqa: F401
from api.src.models.knowledge_upload import KnowledgeUpload  # noqa: F401
from api.src.models.model_param_config import ModelParamConfig  # noqa: F401
from api.src.models.prompt_module_config import PromptModuleConfig  # noqa: F401
from api.src.models.notification_queue import NotificationQueue  # noqa: F401
from api.src.models.oauth_identity import OAuthIdentity  # noqa: F401
from api.src.models.qa_feedback import QAFeedback  # noqa: F401
from api.src.models.qa_log import QALog  # noqa: F401
from api.src.models.rebuild_job import RebuildJob  # noqa: F401
from api.src.models.user import User  # noqa: F401
from api.src.models.subscription import Subscription  # noqa: F401
from api.src.models.billing_key import BillingKey  # noqa: F401
from api.src.models.payment import Payment  # noqa: F401
from api.src.models.payment_event import PaymentEvent  # noqa: F401
from api.src.models.refund import Refund  # noqa: F401
from api.src.models.notice import Notice  # noqa: F401
from api.src.models.popup import Popup  # noqa: F401
from api.src.models.inbox_message import InboxMessage  # noqa: F401
from api.src.models.customer_inquiry import CustomerInquiry  # noqa: F401
from api.src.models.inquiry_reply import InquiryReply  # noqa: F401
from api.src.models.inquiry_attachment import InquiryAttachment  # noqa: F401
from api.src.models.admin_board_post import AdminBoardPost  # noqa: F401
from api.src.models.admin_board_comment import AdminBoardComment  # noqa: F401
from api.src.models.admin_grade_page_permission import AdminGradePagePermission  # noqa: F401
from api.src.models.login_event import LoginEvent  # noqa: F401
from api.src.models.user_watch_flag import UserWatchFlag  # noqa: F401
