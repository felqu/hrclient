from celery import Celery

from app.core.config import get_settings

settings = get_settings()
celery_app = Celery("hrclient", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.update(task_acks_late=True, task_default_retry_delay=60, task_annotations={"send_application": {"rate_limit": "10/m"}})


@celery_app.task(bind=True, name="send_application", max_retries=3)
def send_application(self, application_id: str) -> None:
    # TODO: load approved application, call HHApplicationGateway asynchronously, update status/event log.
    # Celery retries transient provider/API failures; a durable idempotency key is required.
    raise NotImplementedError(f"Application sending is not implemented: {application_id}")
