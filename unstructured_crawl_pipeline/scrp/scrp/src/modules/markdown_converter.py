from markdownify import MarkdownConverter
from src.modules.common_util import clean_url
from urllib.parse import urljoin
class CustomMarkdownConverter(MarkdownConverter):
    def __init__(self, img_di_results=None, pdf_di_results=None, img_di_flag=False, pdf_flag=False, **options):
        super().__init__(**options)
        self.img_di_flag = img_di_flag
        self.pdf_flag = pdf_flag
        self.img_di_results = img_di_results or {}
        self.pdf_di_results = pdf_di_results or {}
        
    def convert_img(self, el, text, convert_as_inline):
        if el.get("class", []) == ["mo"]:
            return ""
        src = ''
        if el.get('data-src-pc', ''): src = el.get('data-src-pc')
        elif el.get('src', ''): src = el.get('src')
        elif el.get('data-desktop-src', ''): src = el.get('data-desktop-src')
        alt = ''
        if el.get('alt', ''): alt = el.get('alt')
        elif el.get('data-desktop-alt', ''): alt = el.get('data-desktop-alt')
        if not alt or not src or src.lower().startswith("javascript"):
            return ""
        if src.startswith("//"):
            src = "https:" + src
        src = clean_url(src)
        if 'image__preview' in el.get('class', []):
            return ''
        di_result = ''
        if self.img_di_flag:
            di_result = self.img_di_results.get(src, '')
        if di_result:
            di_result = '\n### ' + di_result
        return f"![{alt}]({src}){di_result}"
    
    def convert_a(self, el, text, convert_as_inline):
        href = el.get('href', '')
        if not href or href.lower().startswith("javascript"):
            return text.strip() if text else ''
        if href.startswith("//"):
            href = "https:" + href
        href = urljoin("https://samsung.com", href)
        href = clean_url(href)
        text = text.replace("\n", '') if text else ''
        di_result = ''
        if self.pdf_flag and href.endswith(".pdf"):
            di_result = self.pdf_di_results.get(href, '')
        if di_result:
            di_result = '\n### ' + di_result
        return f"[{text}]({href}){di_result}"

from bs4 import BeautifulSoup
import asyncio
from src.modules.document_intelligence import analyze_document
async def prepare_di_results(html_content, img_di_flag=False, pdf_flag=False):
    soup = BeautifulSoup(html_content, 'html.parser')
    img_srcs = set()
    pdf_hrefs = set()
    # 이미지 src 수집
    if img_di_flag:
        for img in soup.find_all('img'):
            src = img.get('data-src-pc') or img.get('src') or img.get('data-desktop-src')
            if src:
                if src.startswith("//"):
                    src = "https:" + src
                img_srcs.add(clean_url(src))
    # PDF 링크 수집
    if pdf_flag:
        for a in soup.find_all('a', href=True):
            href = a['href']
            if href.endswith('.pdf'):
                if href.startswith("//"):
                    href = "https:" + href
                href = urljoin("https://samsung.com", href)
                pdf_hrefs.add(clean_url(href))
    # 비동기로 analyze_document 실행
    img_di_results = {}
    pdf_di_results = {}
    tasks = []
    for src in img_srcs:
        tasks.append(analyze_document(src))
    img_results = await asyncio.gather(*tasks, return_exceptions=True)
    for src, result in zip(img_srcs, img_results):
        if not isinstance(result, Exception):
            img_di_results[src] = result
    tasks = []
    for href in pdf_hrefs:
        tasks.append(analyze_document(href))
    pdf_results = await asyncio.gather(*tasks, return_exceptions=True)
    for href, result in zip(pdf_hrefs, pdf_results):
        if not isinstance(result, Exception):
            pdf_di_results[href] = result
    return img_di_results, pdf_di_results
    
async def custom_markdownify(html_content, img_di_flag=False, pdf_flag=False, **options):
    img_di_results, pdf_di_results = await prepare_di_results(html_content, img_di_flag, pdf_flag)
    converter = CustomMarkdownConverter(
        img_di_results=img_di_results,
        pdf_di_results=pdf_di_results,
        img_di_flag=img_di_flag,
        pdf_flag=pdf_flag,
        **options
    )
    return converter.convert(html_content)