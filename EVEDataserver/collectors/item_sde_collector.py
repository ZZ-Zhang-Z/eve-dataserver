# item_sde_collector.py
# 从 EVE 官方 SDE（Static Data Export，静态数据导出）一次性导入静态数据：
#   - 物品基础信息 / 属性效果 / 市场分组 → eve_items.db
#   - 星系 / 星域 / 星座（universe）      → eve_universe.db
#
# 与逐条请求 ESI（/universe/types/{id} 约 5.3 万次、/universe/systems/{id} 约 8 千次，
# 均受 ESI 限流）相比，SDE 是官方一次性打包的 zip，下载不走 ESI 限流，导入速度快得多。
# 本脚本写入结构与现有采集器保持一致：
#   items(type_id, name, description, group_id, market_group_id, published, mass, volume,
#         capacity, portion_size, radius, graphic_id, icon_id, packaged_volume)
#   item_attributes(type_id, attribute_id, value)
#   item_effects(type_id, effect_id, is_default)
#   market_groups(market_group_id, name, description, parent_group_id)
#   market_group_items(market_group_id, type_id)  # 由 items.market_group_id 派生
#   regions(region_id, name, description, updated_at)
#   region_constellations(region_id, constellation_id)   # 由 region.constellationIDs 派生
#   constellations(constellation_id, name, region_id, position_x/y/z, updated_at)
#   constellation_systems(constellation_id, system_id)   # 由 constellation.solarSystemIDs 派生
#   systems(system_id, name, constellation_id, position_x/y/z, security_status,
#           security_class, star_id, updated_at)
#
# 用法：
#   python item_sde_collector.py            # 全量导入
#   python item_sde_collector.py --limit 500  # 仅导入前 500 条（用于小范围验证）
import io
import json
import logging
import os
import sys
import time
import urllib.error
import urllib.request
import zipfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))  # 自包含副本：置顶以优先于项目根的同名模块

import paths
from database_manager import get_connection_by_table

# 复用公共条件请求缓存（按 url 存 ETag/Last-Modified），避免重复下载 ~95MB 的 zip
from esi_client import HttpCache, get_user_agent

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 官方 SDE 最新版简易地址（会 302 跳转到带 build 号的固定地址）
SDE_LATEST_URL = "https://developers.eveonline.com/static-data/eve-online-static-data-latest-jsonl.zip"

# 本地缓存 zip 与元数据目录（位于 data/ 下，已被 .gitignore 忽略）
SDE_CACHE_DIR = os.path.join(paths.DATA_DIR, 'sde')
SDE_ZIP_PATH = os.path.join(SDE_CACHE_DIR, 'sde_latest.zip')
SDE_META_PATH = os.path.join(SDE_CACHE_DIR, 'sde_latest.meta.json')

# 文本语言：与现有 ESI 采集（Accept-Language: zh）保持一致，使用中文，缺失时回退英文
TEXT_LANGUAGE = "zh"

BATCH_SIZE = 500          # 每批写入 items 的类型数量
DOGMA_BATCH_TYPES = 200   # 每批处理属性/效果的类型数量


# ---------------------------------------------------------------------------
# 下载与缓存
# ---------------------------------------------------------------------------

def _load_meta():
    try:
        with open(SDE_META_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _save_meta(meta):
    try:
        with open(SDE_META_PATH, 'w', encoding='utf-8') as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
    except OSError as exc:
        logger.warning("写入 SDE 元数据失败: %s", exc)


def _download_sde():
    """下载最新 SDE zip；若本地已是最新（304）则复用本地缓存。

    返回本地 zip 路径。
    """
    os.makedirs(SDE_CACHE_DIR, exist_ok=True)
    meta = _load_meta()
    headers = {"User-Agent": get_user_agent()}
    if meta.get('etag'):
        headers['If-None-Match'] = meta['etag']

    request = urllib.request.Request(SDE_LATEST_URL, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=120) as resp:
            etag = resp.headers.get('ETag')
            last_modified = resp.headers.get('Last-Modified')
            total = int(resp.headers.get('Content-Length') or 0)
            logger.info("开始下载 SDE zip（%.1f MB）...", total / 1048576 if total else 0)
            tmp_path = SDE_ZIP_PATH + '.part'
            downloaded = 0
            last_log = time.time()
            with open(tmp_path, 'wb') as out:
                while True:
                    chunk = resp.read(1 << 20)
                    if not chunk:
                        break
                    out.write(chunk)
                    downloaded += len(chunk)
                    if time.time() - last_log >= 3:
                        if total:
                            logger.info("下载进度 %d%%（%.1f/%.1f MB）",
                                        downloaded * 100 // total,
                                        downloaded / 1048576, total / 1048576)
                        else:
                            logger.info("已下载 %.1f MB", downloaded / 1048576)
                        last_log = time.time()
            os.replace(tmp_path, SDE_ZIP_PATH)
        _save_meta({'etag': etag, 'last_modified': last_modified,
                    'downloaded_at': time.strftime('%Y-%m-%d %H:%M:%S'),
                    'size': os.path.getsize(SDE_ZIP_PATH)})
        logger.info("SDE zip 下载完成: %s（%.1f MB）", SDE_ZIP_PATH,
                    os.path.getsize(SDE_ZIP_PATH) / 1048576)
    except urllib.error.HTTPError as exc:
        if exc.code == 304:
            logger.info("SDE 未变化（304 Not Modified），复用本地缓存: %s", SDE_ZIP_PATH)
        else:
            raise
    return SDE_ZIP_PATH


# ---------------------------------------------------------------------------
# 解析与写库
# ---------------------------------------------------------------------------

def _localized(value, lang=TEXT_LANGUAGE):
    """从 SDE 的多语言字典中取指定语言文本，缺失时回退英文。"""
    if isinstance(value, dict):
        return value.get(lang) or value.get('en')
    return value


def _find_member(zf, basename):
    for name in zf.namelist():
        if os.path.basename(name).lower() == basename.lower():
            return name
    raise KeyError(f"SDE zip 中找不到成员: {basename}")


def _count_lines(zf, member):
    """快速统计 zip 成员的行数（二进制计数换行，用于进度百分比）。"""
    count = 0
    with zf.open(member) as f:
        for buf in iter(lambda: f.read(1 << 20), b''):
            count += buf.count(b'\n')
    return count


def _iter_jsonl(zf, member):
    with zf.open(member) as f:
        for line in io.TextIOWrapper(f, encoding='utf-8'):
            line = line.strip()
            if line:
                yield json.loads(line)


def init_database():
    """确保各表存在（结构与其他采集器保持一致）。"""
    conn = get_connection_by_table('items')
    cursor = conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL;")
    cursor.execute("PRAGMA synchronous=NORMAL;")
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS items (
            type_id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            group_id INTEGER,
            market_group_id INTEGER,
            published BOOLEAN NOT NULL,
            mass REAL,
            volume REAL,
            capacity REAL,
            portion_size INTEGER,
            radius REAL,
            graphic_id INTEGER,
            icon_id INTEGER,
            packaged_volume REAL
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS item_attributes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type_id INTEGER NOT NULL,
            attribute_id INTEGER NOT NULL,
            value REAL NOT NULL
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS item_effects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type_id INTEGER NOT NULL,
            effect_id INTEGER NOT NULL,
            is_default BOOLEAN NOT NULL
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS market_groups (
            market_group_id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            parent_group_id INTEGER
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS market_group_items (
            market_group_id INTEGER NOT NULL,
            type_id INTEGER NOT NULL,
            PRIMARY KEY (market_group_id, type_id)
        )
    ''')
    conn.commit()
    logger.info("items 数据库初始化完成")


def _build_item_row(rec):
    """把 types.jsonl 记录映射为 items 行（SDE 使用驼峰字段名）。"""
    name = _localized(rec.get('name'))
    if not name:
        return None
    return (
        rec.get('_key'),
        name,
        _localized(rec.get('description')),
        rec.get('groupID'),
        rec.get('marketGroupID'),
        bool(rec.get('published', False)),
        rec.get('mass'),
        rec.get('volume'),
        rec.get('capacity'),
        rec.get('portionSize'),
        rec.get('radius'),
        rec.get('graphicID'),
        rec.get('iconID'),
        rec.get('packagedVolume'),
    )


ITEMS_SQL = '''
    INSERT OR REPLACE INTO items
    (type_id, name, description, group_id, market_group_id, published,
     mass, volume, capacity, portion_size, radius, graphic_id, icon_id, packaged_volume)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
'''

ATTRIBUTES_SQL = '''
    INSERT OR REPLACE INTO item_attributes (type_id, attribute_id, value)
    VALUES (?, ?, ?)
'''

EFFECTS_SQL = '''
    INSERT OR REPLACE INTO item_effects (type_id, effect_id, is_default)
    VALUES (?, ?, ?)
'''

MARKET_GROUPS_SQL = '''
    INSERT OR REPLACE INTO market_groups (market_group_id, name, description, parent_group_id)
    VALUES (?, ?, ?, ?)
'''

MARKET_GROUP_ITEMS_SQL = '''
    INSERT OR REPLACE INTO market_group_items (market_group_id, type_id)
    VALUES (?, ?)
'''


def import_market_groups(zf, limit=None):
    """导入 marketGroups.jsonl 到 market_groups 表，返回写入数量。"""
    member = _find_member(zf, 'marketGroups.jsonl')
    total = limit if limit else _count_lines(zf, member)
    logger.info("开始导入市场分组，共 %d 个分组", total)

    conn = get_connection_by_table('market_groups')
    cursor = conn.cursor()
    batch = []
    written = 0
    for rec in _iter_jsonl(zf, member):
        gid = rec.get('_key')
        name = _localized(rec.get('name'))
        if gid is None or not name:
            continue
        batch.append((gid, name, _localized(rec.get('description')), rec.get('parentGroupID')))
        if len(batch) >= BATCH_SIZE:
            cursor.executemany(MARKET_GROUPS_SQL, batch)
            conn.commit()
            written += len(batch)
            batch = []
            logger.info("已导入市场分组 %d/%d（%d%%）", written, total, written * 100 // total)
        if limit and written + len(batch) >= limit:
            break
    if batch:
        cursor.executemany(MARKET_GROUPS_SQL, batch)
        conn.commit()
        written += len(batch)
    logger.info("市场分组导入完成，共写入 %d 个分组", written)
    return written


def import_types(zf, limit=None):
    """导入 types.jsonl 到 items 表，并由其 marketGroupID 重建 market_group_items。

    返回写入的物品数量。
    """
    member = _find_member(zf, 'types.jsonl')
    total = limit if limit else _count_lines(zf, member)
    logger.info("开始导入物品基础信息，共 %d 个类型", total)

    conn = get_connection_by_table('items')
    cursor = conn.cursor()

    def flush(item_batch, mg_item_batch, type_ids):
        cursor.executemany(ITEMS_SQL, item_batch)
        # market_group_items 由 items 派生：先删除本批 type_id 的旧关联再写，保证幂等
        placeholders = ','.join('?' * len(type_ids))
        cursor.execute(f'DELETE FROM market_group_items WHERE type_id IN ({placeholders})', type_ids)
        if mg_item_batch:
            cursor.executemany(MARKET_GROUP_ITEMS_SQL, mg_item_batch)
        conn.commit()

    item_batch = []
    mg_item_batch = []
    type_ids = []
    written = 0
    for rec in _iter_jsonl(zf, member):
        row = _build_item_row(rec)
        if row is not None:
            item_batch.append(row)
            type_ids.append(rec.get('_key'))
            mgid = rec.get('marketGroupID')
            if mgid is not None:
                mg_item_batch.append((mgid, rec.get('_key')))
        if len(item_batch) >= BATCH_SIZE:
            flush(item_batch, mg_item_batch, type_ids)
            written += len(item_batch)
            item_batch, mg_item_batch, type_ids = [], [], []
            logger.info("已导入物品 %d/%d（%d%%）", written, total, written * 100 // total)
        if limit and written + len(item_batch) >= limit:
            break
    if item_batch:
        flush(item_batch, mg_item_batch, type_ids)
        written += len(item_batch)
    logger.info("物品基础信息导入完成，共写入 %d 个物品", written)
    return written


def import_dogma(zf, limit=None):
    """导入 typeDogma.jsonl 的属性/效果到 item_attributes、item_effects 表。

    为保持幂等（表无 (type_id, attribute_id) 唯一约束），每批先删除本批涉及
    type_id 的旧行再写入，避免重复累积。
    返回 (属性行数, 效果行数)。
    """
    member = _find_member(zf, 'typeDogma.jsonl')
    total = limit if limit else _count_lines(zf, member)
    logger.info("开始导入物品属性/效果，共 %d 条记录", total)

    conn = get_connection_by_table('items')
    cursor = conn.cursor()
    attr_batch = []
    eff_batch = []
    type_ids = []
    attr_total = 0
    eff_total = 0
    processed = 0

    def flush():
        nonlocal attr_total, eff_total
        if not type_ids:
            return
        placeholders = ','.join('?' * len(type_ids))
        cursor.execute(f'DELETE FROM item_attributes WHERE type_id IN ({placeholders})', type_ids)
        cursor.execute(f'DELETE FROM item_effects WHERE type_id IN ({placeholders})', type_ids)
        if attr_batch:
            cursor.executemany(ATTRIBUTES_SQL, attr_batch)
        if eff_batch:
            cursor.executemany(EFFECTS_SQL, eff_batch)
        conn.commit()
        attr_total += len(attr_batch)
        eff_total += len(eff_batch)

    for rec in _iter_jsonl(zf, member):
        type_id = rec.get('_key')
        if type_id is None:
            continue
        type_ids.append(type_id)
        for attr in rec.get('dogmaAttributes') or []:
            value = attr.get('value')
            if value is not None:
                attr_batch.append((type_id, attr.get('attributeID'), value))
        for eff in rec.get('dogmaEffects') or []:
            eff_batch.append((type_id, eff.get('effectID'), bool(eff.get('isDefault', False))))

        processed += 1
        if len(type_ids) >= DOGMA_BATCH_TYPES:
            flush()
            attr_batch, eff_batch, type_ids = [], [], []
            logger.info("已导入属性/效果 %d/%d（%d%%）", processed, total,
                        processed * 100 // max(total, 1))
        if limit and processed >= limit:
            break

    flush()
    logger.info("属性/效果导入完成，共写入属性 %d 行、效果 %d 行", attr_total, eff_total)
    return attr_total, eff_total


# ---------------------------------------------------------------------------
# universe（星系 / 星域 / 星座）
# ---------------------------------------------------------------------------

REGIONS_SQL = '''
    INSERT OR REPLACE INTO regions (region_id, name, description, updated_at)
    VALUES (?, ?, ?, CURRENT_TIMESTAMP)
'''

REGION_CONSTELLATIONS_SQL = '''
    INSERT OR REPLACE INTO region_constellations (region_id, constellation_id)
    VALUES (?, ?)
'''

CONSTELLATIONS_SQL = '''
    INSERT OR REPLACE INTO constellations
    (constellation_id, name, region_id, position_x, position_y, position_z, updated_at)
    VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
'''

CONSTELLATION_SYSTEMS_SQL = '''
    INSERT OR REPLACE INTO constellation_systems (constellation_id, system_id)
    VALUES (?, ?)
'''

SYSTEMS_SQL = '''
    INSERT OR REPLACE INTO systems
    (system_id, name, constellation_id, position_x, position_y, position_z,
     security_status, security_class, star_id, updated_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
'''


def init_universe_database():
    """确保 universe 各表存在（结构与其他 universe 采集器保持一致）。"""
    conn = get_connection_by_table('regions')
    cursor = conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL;")
    cursor.execute("PRAGMA synchronous=NORMAL;")
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS regions (
            region_id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS region_constellations (
            region_id INTEGER NOT NULL,
            constellation_id INTEGER NOT NULL,
            PRIMARY KEY (region_id, constellation_id)
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS constellations (
            constellation_id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            region_id INTEGER,
            position_x REAL,
            position_y REAL,
            position_z REAL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS constellation_systems (
            constellation_id INTEGER NOT NULL,
            system_id INTEGER NOT NULL,
            PRIMARY KEY (constellation_id, system_id)
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS systems (
            system_id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            constellation_id INTEGER,
            position_x REAL,
            position_y REAL,
            position_z REAL,
            security_status REAL,
            security_class TEXT,
            star_id INTEGER,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    logger.info("universe 数据库初始化完成")


def import_regions(zf, limit=None):
    """导入 mapRegions.jsonl 到 regions，并由 constellationIDs 重建 region_constellations。

    返回写入的星域数量。
    """
    member = _find_member(zf, 'mapRegions.jsonl')
    total = limit if limit else _count_lines(zf, member)
    logger.info("开始导入星域，共 %d 个星域", total)

    conn = get_connection_by_table('regions')
    cursor = conn.cursor()
    batch = []
    rc_batch = []
    region_ids = []
    written = 0

    def flush():
        cursor.executemany(REGIONS_SQL, batch)
        placeholders = ','.join('?' * len(region_ids))
        cursor.execute(f'DELETE FROM region_constellations WHERE region_id IN ({placeholders})', region_ids)
        if rc_batch:
            cursor.executemany(REGION_CONSTELLATIONS_SQL, rc_batch)
        conn.commit()

    for rec in _iter_jsonl(zf, member):
        rid = rec.get('_key')
        name = _localized(rec.get('name'))
        if rid is None or not name:
            continue
        batch.append((rid, name, _localized(rec.get('description'))))
        region_ids.append(rid)
        for cid in rec.get('constellationIDs') or []:
            rc_batch.append((rid, cid))
        if len(batch) >= BATCH_SIZE:
            flush()
            written += len(batch)
            batch, rc_batch, region_ids = [], [], []
            logger.info("已导入星域 %d/%d（%d%%）", written, total, written * 100 // total)
        if limit and written + len(batch) >= limit:
            break
    if batch:
        flush()
        written += len(batch)
    logger.info("星域导入完成，共写入 %d 个星域", written)
    return written


def import_constellations(zf, limit=None):
    """导入 mapConstellations.jsonl 到 constellations，并由 solarSystemIDs 重建 constellation_systems。

    返回写入的星座数量。
    """
    member = _find_member(zf, 'mapConstellations.jsonl')
    total = limit if limit else _count_lines(zf, member)
    logger.info("开始导入星座，共 %d 个星座", total)

    conn = get_connection_by_table('constellations')
    cursor = conn.cursor()
    batch = []
    cs_batch = []
    constellation_ids = []
    written = 0

    def flush():
        cursor.executemany(CONSTELLATIONS_SQL, batch)
        placeholders = ','.join('?' * len(constellation_ids))
        cursor.execute(f'DELETE FROM constellation_systems WHERE constellation_id IN ({placeholders})', constellation_ids)
        if cs_batch:
            cursor.executemany(CONSTELLATION_SYSTEMS_SQL, cs_batch)
        conn.commit()

    for rec in _iter_jsonl(zf, member):
        cid = rec.get('_key')
        name = _localized(rec.get('name'))
        if cid is None or not name:
            continue
        pos = rec.get('position') or {}
        batch.append((cid, name, rec.get('regionID'),
                      pos.get('x'), pos.get('y'), pos.get('z')))
        constellation_ids.append(cid)
        for sid in rec.get('solarSystemIDs') or []:
            cs_batch.append((cid, sid))
        if len(batch) >= BATCH_SIZE:
            flush()
            written += len(batch)
            batch, cs_batch, constellation_ids = [], [], []
            logger.info("已导入星座 %d/%d（%d%%）", written, total, written * 100 // total)
        if limit and written + len(batch) >= limit:
            break
    if batch:
        flush()
        written += len(batch)
    logger.info("星座导入完成，共写入 %d 个星座", written)
    return written


def import_systems(zf, limit=None):
    """导入 mapSolarSystems.jsonl 到 systems 表，返回写入的星系数量。"""
    member = _find_member(zf, 'mapSolarSystems.jsonl')
    total = limit if limit else _count_lines(zf, member)
    logger.info("开始导入星系，共 %d 个星系", total)

    conn = get_connection_by_table('systems')
    cursor = conn.cursor()
    batch = []
    written = 0

    for rec in _iter_jsonl(zf, member):
        sid = rec.get('_key')
        name = _localized(rec.get('name'))
        if sid is None or not name:
            continue
        pos = rec.get('position') or {}
        batch.append((sid, name, rec.get('constellationID'),
                      pos.get('x'), pos.get('y'), pos.get('z'),
                      rec.get('securityStatus'), rec.get('securityClass'),
                      rec.get('starID')))
        if len(batch) >= BATCH_SIZE:
            cursor.executemany(SYSTEMS_SQL, batch)
            conn.commit()
            written += len(batch)
            batch = []
            logger.info("已导入星系 %d/%d（%d%%）", written, total, written * 100 // total)
        if limit and written + len(batch) >= limit:
            break
    if batch:
        cursor.executemany(SYSTEMS_SQL, batch)
        conn.commit()
        written += len(batch)
    logger.info("星系导入完成，共写入 %d 个星系", written)
    return written


def main():
    start_time = time.time()
    limit = None
    for i, arg in enumerate(sys.argv):
        if arg == '--limit' and i + 1 < len(sys.argv):
            limit = int(sys.argv[i + 1])
    if limit:
        logger.info("小范围验证模式：每个数据文件仅导入前 %d 条", limit)

    init_database()
    init_universe_database()

    zip_path = _download_sde()

    with zipfile.ZipFile(zip_path) as zf:
        group_count = import_market_groups(zf, limit=limit)
        item_count = import_types(zf, limit=limit)
        attr_count, eff_count = import_dogma(zf, limit=limit)
        region_count = import_regions(zf, limit=limit)
        constellation_count = import_constellations(zf, limit=limit)
        system_count = import_systems(zf, limit=limit)

    elapsed = time.time() - start_time
    logger.info("SDE 导入全部完成：市场分组 %d、物品 %d、属性 %d、效果 %d、"
                "星域 %d、星座 %d、星系 %d，用时 %.1f 秒",
                group_count, item_count, attr_count, eff_count,
                region_count, constellation_count, system_count, elapsed)


if __name__ == '__main__':
    main()
