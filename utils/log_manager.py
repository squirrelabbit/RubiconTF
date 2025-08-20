from data_cosmos import LogContainer,ErrorLogContainer
import traceback
import uuid
from datetime import datetime
from typing import Dict, Any
import logging
import os

SYSTEM_NAME = os.environ['SYSTEM_NAME']

class LogManager:
    @staticmethod
    def get_log_container():
        return LogContainer()
    
    @staticmethod
    def get_error_log_container():
        return ErrorLogContainer()


    @staticmethod
    async def log(log_data: Dict[str, Any]) -> None:
        """
        Log data to the Cosmos DB.
        :param log_data: A dictionary containing log information.
        """
        log_data["id"] = str(uuid.uuid4())
        log_data["log_date"] = datetime.now().isoformat()

        async with LogManager.get_log_container() as container:
            await container.insert(log_data)

    @staticmethod
    async def info(message: str) -> None:
        """
        Log an info message.
        """
        tb_details = traceback.extract_stack()[:-1]  # Exclude the current function call
        filename, lineno, funcname, _ = tb_details[-1]

        await LogManager.log({
            "level": "INFO",
            "message": message,
            "filename": filename,
            "line": lineno,
            "function": funcname,
            "system_name"  : SYSTEM_NAME
        })
        logging.info(message)

    @staticmethod
    async def error(message: str) -> None:
        """
        Log an error message.
        """
        tb_details = traceback.extract_stack()[:-1]  # Exclude the current function call
        filename, lineno, funcname, _ = tb_details[-1]

        await LogManager.log({
            "level": "ERROR",
            "message": message,
            "filename": filename,
            "line": lineno,
            "function": funcname,
            "system_name"  : SYSTEM_NAME
        })

        logging.error(message)

    @staticmethod
    async def exception(exception: Exception,message = "") -> None:
        """
        Log an exception with its traceback.
        """
        trace = traceback.format_exception(type(exception), exception, exception.__traceback__)
        # Extract the traceback details
        tb_details = traceback.extract_tb(exception.__traceback__)
        filename, lineno, funcname, _ = tb_details[-1]

        log_data = {
            "level": "ERROR",
            "message": str(exception),
            "trace": "".join(trace),
            "filename": filename,
            "line": lineno,
            "function": funcname,
            "message": message,
            "system_name"  : SYSTEM_NAME
        }

        await LogManager.log(log_data)

        async with LogManager.get_error_log_container() as container:
            await container.insert(log_data)

        logging.error(f"{str(exception)}\n{''.join(trace)}")