# webapp/routes/wallet.py
# 钱包相关接口：导入记录、统计、图表数据、记录列表、清空。

import sqlite3

from flask import Blueprint, jsonify, request

from database_manager import get_connection_by_table

bp = Blueprint('wallet', __name__)


@bp.route('/api/wallet/import', methods=['POST'])
def import_wallet_records():
    """导入钱包记录"""
    try:
        data = request.get_json()
        if not data or 'records' not in data:
            return jsonify({"success": False, "error": "无效的请求数据"}), 400

        records_input = data['records']
        print(f"接收到的记录类型: {type(records_input)}")  # 调试信息
        print(f"接收到的记录内容: {records_input}")  # 调试信息

        # 解析钱包记录
        import re
        records = []
        # 正则表达式匹配钱包记录行
        pattern = r'^(\d{4}\.\d{2}\.\d{2} \d{2}:\d{2})[\t\s]+(.*?)[\t\s]+(-?[\d,]+) 星币[\t\s]+([\d,]+) 星币[\t\s]+(.*)$'

        # 处理输入格式：如果是字符串则按行分割，如果是列表则直接使用
        if isinstance(records_input, str):
            if not records_input.strip():
                return jsonify({"success": False, "error": "钱包记录不能为空"}), 400
            lines = records_input.strip().split('\n')
        elif isinstance(records_input, list):
            lines = records_input
        else:
            return jsonify({"success": False, "error": "无效的记录格式"}), 400
        for line in lines:
            line = line.strip()
            if not line:
                continue

            match = re.match(pattern, line)
            if not match:
                print(f"匹配失败的行: '{line}'")  # 调试信息
                continue  # 跳过格式不正确的行

            datetime_str, type_str, amount_str, balance_str, description = match.groups()

            # 处理金额和余额（移除逗号并转换为整数）
            amount = int(amount_str.replace(',', ''))
            balance = int(balance_str.replace(',', ''))

            # 将日期格式从YYYY.MM.DD转换为YYYY-MM-DD
            datetime_str = datetime_str.replace('.', '-')

            records.append((datetime_str, type_str, amount, balance, description))

        if not records:
            return jsonify({"success": False, "error": "没有找到有效的钱包记录"}), 400

        # 插入数据库
        conn = get_connection_by_table('wallet_transactions')
        cursor = conn.cursor()

        imported_count = 0
        skipped_count = 0

        for record in records:
            try:
                cursor.execute('''
                    INSERT INTO wallet_transactions (datetime, type, amount, balance, description)
                    VALUES (?, ?, ?, ?, ?)
                ''', record)
                imported_count += 1
            except sqlite3.IntegrityError:
                skipped_count += 1  # 跳过重复记录

        conn.commit()
        conn.close()

        return jsonify({
            "success": True,
            "imported_count": imported_count,
            "skipped_count": skipped_count
        })

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@bp.route('/api/wallet/stats')
def get_wallet_stats():
    """获取钱包统计数据（支持7天或30天时间范围）"""
    try:
        conn = get_connection_by_table('wallet_transactions')
        cursor = conn.cursor()

        # 获取查询参数
        exclude_contracts = request.args.get('exclude_contracts', 'false').lower() == 'true'
        time_range = request.args.get('time_range', '30')  # 修复：移除.lower()，保持数字字符串

        # 计算日期范围
        from datetime import datetime, timedelta
        if time_range == '7':
            days_ago = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
        else:  # 默认30天
            days_ago = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')

        # 构建查询条件
        where_clause = "datetime >= ?"
        params = [days_ago]

        # 如果需要排除合同相关记录
        if exclude_contracts:
            where_clause += " AND description NOT LIKE '%合同%'"

        # 计算总收入
        cursor.execute(f'SELECT COALESCE(SUM(amount), 0) FROM wallet_transactions WHERE {where_clause} AND amount > 0', params)
        total_income = cursor.fetchone()[0]

        # 计算总支出
        cursor.execute(f'SELECT COALESCE(SUM(ABS(amount)), 0) FROM wallet_transactions WHERE {where_clause} AND amount < 0', params)
        total_expense = cursor.fetchone()[0]

        # 计算总利润
        total_profit = total_income - total_expense

        conn.close()

        return jsonify({
            "total_income": total_income,
            "total_expense": total_expense,
            "total_profit": total_profit,
            "time_range": time_range
        })

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@bp.route('/api/wallet/chart-data')
def get_wallet_chart_data():
    """获取钱包图表数据（支持7天或30天时间范围）"""
    try:
        conn = get_connection_by_table('wallet_transactions')
        cursor = conn.cursor()

        # 获取查询参数
        exclude_contracts = request.args.get('exclude_contracts', 'false').lower() == 'true'
        time_range = request.args.get('time_range', '30')  # 修复：移除.lower()，保持数字字符串

        # 计算日期范围
        from datetime import datetime, timedelta
        if time_range == '7':
            days_ago = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
        else:  # 默认30天
            days_ago = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')

        # 构建查询条件
        where_clause = "datetime >= ?"
        params = [days_ago]

        # 如果需要排除合同相关记录
        if exclude_contracts:
            where_clause += " AND description NOT LIKE '%合同%'"

        # 获取每日收支数据（最近30天）
        cursor.execute(f'''
            SELECT 
                SUBSTR(datetime, 1, 10) as date,
                SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END) as income,
                SUM(CASE WHEN amount < 0 THEN ABS(amount) ELSE 0 END) as expense
            FROM wallet_transactions
            WHERE {where_clause}
            GROUP BY date
            ORDER BY date
        ''', params)
        daily_data = cursor.fetchall()

        daily_dates = [row[0] for row in daily_data]
        daily_income = [row[1] for row in daily_data]
        daily_expense = [row[2] for row in daily_data]

        # 获取收支类型分布（最近30天）
        cursor.execute(f'''
            SELECT 
                type,
                SUM(ABS(amount)) as total_amount
            FROM wallet_transactions
            WHERE {where_clause}
            GROUP BY type
            ORDER BY ABS(total_amount) DESC
            LIMIT 8  -- 只显示前8种类型
        ''', params)
        category_data = cursor.fetchall()

        category_names = [row[0] for row in category_data]
        category_amounts = [abs(row[1]) for row in category_data]  # 使用绝对值

        conn.close()

        return jsonify({
            "daily_dates": daily_dates,
            "daily_income": daily_income,
            "daily_expense": daily_expense,
            "category_names": category_names,
            "category_amounts": category_amounts
        })

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@bp.route('/api/wallet/records')
def get_wallet_records():
    """获取钱包记录"""
    try:
        conn = get_connection_by_table('wallet_transactions')
        cursor = conn.cursor()

        # 获取查询参数
        limit = request.args.get('limit', 20, type=int)
        skip = request.args.get('skip', 0, type=int)
        exclude_contracts = request.args.get('exclude_contracts', 'false').lower() == 'true'
        time_range = request.args.get('time_range', '30')  # 新增：添加time_range参数支持

        # 计算日期范围 - 新增
        from datetime import datetime, timedelta
        if time_range == '7':
            days_ago = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
        else:  # 默认30天
            days_ago = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')

        # 构建查询SQL
        query = '''
            SELECT datetime, type, amount, balance, description
            FROM wallet_transactions
        '''
        params = []

        # 构建WHERE子句 - 修改以支持日期范围和合同排除
        conditions = []
        conditions.append("datetime >= ?")
        params.append(days_ago)

        # 如果需要排除合同相关记录
        if exclude_contracts:
            conditions.append("description NOT LIKE '%合同%'")

        # 添加WHERE子句
        if conditions:
            query += "\nWHERE " + " AND ".join(conditions)

        query += '''
            ORDER BY datetime DESC
            LIMIT ? OFFSET ?
        '''
        params.extend([limit, skip])

        # 执行查询
        cursor.execute(query, params)

        records = []
        for row in cursor.fetchall():
            records.append({
                "datetime": row[0],
                "type": row[1],
                "amount": row[2],
                "balance": row[3],
                "description": row[4]
            })

        conn.close()

        return jsonify(records)

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@bp.route('/api/wallet/clear', methods=['DELETE'])
def clear_wallet_records():
    """清空钱包记录"""
    try:
        conn = get_connection_by_table('wallet_transactions')
        cursor = conn.cursor()

        cursor.execute('DELETE FROM wallet_transactions')
        conn.commit()
        conn.close()

        return jsonify({"success": True})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500