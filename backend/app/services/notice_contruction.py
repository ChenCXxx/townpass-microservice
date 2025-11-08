import requests
import re
import json
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional
from datetime import date
from ..models import ConstructionNotice
import logging

logger = logging.getLogger(__name__)

BASE_URL = "https://dig.taipei/Tpdig/PWorkData.aspx"
COORDINATE_API_URL = "https://dig.taipei/TpdigR.net/Map/caseMap3.ashx"


def extract_caseid_from_url(url: str) -> Optional[str]:
    """
    從 URL 中提取 caseid
    
    Args:
        url: 例如 "https://dig.taipei/TpdigR.net/Map/ShowPWorkData.aspx?caseid=11200814"
    
    Returns:
        caseid 字串，如果提取失敗則返回 None
    """
    if not url:
        return None
    match = re.search(r'caseid=(\d+)', url)
    return match.group(1) if match else None


def twd97_to_wgs84(x: float, y: float) -> tuple[float, float]:
    """
    將 TWD97 座標轉換為 WGS84 經緯度
    
    Args:
        x: TWD97 X 座標
        y: TWD97 Y 座標
    
    Returns:
        (longitude, latitude) 元組
    """
    try:
        # 使用 pyproj 進行座標轉換
        from pyproj import Transformer
        
        # TWD97 / TM2 zone 121 (EPSG:3826) -> WGS84 (EPSG:4326)
        transformer = Transformer.from_crs("EPSG:3826", "EPSG:4326", always_xy=True)
        lon, lat = transformer.transform(x, y)
        return float(lon), float(lat)
    except ImportError:
        logger.warning("pyproj not installed, using approximate conversion")
        # 簡化的近似轉換（不精確，建議安裝 pyproj）
        # TWD97 到 WGS84 的近似轉換
        lon = 121.0 + (x - 250000) / 111320.0
        lat = 24.0 + (y - 2750000) / 110540.0
        return lon, lat
    except Exception as e:
        logger.error(f"Failed to convert coordinates ({x}, {y}): {e}")
        return None, None


def parse_xystring_to_geojson(xystring: str) -> Optional[Dict[str, Any]]:
    """
    將 XYSTRING 座標字串轉換為 GeoJSON Polygon
    
    Args:
        xystring: 座標字串，格式如 "306329.019,2768888.675,306343.515,2768885.437,..."
    
    Returns:
        GeoJSON Polygon 格式的字典，如果解析失敗則返回 None
    """
    if not xystring or not xystring.strip():
        return None
    
    try:
        # 分割座標字串
        coords = [float(c.strip()) for c in xystring.split(',')]
        
        if len(coords) < 6 or len(coords) % 2 != 0:
            logger.warning(f"Invalid coordinate string length: {len(coords)}")
            return None
        
        # 將座標配對成 (x, y) 元組
        twd97_points = []
        for i in range(0, len(coords), 2):
            if i + 1 < len(coords):
                twd97_points.append((coords[i], coords[i + 1]))
        
        if len(twd97_points) < 3:
            logger.warning(f"Not enough points to form a polygon: {len(twd97_points)}")
            return None
        
        # 轉換為 WGS84 座標
        wgs84_points = []
        for x, y in twd97_points:
            lon, lat = twd97_to_wgs84(x, y)
            if lon is not None and lat is not None:
                wgs84_points.append([lon, lat])
        
        if len(wgs84_points) < 3:
            logger.warning(f"Failed to convert enough points: {len(wgs84_points)}")
            return None
        
        # 確保多邊形閉合（第一個點和最後一個點相同）
        if wgs84_points[0] != wgs84_points[-1]:
            wgs84_points.append(wgs84_points[0])
        
        # 構建 GeoJSON Polygon
        return {
            "type": "Polygon",
            "coordinates": [wgs84_points]
        }
    except Exception as e:
        logger.error(f"Failed to parse XYSTRING '{xystring}': {e}", exc_info=True)
        return None


def fetch_coordinates_for_case(caseid: str) -> Optional[Dict[str, Any]]:
    """
    從 API 獲取指定 caseid 的座標資料
    
    Args:
        caseid: 案件 ID
    
    Returns:
        包含座標資料的字典，如果獲取失敗則返回 None
    """
    if not caseid:
        return None
    
    try:
        url = f"{COORDINATE_API_URL}?cmode=DIGPWORK&caseid={caseid}"
        response = requests.get(url, timeout=5)  # 減少超時時間
        response.raise_for_status()
        
        data = response.json()
        if isinstance(data, list) and len(data) > 0:
            return data[0]  # 返回第一個結果
        return None
    except requests.exceptions.Timeout:
        logger.debug(f"Timeout fetching coordinates for caseid {caseid}")
        return None
    except Exception as e:
        logger.debug(f"Failed to fetch coordinates for caseid {caseid}: {e}")
        return None


def parse_roc_date_range(date_range_str: str) -> tuple[date | None, date | None]:
    """
    解析民國年日期範圍字串，轉換為西元年日期
    
    Args:
        date_range_str: 日期範圍字串，格式如 "114/12/01-114/12/31"
    
    Returns:
        (start_date, end_date) 元組，如果解析失敗則返回 (None, None)
    """
    if not date_range_str or not date_range_str.strip():
        return None, None
    
    try:
        # 分割起始和結束日期
        if '-' in date_range_str:
            start_str, end_str = date_range_str.split('-', 1)
            start_str = start_str.strip()
            end_str = end_str.strip()
        else:
            # 如果沒有分隔符，假設是單一日期
            start_str = date_range_str.strip()
            end_str = start_str
        
        def roc_to_gregorian(roc_date_str: str) -> date | None:
            """將民國年日期轉換為西元年日期"""
            # 格式: "114/12/01" -> (114, 12, 01)
            parts = roc_date_str.split('/')
            if len(parts) != 3:
                return None
            
            try:
                roc_year = int(parts[0])
                month = int(parts[1])
                day = int(parts[2])
                
                # 民國年轉西元年: 114 + 1911 = 2025
                gregorian_year = roc_year + 1911
                
                return date(gregorian_year, month, day)
            except (ValueError, IndexError):
                return None
        
        start_date = roc_to_gregorian(start_str)
        end_date = roc_to_gregorian(end_str)
        
        return start_date, end_date
        
    except Exception as e:
        logger.warning(f"Failed to parse date range '{date_range_str}': {e}")
        return None, None


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
            row_count = 0
            for tr in rows:
                tds = tr.select("td")
                if len(tds) >= 4:
                    row_count += 1
                    # 解析欄位
                    date_range_str = tds[0].text.strip()  # 日期範圍字串
                    notice_type = tds[1].text.strip()  # 類型
                    unit = tds[2].text.strip()  # 單位
                    name = tds[3].text.strip()  # 名稱/道路
                    
                    # 解析日期範圍
                    start_date, end_date = parse_roc_date_range(date_range_str)
                    
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
                    
                    # 提取 caseid 並獲取座標（先不獲取，在保存時再獲取以加快速度）
                    # geometry = None
                    # caseid = extract_caseid_from_url(url) if url else None
                    # if caseid:
                    #     coord_data = fetch_coordinates_for_case(caseid)
                    #     if coord_data and coord_data.get('XYSTRING'):
                    #         geometry = parse_xystring_to_geojson(coord_data['XYSTRING'])
                    #         if geometry:
                    #             logger.debug(f"Successfully parsed coordinates for caseid {caseid}")
                    
                    notice_data = {
                        'start_date': start_date,
                        'end_date': end_date,
                        'name': name,
                        'type': notice_type if notice_type else None,
                        'unit': unit if unit else None,
                        'road': road if road else name,  # 如果沒有提取到道路，就用名稱
                        'url': url,
                        'geometry': None  # 稍後在保存時獲取
                    }
                    all_notices.append(notice_data)
            
            logger.info(f"第 {page_num} 頁解析完成，共 {row_count} 筆資料")
        
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
        updated_count = 0
        total = len(notices)
        
        for idx, notice_data in enumerate(notices, 1):
            # 每處理 10 筆顯示一次進度
            if idx % 10 == 0 or idx == total:
                logger.info(f"處理進度: {idx}/{total}")
            
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
            
            # 獲取座標（僅在需要時）
            geometry = None
            if not existing or not existing.geometry:
                caseid = extract_caseid_from_url(notice_data.get('url')) if notice_data.get('url') else None
                if caseid:
                    coord_data = fetch_coordinates_for_case(caseid)
                    if coord_data and coord_data.get('XYSTRING'):
                        geometry = parse_xystring_to_geojson(coord_data['XYSTRING'])
                        if geometry:
                            logger.debug(f"Successfully parsed coordinates for caseid {caseid}")
            
            if not existing:
                notice = ConstructionNotice(
                    start_date=notice_data.get('start_date'),
                    end_date=notice_data.get('end_date'),
                    name=notice_data['name'],
                    type=notice_data.get('type'),
                    unit=notice_data.get('unit'),
                    road=notice_data.get('road'),
                    url=notice_data.get('url'),
                    geometry=geometry
                )
                session.add(notice)
                saved_count += 1
            else:
                # 如果已存在但沒有座標，嘗試更新座標
                if not existing.geometry and geometry:
                    existing.geometry = geometry
                    session.add(existing)
                    updated_count += 1
        
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
