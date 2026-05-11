import logging


def make_logger(name: str, log_file: str) -> logging.Logger:
    """创建 logger，同时写文件和控制台"""
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter('%(asctime)s [%(name)s] %(levelname)s - %(message)s')
    if not logger.handlers:
        logger.addHandler(logging.FileHandler(log_file))
        logger.addHandler(logging.StreamHandler())
    for h in logger.handlers:
        h.setFormatter(fmt)
    return logger
