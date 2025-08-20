import time
import logging
import numpy as np
from tqdm import tqdm
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from src.config.settings import LANGUAGE
from src.modules.markdown_converter import custom_markdownify
from utils.data_search import IndexBase
from src.modules.load import load_page_with_retry
from src.modules.chunking import run_autochunking
from src.modules.document_intelligence import analyze_document
import json
from src.utils.selenium_util import handle_click, handle_get_attribute, wait_for_element
from utils.log_manager import LogManager

logger = logging.getLogger("app_logger")
    
async def process_page(driver, page, url):
    result_data =[]
    try:
        text_content = await process_elements(json.loads(page['elements']), driver, url)
        
        if text_content:
            category1 = page['category1']
            category2 = page['category2']
            category3 =""
            title = page.get('title', "")
            if page.get("category3", ""):
                if isinstance(page.get("category3",""), list):
                    category3_element = page['category3']
                    type = getattr(By, category3_element['type'].upper())
                    category3_element_node = wait_for_element(driver, type, category3_element['selector'])
                    category3 = category3_element_node.text if category3_element_node.text else category3_element_node.get_attribute('innerText')
                elif isinstance(page.get("category3",""), str):
                    category3 = page.get("category3", "")
                    
            if isinstance(text_content, str):
                try:
                    json_data = IndexBase(
                        title= title if title else driver.title,
                        semantic_title= title if title else driver.title,
                        chunk= text_content,
                        category1= category1,
                        category2= category2,
                        category3= category3,
                        blob_path= url,
                        display_seq= 1 ,
                    )
                    json_data_result = run_autochunking(json_data)
                    for json_result in json_data_result:
                        result_data.append(json_result.to_dict())
                except Exception as e:
                    logger.error(f"Error processing text chunk: {e}")
                    
            elif isinstance(text_content, list):
                for chunk_idx, chunk_from_link in enumerate(text_content):
                    try:
                        json_data = IndexBase(
                            title= chunk_from_link["header"].strip(),
                            chunk= chunk_from_link["chunk"],
                            category1= category1,
                            category2= category2,
                            category3= category3,
                            blob_path= chunk_from_link["blob_path"],
                            display_seq= int(np.int32(chunk_idx + 1)),
                        )
                        json_data_result = run_autochunking(json_data)
                        for json_result in json_data_result:
                            result_data.append(json_result.to_dict())
                    except Exception as e:
                        logger.error(f"Error processing text chunk {chunk_idx}: {e}")

    except Exception as e:
        logger.error(f"Failed to process page: {url}, Error: {e}")
    
    return result_data

async def process_list_page(driver, page, url):
    if LANGUAGE =="KR": text_content_dict = await process_faq_crawler(driver)
    else : text_content_dict = await process_faq_uk_crawler(driver, json.loads(page["elements"]))
    
    result_data =[]
    category_keys = list(text_content_dict.keys())                              
    category1 = page["category1"]
    for idx, key in enumerate(category_keys):
        chunk_result = text_content_dict.get(key)
        if chunk_result:
            try:
                json_data = IndexBase(
                    title= key if key else driver.title,
                    chunk= chunk_result,
                    category1= category1,
                    category2= page.get("category2","") if page.get("category2","") else key,
                    category3= "",
                    blob_path= url,
                    display_seq= int(np.int32(idx + 1)) ,
                )
                json_data_result = run_autochunking(json_data)
                for json_result in json_data_result:
                    result_data.append(json_result.to_dict())
            except Exception as e:
                logger.error(f"Error processing text chunk: {e}")
    
    return result_data

def append_or_merge(html_list, new_item):
    """
    html_list에 new_item을 추가하되,
    blob_path가 같으면 chunk만 합침.
    """
    for item in html_list:
        if item.get("blob_path") == new_item.get("blob_path"):
            # chunk 병합
            if isinstance(item["chunk"], list) and isinstance(new_item["chunk"], list):
                item["chunk"].extend(new_item["chunk"])
            elif isinstance(item["chunk"], list):
                item["chunk"].append(new_item["chunk"])
            else:
                item["chunk"] = [item["chunk"], new_item["chunk"]]
            return
    html_list.append(new_item)
           
async def process_elements(elements, driver, url):
    """
    Processes elements based on their action type and extracts content.
    """
    from .login import login
    html_text =[]
    for element in elements:
        start = element.get('start', None)
        end = element.get('end', None)
        action = element['name']
        type = getattr(By, element['type'].upper())
        if action == 'login':
            login(driver)
        elif action in ['btnclick', 'alink']:
            await wait_for_element(driver, type , element['selector'], timeout=10)
            handle_click(driver,(type, element['selector']))
        elif action == 'wait' :
            await wait_for_element(driver, type, element['selector'])
        elif action == 'crawler':
            new_item = { 
                            "header":driver.title,
                            "blob_path":url,
                            "chunk":
                                await custom_markdownify(
                                    await process_simple_crawler(element, driver, start, end, url),
                                    img_di_flag=element.get("img_di",False), 
                                    pdf_flag=element.get("pdf",False) )
                            }
            html_text = append_or_merge(html_text,new_item)
        elif element["name"] =="link_crawler":
            html_text.extend(await process_link_crawler(element, driver))
    return html_text

async def process_simple_crawler(element, driver, start, end, url):
    html_content = ""
    if element.get("remove_hidden", False):
        script = """
            const elements = document.querySelectorAll('*');
            for (let i = elements.length - 1; i >= 0; i--) {
                const el = elements[i];
                const s = window.getComputedStyle(el);
            if (
                s.display === 'none' ||
                s.visibility === 'hidden' ||
                s.opacity === '0' ||
                el.classList.contains('hidden') ||
                el.classList.contains('blind')
            ) {
                el.remove();
                }
            }
            """
        driver.execute_script(script)

    try:
        if element['type'] == "XPATH":
            if start is None and end is None:
                element_node = await wait_for_element(driver, By.XPATH, element['selector'])
                html_content += await handle_get_attribute(element_node, 'outerHTML', url)
            else:
                for i in range(start, end + 1):
                    xpath = f"{element['selector']}[{i}]"
                    element_node = await wait_for_element(driver, By.XPATH, xpath)
                    html_content += await handle_get_attribute(element_node, 'outerHTML',  url)
        else:
            type = getattr(By, element['type'].upper())
            
            element_node = await wait_for_element(driver, type, element['selector'])
            html_content += await handle_get_attribute(element_node, 'outerHTML',  url)
        
        if html_content:
            soup = BeautifulSoup(html_content, 'html.parser')
            if soup.find_all("nav"):
                for nav in soup.find_all("nav"):
                    nav.decompose()
            
    except TimeoutException as e:
        logger.warning(f"Timeout during crawling for selector {element['selector']}: {e}")
    except NoSuchElementException as e:
        logger.warning(f"Element not found: {element['selector']}: {e}")
    except Exception as e:
        logger.error(f"Unexpected error in process_crawler: {e}")
    return str(soup)

async def process_link_crawler(element, driver):
    try:
        def clean_text(text):
            result = text.replace("\t","").replace("\n"," ")
            return result

        type = getattr(By, element['type'].upper())
        element_node = await wait_for_element(driver, type, element['selector'])
        link_element_list = element_node.find_elements(By.XPATH, ".//a")
        link_url_list = []
        visited_urls = set() 
        original_url = driver.current_url

        for link_element in link_element_list:
            href =link_element.get_attribute("href")
            if href.startswith("javascript:") or href.strip() == "":
                continue
            if href in visited_urls:
                continue
            visited_urls.add(href)  # 방문한 URL 저장
            href = urljoin("www.samsung.com", href)
            link_url_list.append(href)
        
        title_selector = element["title_selector"]
        title_type = getattr(By, title_selector["type"].upper())   # e.g., "CSS_SELECTOR" or "XPATH"
        selector_str = title_selector["selector"]
        element_list = element_node.find_elements(title_type, selector_str)
        category_list = [clean_text(element.get_attribute("innerText")) for element in element_list]
        result = []
        
        for idx, link_url in tqdm(enumerate(link_url_list)):
            await load_page_with_retry(driver, link_url)
            content_selector_list = element.get("content_selector")
            if content_selector_list:
                for content_selector in content_selector_list:
                    type = getattr(By, content_selector['type'].upper())
                    main_element += await wait_for_element(driver, type, content_selector['selector'])
            else:
                main_element = await wait_for_element(driver, By.ID, "content")
                if not main_element:
                    main_element = await wait_for_element(driver, By.ID, "container")
            html = await handle_get_attribute(main_element, "outerHTML", link_url)
            element_dict = {}
            element_dict["title"] = driver.title
            element_dict["header"] = category_list[idx]
            element_dict["blob_path"] = link_url
            element_dict["chunk"] = await custom_markdownify(html, pdf_flag=element.get("pdf",False))
            result.append(element_dict)

        # 작업 편의성을 위해 original site url로 이동
        try:
            driver.get(original_url)
        except Exception as e:
            logger.error(f"Failed to return to the original URL {original_url}: {e}")
        
        return result
    except Exception as e:
        logger.error(e)

async def process_faq_crawler(driver):
    html_content = {}
    soup = BeautifulSoup(driver.page_source, 'html.parser')
    for tag in soup(["script", "style", "header", "footer"]):
        tag.decompose()
    try:
        category_wrap= driver.find_element(By.XPATH,'//*[@id="container"]/div[3]/section/div/div/ul')
        category_tab = category_wrap.find_elements(By.XPATH, './/*[@role="tab"]')
        for tab_idx, tab in enumerate(category_tab):
            handle_click(driver, (By.XPATH, f'//*[@id="container"]/div[3]/section/div/div/ul/li[{tab_idx + 1}]/a'))
            time.sleep(2)
            soup = BeautifulSoup(tab.get_attribute('outerHTML'), 'html.parser')
            title = soup.find('span').text
            paging_area = driver.find_element(By.CLASS_NAME, "paging")
            paging_buttons = paging_area.find_elements(By.XPATH, './ul/li')
            if title =="시스템에어컨":
                html_page_content = ""
                faq_content = driver.find_element(By.CLASS_NAME, "faq-list-wrap")
                soup = BeautifulSoup(faq_content.get_attribute("outerHTML"),'html.parser')
                faq_content_image  = soup.find_all("img")
                for content_img in faq_content_image:
                    image_url= urljoin("https:",content_img["src"])
                    html_page_content += await analyze_document(image_url)
                html_content[title]= html_page_content
            else:
                if len(paging_buttons) >1 : 
                    html_page_content = ""
                    for idx, page in enumerate(paging_buttons):
                        if idx !=0:
                            handle_click(driver, (By.XPATH,  f'//div[contains(@class, "paging")]//a[@data-page="{idx + 1}"]'))
                        #  새로운 FAQ 내용 로드 대기
                        time.sleep(2)
                        # 새로 로드된 FAQ 내용 추가
                        faq_content = await wait_for_element(driver, By.CLASS_NAME, "faq-list-wrap")
                        html_page_content += await custom_markdownify(faq_content.get_attribute('outerHTML'))
                    html_content[title]= html_page_content
                else:
                    # 페이징이 없는 경우 FAQ 내용 추가
                    faq_content = driver.find_element(By.CLASS_NAME, "faq-list-wrap")
                    html_content[title]= await custom_markdownify(faq_content.get_attribute('outerHTML'))
    except Exception as e:
        await LogManager.exception(e,"error occured while crawling faq-kr")
    return html_content

async def process_faq_uk_crawler(driver, elements):
    html_content = {}
    soup = BeautifulSoup(driver.page_source, 'html.parser')
    for tag in soup(["script", "style", "header", "footer"]):
        tag.decompose()
    try:
        faq_content_list = soup.find("div", id=elements[0].get("selector","") ).find_all("div","feature-column-carousel__item")
        for faq_content in faq_content_list:
            html = ""
            title = faq_content.find("h2").text if faq_content.find("h2") else faq_content.find("h4").text
            html += await custom_markdownify(faq_content.text)

            link = urljoin("https://www.samsung.com", (faq_content.find("a")["href"]))
            if link:
                driver.get(link)
                link_soup = BeautifulSoup(driver.page_source, 'html.parser')
                main_area = link_soup.find("div", id="content")  # soup가 아니라 link_soup!
                if not main_area:
                    main_area = link_soup.find("div", id="container")
                if main_area:
                    for tag in main_area(["script", "style", "header", "footer"]):  # 이 라인이 안전해짐
                        tag.decompose()
                    elements_to_remove = [
                        ("nav", None),
                        ("div", {"id": "faq-links"}),
                        ("section", "st-feature-benefit-banner"),
                        ("nav", "breadcrumb"),
                        ("p", "hideInAem"),
                        ("section", "satisfaction-survey"),
                        ("section", "related-questions"),
                    ]
                    for tag, identifier in elements_to_remove:
                        if isinstance(identifier, dict):
                            element = main_area.find(tag, identifier)
                        else:
                            element = main_area.find(tag, class_=identifier) if identifier else main_area.find(tag)
                        if element:
                            element.decompose()
                    html += str(main_area)     
            html_content[title] = await custom_markdownify(html)
    except Exception as e :
        await LogManager.exception(e,"error occured while crawling faq-uk")
    return html_content        