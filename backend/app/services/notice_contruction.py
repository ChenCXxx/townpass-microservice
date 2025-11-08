import requests
import re
import json
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session
from sqlalchemy import or_
from typing import List, Dict, Any, Optional
from datetime import date
from concurrent.futures import ThreadPoolExecutor, as_completed
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
    將 XYSTRING 座標字串轉換為 GeoJSON Point（只取第一個座標點）
    
    Args:
        xystring: 座標字串，格式如 "306329.019,2768888.675,306343.515,2768885.437,..."
    
    Returns:
        GeoJSON Point 格式的字典，如果解析失敗則返回 None
    """
    if not xystring or not xystring.strip():
        return None
    
    try:
        # 只分割並取前兩個座標值（第一個座標點），不解析所有座標
        parts = xystring.split(',')
        if len(parts) < 2:
            logger.warning(f"Invalid coordinate string: not enough values")
            return None
        
        # 只解析第一個座標點 (x, y)
        first_x = float(parts[0].strip())
        first_y = float(parts[1].strip())
        
        # 轉換為 WGS84 座標
        lon, lat = twd97_to_wgs84(first_x, first_y)
        if lon is None or lat is None:
            logger.warning(f"Failed to convert coordinates ({first_x}, {first_y})")
            return None
        
        # 構建 GeoJSON Point
        return {
            "type": "Point",
            "coordinates": [lon, lat]
        }
    except (ValueError, IndexError) as e:
        logger.warning(f"Failed to parse first coordinate from XYSTRING: {e}")
        return None
    except Exception as e:
        logger.error(f"Failed to parse XYSTRING '{xystring}': {e}", exc_info=True)
        return None


def fetch_coordinates_for_case(caseid: str, http_session: requests.Session = None) -> Optional[Dict[str, Any]]:
    """
    從 API 獲取指定 caseid 的座標資料
    
    Args:
        caseid: 案件 ID
        http_session: 可選的 requests.Session 用於連接復用
    
    Returns:
        包含座標資料的字典，如果獲取失敗則返回 None
    """
    if not caseid:
        return None
    
    try:
        url = f"{COORDINATE_API_URL}?cmode=DIGPWORK&caseid={caseid}"
        if http_session:
            response = http_session.get(url, timeout=5)
        else:
            response = requests.get(url, timeout=5)
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


def fetch_geometry_for_notice(notice_data: Dict[str, Any], http_session: requests.Session) -> Optional[Dict[str, Any]]:
    """
    為單個 notice 獲取 geometry（用於並行處理）
    
    Args:
        notice_data: notice 資料字典
        http_session: requests.Session 用於連接復用
    
    Returns:
        (notice_data, geometry) 元組，如果獲取失敗則 geometry 為 None
    """
    caseid = extract_caseid_from_url(notice_data.get('url')) if notice_data.get('url') else None
    if not caseid:
        return None
    
    coord_data = fetch_coordinates_for_case(caseid, http_session)
    if coord_data and coord_data.get('XYSTRING'):
        geometry = parse_xystring_to_geojson(coord_data['XYSTRING'])
        return geometry
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
    將爬取的資料保存到資料庫（優化版本：批量查詢 + 並行獲取座標）
    
    Args:
        session: 資料庫 session
        notices: 要保存的資料列表
        clear_existing: 是否先清除現有資料
    
    Returns:
        保存的資料筆數
    """
    try:
        if clear_existing:
            deleted_count = session.query(ConstructionNotice).count()
            session.query(ConstructionNotice).delete()
            session.commit()
            logger.info(f"已清除現有資料（刪除 {deleted_count} 筆記錄）")
        
        if not notices:
            return 0
        
        total = len(notices)
        logger.info(f"開始處理 {total} 筆資料...")
        
        # 批量查詢所有已存在的記錄（一次性查詢，避免 N+1 問題）
        # 如果 clear_existing=True，此時資料庫應該是空的
        urls = [n.get('url') for n in notices if n.get('url')]
        names = [n.get('name') for n in notices if n.get('name')]
        
        existing_map = {}
        if urls and not clear_existing:  # 如果已清除，跳過查詢（資料庫是空的）
            existing_by_url = session.query(ConstructionNotice).filter(
                ConstructionNotice.url.in_(urls)
            ).all()
            for notice in existing_by_url:
                if notice.url:
                    existing_map[('url', notice.url)] = notice
        
        if names and not clear_existing:  # 如果已清除，跳過查詢（資料庫是空的）
            existing_by_name = session.query(ConstructionNotice).filter(
                ConstructionNotice.name.in_(names)
            ).all()
            for notice in existing_by_name:
                if notice.name:
                    # 优先使用 URL 作为 key，如果没有 URL 或 URL 已存在，则使用 name
                    if notice.url and ('url', notice.url) not in existing_map:
                        existing_map[('url', notice.url)] = notice
                    elif ('name', notice.name) not in existing_map:
                        existing_map[('name', notice.name)] = notice
        
        if clear_existing:
            logger.info(f"已清除模式：所有 {total} 筆都是新記錄，需要獲取座標")
        else:
            logger.info(f"找到 {len(existing_map)} 筆已存在的記錄")
        
        # 找出需要獲取座標的 notices（不存在或沒有 geometry）
        notices_needing_geometry = []
        for idx, notice_data in enumerate(notices):
            key = None
            if notice_data.get('url'):
                key = ('url', notice_data['url'])
            elif notice_data.get('name'):
                key = ('name', notice_data['name'])
            
            existing = existing_map.get(key) if key else None
            if not existing or not existing.geometry:
                notices_needing_geometry.append((idx, notice_data))
        
        logger.info(f"需要獲取座標的記錄: {len(notices_needing_geometry)} 筆")
        
        # 並行獲取座標（使用線程池）
        geometry_map = {}
        if notices_needing_geometry:
            http_session = requests.Session()
            max_workers = min(10, len(notices_needing_geometry))  # 最多 10 個並行請求
            
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                # 提交所有任務
                future_to_idx = {
                    executor.submit(fetch_geometry_for_notice, notice_data, http_session): idx
                    for idx, notice_data in notices_needing_geometry
                }
                
                # 收集結果
                completed = 0
                for future in as_completed(future_to_idx):
                    idx = future_to_idx[future]
                    completed += 1
                    if completed % 10 == 0 or completed == len(notices_needing_geometry):
                        logger.info(f"獲取座標進度: {completed}/{len(notices_needing_geometry)}")
                    
                    try:
                        geometry = future.result()
                        if geometry:
                            geometry_map[idx] = geometry
                    except Exception as e:
                        logger.debug(f"獲取座標失敗 (index {idx}): {e}")
            
            http_session.close()
            logger.info(f"成功獲取 {len(geometry_map)} 筆座標")
        
        # 批量保存資料
        saved_count = 0
        updated_count = 0
        
        for idx, notice_data in enumerate(notices):
            if idx % 50 == 0 and idx > 0:
                session.commit()  # 每 50 筆提交一次，減少內存占用
            
            key = None
            if notice_data.get('url'):
                key = ('url', notice_data['url'])
            elif notice_data.get('name'):
                key = ('name', notice_data['name'])
            
            existing = existing_map.get(key) if key else None
            geometry = geometry_map.get(idx)
            
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
        logger.info(f"成功保存 {saved_count} 筆新資料，更新 {updated_count} 筆座標")
        return saved_count
        
    except Exception as e:
        session.rollback()
        logger.error(f"保存資料時發生錯誤: {e}", exc_info=True)
        raise


def update_missing_geometries(session: Session) -> Dict[str, Any]:
    """
    更新缺少 geometry 的施工通知記錄
    
    Args:
        session: 資料庫 session
    
    Returns:
        包含更新結果的字典
    """
    try:
        # 查詢所有缺少 geometry 的記錄
        # 使用 is_(None) 檢查 NULL，並使用 JSON 函數檢查是否為空物件
        from sqlalchemy import or_
        notices_without_geometry = session.query(ConstructionNotice).filter(
            or_(
                ConstructionNotice.geometry.is_(None),
                ConstructionNotice.geometry == None  # 兼容性檢查
            )
        ).all()
        
        # 過濾掉空字典（PostgreSQL JSON 欄位可能存儲為 {}）
        notices_without_geometry = [
            n for n in notices_without_geometry 
            if n.geometry is None or n.geometry == {} or (isinstance(n.geometry, dict) and len(n.geometry) == 0)
        ]
        
        if not notices_without_geometry:
            return {
                "status": "success",
                "message": "All notices already have geometry",
                "updated_count": 0,
                "failed_count": 0,
                "total": 0
            }
        
        logger.info(f"發現 {len(notices_without_geometry)} 筆缺少 geometry 的記錄，開始更新...")
        
        # 並行獲取座標
        http_session = requests.Session()
        max_workers = min(10, len(notices_without_geometry))
        
        def fetch_geometry_for_existing_notice(notice):
            """為已存在的 notice 獲取 geometry"""
            caseid = extract_caseid_from_url(notice.url) if notice.url else None
            if not caseid:
                return None, None
            
            coord_data = fetch_coordinates_for_case(caseid, http_session)
            if coord_data and coord_data.get('XYSTRING'):
                geometry = parse_xystring_to_geojson(coord_data['XYSTRING'])
                return notice, geometry
            return notice, None
        
        updated_count = 0
        failed_count = 0
        total = len(notices_without_geometry)
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # 提交所有任務
            future_to_notice = {
                executor.submit(fetch_geometry_for_existing_notice, notice): notice
                for notice in notices_without_geometry
            }
            
            # 收集結果並更新
            completed = 0
            for future in as_completed(future_to_notice):
                completed += 1
                if completed % 10 == 0 or completed == total:
                    logger.info(f"更新 geometry 進度: {completed}/{total}")
                
                try:
                    notice, geometry = future.result()
                    if geometry:
                        notice.geometry = geometry
                        session.add(notice)
                        updated_count += 1
                    else:
                        failed_count += 1
                except Exception as e:
                    logger.debug(f"獲取座標失敗: {e}")
                    failed_count += 1
        
        http_session.close()
        session.commit()
        logger.info(f"成功更新 {updated_count} 筆記錄的 geometry，{failed_count} 筆失敗")
        
        return {
            "status": "success",
            "message": f"Updated {updated_count} notices with geometry",
            "updated_count": updated_count,
            "failed_count": failed_count,
            "total": total
        }
        
    except Exception as e:
        session.rollback()
        logger.error(f"更新 geometry 時發生錯誤: {e}", exc_info=True)
        return {
            "status": "error",
            "message": str(e)
        }


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
