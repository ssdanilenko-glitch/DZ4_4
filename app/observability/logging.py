import structlog
from app.observability.pii import redact_pii

def setup_logging(level: str = "INFO"):
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(ensure_ascii=False),
            # добавляем процессор маскирования перед выводом
            lambda _, __, event_dict: redact_pii(event_dict),
        ],
    )
    # Настройка стандартного логгера (если нужно)
    import logging
    logging.basicConfig(level=getattr(logging, level.upper()))