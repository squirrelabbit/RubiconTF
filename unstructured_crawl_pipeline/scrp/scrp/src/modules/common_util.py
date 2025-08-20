import re
from urllib.parse import urlparse, urlunparse,unquote
from bs4 import BeautifulSoup,MarkupResemblesLocatorWarning
import warnings

def clean_url(url):
    parsed_url = urlparse(url)
    # 쿼리 매개변수 제거
    cleaned_url = urlunparse(parsed_url._replace(query=""))
    return cleaned_url

def clean_markdown(text):
    """
    Markdown 데이터를 정리하여 불필요한 문법을 제거하고 텍스트를 반환합니다.
    """
    # Markdown 문법 제거
    text = re.sub(r'\[.*?\]\(.*?\)', '', text)  # 링크 제거
    text = re.sub(r'!\[.*?\]\(.*?\)', '', text)  # 이미지 제거
    text = re.sub(r'[*_~`#>|]', '', text)  # Markdown 스타일 제거
    # 공백 및 줄바꿈 정리
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def clean_text(text):
    warnings.filterwarnings("ignore", category=MarkupResemblesLocatorWarning)
    if not text:
        return ""
    soup = BeautifulSoup(text, "html.parser")
    for a_tag in soup.find_all("a"):
        a_tag.replace_with(a_tag.text)
    return unquote(soup.get_text().strip()).replace("\u200e", "").replace("\u200c", "").replace("\u200b", "").replace("\ufeff", "")

def clean_html_to_text(html):
    soup = BeautifulSoup(html, 'html.parser')
    return soup.get_text(separator=' ', strip=True)