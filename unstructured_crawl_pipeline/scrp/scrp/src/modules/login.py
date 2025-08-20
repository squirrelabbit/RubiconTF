import time
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC 
from src.config.settings import USER, FMUSER
import logging

logger = logging.getLogger("app_logger")

def login(driver):
    url = "https://www.samsung.com/sec/mypage/info/mypetList/" #TO-DO url 가져오기.

    driver.get(url)
    time.sleep(5)

    username_element = WebDriverWait(driver, 10).until(
    EC.presence_of_element_located((By.XPATH, '//*[@id="account"]'))
    )
    username_element.send_keys(USER["id"])

    # Wait until the button is clickable
    next_button = WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable((By.XPATH, "//button[contains(@class, 'MuiButton-containedPrimary') and text()='다음']"))
    )
    next_button.click()

    # 비밀번호 입력 필드에 비밀번호 입력
    # password_element = driver.find_element(By.XPATH, '//*[@id="password"]')  # 비밀번호 입력 필드
    password_element = WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.XPATH, '//*[@id="password"]'))
    )
    password_element.send_keys(USER["pwd"])

    # Wait until the button is clickable
    login_button = WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable((By.XPATH, "//button[contains(@class, 'MuiButton-containedPrimary') and text()='로그인']"))
    )

    login_button.click()

    # 로그인 유지 
    # Wait until the button is clickable
    login_keep_button = WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable((By.XPATH, "//button[contains(@class, 'MuiButton-containedPrimary') and text()='로그인 유지']"))
    )
    login_keep_button.click()

def familynet_login(driver):
    url = "https://familynet.samsung.com/member/indexLogin/" #TO-DO url 가져오기.

    driver.get(url)
    time.sleep(5)
    try:

        username_element = WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.XPATH, '//*[@id="inpUserAccount"]'))
        )
        username_element.send_keys(FMUSER["id"])

        password_element = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, '//*[@id="inpUserPassword"]'))
        )
        password_element.send_keys(FMUSER["pwd"])
        
            # Wait until the button is clickable
        login_button = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, "//button[@id='loginBtn']"))
        )

        login_button.click()
        time.sleep(5)
        

    except Exception as e:
        logger.error(f"Error occured while login: {e}")