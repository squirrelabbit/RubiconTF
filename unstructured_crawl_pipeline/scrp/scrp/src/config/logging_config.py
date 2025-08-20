import logging
import os
from logging.handlers import TimedRotatingFileHandler

IS_AZURE = os.getenv("WEBSITE_INSTANCE_ID") is not None

def setup_logging():
    """
    로깅 설정: INFO와 ERROR 로그를 날짜별로 파일에 기록하고, 콘솔에도 출력.

    Returns:
        logging.Logger: 설정된 로거 객체
    """
    LOG_DIR = "/tmp" if IS_AZURE else "./logs"    
    os.makedirs(LOG_DIR, exist_ok=True)

    logger = logging.getLogger("app_logger")
    logger.setLevel(logging.DEBUG)
    
    # 기존 핸들러 제거 (중복 방지)
    if logger.hasHandlers():
        logger.handlers.clear()

    # 공통 포맷터
    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")

    # INFO 로그 핸들러 (날짜별 파일 생성)
    info_log_file = os.path.join(LOG_DIR, "info.log")
    info_handler = TimedRotatingFileHandler(
        info_log_file, when="midnight", interval=1, encoding="utf-8"
    )
    info_handler.suffix = "%Y-%m-%d"  # 파일 이름에 날짜 추가
    info_handler.setLevel(logging.INFO)
    info_handler.setFormatter(formatter)

    # ERROR 로그 핸들러 (날짜별 파일 생성)
    error_log_file = os.path.join(LOG_DIR, "error.log")
    error_handler = TimedRotatingFileHandler(
        error_log_file, when="midnight", interval=1, encoding="utf-8"
    )
    error_handler.suffix = "%Y-%m-%d"  # 파일 이름에 날짜 추가
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(formatter)

    # 로거에 핸들러 추가
    logger.addHandler(info_handler)
    logger.addHandler(error_handler)

    # 콘솔 핸들러 (선택 사항)
    # console_handler = logging.StreamHandler()
    # console_handler.setLevel(logging.DEBUG)
    # console_handler.setFormatter(formatter)
    # logger.addHandler(console_handler)

    return logger