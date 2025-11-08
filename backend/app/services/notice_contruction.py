import requests
import re
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session
from typing import List, Dict, Any
from ..models import ConstructionNotice
import logging

logger = logging.getLogger(__name__)

BASE_URL = "https://dig.taipei/Tpdig/PWorkData.aspx"


def scrape_construction_notices(session: Session, max_pages: int = None) -> List[Dict[str, Any]]:
    """
    爬取施工通知資料並返回列表
    
    Args:
        session: 資料庫 session
        max_pages: 最大爬取頁數，None 表示爬取所有頁面
    
    Returns:
        爬取到的資料列表
    """
    http_session = requests.Session()
    all_notices = []
    
    try:
        # Step 1: 先取得首頁
        r = http_session.get(BASE_URL)
        r.encoding = "utf-8"
        soup = BeautifulSoup(r.text, "html.parser")
        
        # 獲取總頁數（如果有限制）
        total_pages = 1
        page_links = soup.select("a[href*='Page$']")
        if page_links:
            page_numbers = []
            for link in page_links:
                match = re.search(r"Page\$(\d+)", link.get('href', ''))
                if match:
                    page_numbers.append(int(match.group(1)))
            if page_numbers:
                total_pages = max(page_numbers)
        
        if max_pages:
            total_pages = min(total_pages, max_pages)
        
        logger.info(f"開始爬取施工通知，共 {total_pages} 頁")
        
        # 爬取每一頁
        for page_num in range(1, total_pages + 1):
            logger.info(f"正在爬取第 {page_num} 頁...")
            
            # Step 2: 擷取整個 <form> 中所有欄位
            form_data = {}
            for inp in soup.select("form input"):
                name = inp.get("name")
                value = inp.get("value", "")
                if name:
                    form_data[name] = value
            
            # Step 3: 設置分頁參數
            form_data["__EVENTTARGET"] = "GridView1"
            form_data["__EVENTARGUMENT"] = f"Page${page_num}"
            
            # Step 4: 送出 POST
            resp = http_session.post(BASE_URL, data=form_data)
            resp.encoding = "utf-8"
            soup = BeautifulSoup(resp.text, "html.parser")
            
            # Step 5: 解析結果
            rows = soup.select("tr")[1:]  # 跳過表頭
            for tr in rows:
                tds = tr.select("td")
                if len(tds) >= 4:
                    # 解析欄位
                    date_range = tds[0].text.strip()  # 日期範圍
                    notice_type = tds[1].text.strip()  # 類型
                    unit = tds[2].text.strip()  # 單位
                    name = tds[3].text.strip()  # 名稱/道路
                    
                    # 提取 URL
                    url = None
                    if tds[3].a:
                        onclick = tds[3].a.get('onclick', '')
                        if onclick:
                            match = re.search(r"window\.open\('([^']+)'\)", onclick)
                            if match:
                                url = match.group(1)
                    
                    # 提取道路名稱（從 name 中，如果包含括號）
                    road = None
                    if '(' in name and ')' in name:
                        match = re.search(r'\(([^)]+)\)', name)
                        if match:
                            road = match.group(1)
                    
                    notice_data = {
                        'date_range': date_range if date_range else None,
                        'name': name,
                        'type': notice_type if notice_type else None,
                        'unit': unit if unit else None,
                        'road': road if road else name,  # 如果沒有提取到道路，就用名稱
                        'url': url
                    }
                    all_notices.append(notice_data)
        
        logger.info(f"爬取完成，共 {len(all_notices)} 筆資料")
        return all_notices
        
    except Exception as e:
        logger.error(f"爬取施工通知時發生錯誤: {e}", exc_info=True)
        raise


def save_construction_notices(session: Session, notices: List[Dict[str, Any]], clear_existing: bool = False) -> int:
    """
    將爬取的資料保存到資料庫
    
    Args:
        session: 資料庫 session
        notices: 要保存的資料列表
        clear_existing: 是否先清除現有資料
    
    Returns:
        保存的資料筆數
    """
    try:
        if clear_existing:
            session.query(ConstructionNotice).delete()
            session.commit()
            logger.info("已清除現有資料")
        
        saved_count = 0
        for notice_data in notices:
            # 檢查是否已存在（根據 URL 或 name）
            existing = None
            if notice_data.get('url'):
                existing = session.query(ConstructionNotice).filter(
                    ConstructionNotice.url == notice_data['url']
                ).first()
            elif notice_data.get('name'):
                existing = session.query(ConstructionNotice).filter(
                    ConstructionNotice.name == notice_data['name']
                ).first()
            
            if not existing:
                notice = ConstructionNotice(
                    date_range=notice_data.get('date_range'),
                    name=notice_data['name'],
                    type=notice_data.get('type'),
                    unit=notice_data.get('unit'),
                    road=notice_data.get('road'),
                    url=notice_data.get('url')
                )
                session.add(notice)
                saved_count += 1
        
        session.commit()
        logger.info(f"成功保存 {saved_count} 筆新資料")
        return saved_count
        
    except Exception as e:
        session.rollback()
        logger.error(f"保存資料時發生錯誤: {e}", exc_info=True)
        raise


def update_construction_notices(session: Session, max_pages: int = None, clear_existing: bool = True) -> Dict[str, Any]:
    """
    更新施工通知資料（爬取並保存）
    
    Args:
        session: 資料庫 session
        max_pages: 最大爬取頁數
        clear_existing: 是否先清除現有資料
    
    Returns:
        更新結果
    """
    try:
        notices = scrape_construction_notices(session, max_pages)
        saved_count = save_construction_notices(session, notices, clear_existing)
        return {
            "status": "success",
            "scraped_count": len(notices),
            "saved_count": saved_count
        }
    except Exception as e:
        return {
            "status": "error",
            "message": str(e)
        }
