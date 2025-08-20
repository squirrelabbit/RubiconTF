# scrp/src/utils/selenium_util.py

import asyncio
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, ElementClickInterceptedException


async def wait_for_element(driver, by, selector, timeout=10):
    """
    비동기로 특정 요소가 나타날 때까지 기다림
    """
    loop = asyncio.get_event_loop()
    try:
        return await loop.run_in_executor(
            None,
            lambda: WebDriverWait(driver, timeout).until(
                EC.presence_of_element_located((by, selector))
            )
        )
    except TimeoutException:
        return None


async def handle_click(driver, by, selector, timeout=10):
    """
    비동기 안전 클릭
    """
    loop = asyncio.get_event_loop()
    try:
        # 1. 클릭 전에 오버레이 제거
        await hide_overlay(driver)

        # 2. 요소 대기 후 클릭
        element = await loop.run_in_executor(
            None,
            lambda: WebDriverWait(driver, timeout).until(
                EC.element_to_be_clickable((by, selector))
            )
        )
        await loop.run_in_executor(None, element.click)
        return True
    except (TimeoutException, NoSuchElementException, ElementClickInterceptedException):
        return False



async def handle_get_attribute(driver, by, selector, attribute, timeout=10):
    """
    비동기로 속성값 가져오기
    """
    loop = asyncio.get_event_loop()
    try:
        element = await loop.run_in_executor(
            None,
            lambda: WebDriverWait(driver, timeout).until(
                EC.presence_of_element_located((by, selector))
            )
        )
        return await loop.run_in_executor(None, element.get_attribute, attribute)
    except TimeoutException:
        return None


async def hide_overlay(driver, by=By.CSS_SELECTOR, selector=".overlay, .popup, .modal", timeout=3):
    """
    비동기로 오버레이/팝업 닫기
    """
    loop = asyncio.get_event_loop()
    try:
        elements = await loop.run_in_executor(None, driver.find_elements, by, selector)
        for el in elements:
            try:
                # 닫기 버튼이 있으면 클릭, 아니면 display:none 처리
                await loop.run_in_executor(None, lambda: driver.execute_script("arguments[0].style.display='none';", el))
            except Exception:
                pass
        return True
    except Exception:
        return False
