#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
滚球水位实时监控系统 v6.2
- 修复SSL证书验证问题
- 增强UID提取功能
- 支持手动输入UID
- 使用API方式获取数据
"""

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support. ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium. common.exceptions import TimeoutException, NoSuchElementException
import requests
import urllib3
import xml.etree.ElementTree as ET
import time
import pickle
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import threading
from datetime import datetime
import re
import json
import os

# 禁用SSL警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ================== 配置 ==================
URL = "https://mos055.com/"
API_URL = "https://mos055.com/transform.php"
USERNAME = "LJJ123123"
PASSWORD = "zz66688899"
COOKIES_FILE = "mos055_cookies.pkl"
CONFIG_FILE = "bet_config.json"

# ================== 盘口类型映射 ==================
BET_TYPES_ORDER = ['让球', '大/小', '独赢', '让球上半场', '大/小上半场', '独赢上半场', '下个进球', '双方球队进球']


class BettingAPI:
    """投注API类 - 基于HAR分析"""
    
    def __init__(self):
        self.session = requests.Session()
        self.base_url = API_URL
        self.cookies = {}
        self.uid = ""
        self.langx = "zh-cn"
        
        # 禁用SSL验证
        self.session.verify = False
        
        # 设置请求头
        self. session.headers. update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': '*/*',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'X-Requested-With': 'XMLHttpRequest',
            'Origin': 'https://mos055.com',
            'Referer': 'https://mos055.com/',
            'Connection': 'keep-alive',
        })
    
    def set_cookies(self, cookies_dict):
        """设置cookies"""
        self.cookies = cookies_dict
        self.session.cookies.update(cookies_dict)
        
        # 尝试从cookies提取uid
        uid_keys = ['uid', 'member_id', 'user_id', 'userid', 'memberId', 'memberCode', 'member_code']
        for key in uid_keys: 
            if key in cookies_dict and cookies_dict[key]: 
                val = str(cookies_dict[key])
                if val. isdigit() or (len(val) > 0 and val[0]. isdigit()):
                    self.uid = val
                    break
    
    def set_uid(self, uid):
        """手动设置UID"""
        if uid:
            self.uid = str(uid).strip()
    
    def get_rolling_matches(self, gtype='ft', ltype=3, sorttype='L'):
        """获取滚球比赛列表和赔率数据"""
        try:
            params = {
                'ver': datetime.now().strftime('%Y-%m-%d-mtfix_133')
            }
            
            data = {
                'p': 'get_game_list',
                'uid': self.uid,
                'showtype': 'live',
                'rtype': 'rb',
                'gtype': gtype. upper(),
                'ltype':  ltype,
                'sorttype': sorttype,
                'specialClick': '',
                'langx': self.langx,
                'date': datetime.now().strftime('%Y-%m-%d'),
                'ts': int(time.time() * 1000)
            }
            
            response = self. session.post(
                self.base_url,
                params=params,
                data=data,
                timeout=30,
                verify=False  # 禁用SSL验证
            )
            
            if response.status_code != 200:
                return {
                    'success': False,
                    'error': f'HTTP {response.status_code}',
                    'matches': [],
                    'totalOdds': 0
                }
            
            # 检查是否有错误
            if 'table id error' in response.text. lower():
                return {
                    'success': False,
                    'error': 'UID无效或未设置 (table id error)',
                    'matches': [],
                    'totalOdds': 0,
                    'raw':  response.text[: 200]
                }
            
            # 解析XML响应
            xml_text = response.text
            matches, total_odds = self._parse_match_xml(xml_text)
            
            return {
                'success': True,
                'matches': matches,
                'totalOdds': total_odds,
                'total_count': len(matches),
                'raw_xml': xml_text[: 500] if len(xml_text) > 500 else xml_text,
                'timestamp': datetime.now().isoformat()
            }
            
        except requests.exceptions.SSLError as e:
            return {
                'success': False,
                'error': f'SSL错误: {str(e)[: 100]}',
                'matches': [],
                'totalOdds': 0
            }
        except requests. exceptions.ConnectionError as e:
            return {
                'success': False,
                'error': f'连接错误: {str(e)[:100]}',
                'matches': [],
                'totalOdds':  0
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'matches':  [],
                'totalOdds': 0
            }
    
    def _parse_match_xml(self, xml_text):
        """解析比赛XML数据"""
        matches = []
        total_odds = 0
        
        try:
            # 清理XML
            xml_text = re.sub(r'<\?xml[^>]+\?>', '', xml_text)
            xml_text = xml_text.strip().lstrip('\ufeff')
            
            if not xml_text or '<game' not in xml_text. lower():
                return matches, total_odds
            
            root = ET.fromstring(xml_text)
            current_league = ""
            
            # 遍历所有game节点
            for game in root. findall('. //game'):
                match = self._extract_match_data(game)
                if match: 
                    league = self._get_text(game, 'league')
                    if league: 
                        current_league = league
                    match['league'] = current_league
                    
                    match_odds = self._count_match_odds(match)
                    total_odds += match_odds
                    
                    matches.append(match)
                    
        except ET.ParseError as e:
            print(f"XML解析错误: {e}")
            matches = self._fallback_parse(xml_text)
        except Exception as e:
            print(f"解析错误: {e}")
        
        return matches, total_odds
    
    def _extract_match_data(self, game_node):
        """从game节点提取完整数据"""
        try:
            match = {
                'gid': self._get_text(game_node, 'gid'),
                'league': self._get_text(game_node, 'league', '未知联赛'),
                'team1': self._get_text(game_node, 'team_h'),
                'team2': self._get_text(game_node, 'team_c'),
                'score1': self._get_text(game_node, 'SCORE_H', '0'),
                'score2': self._get_text(game_node, 'SCORE_C', '0'),
                'time': self._get_text(game_node, 'RETIMESET', ''),
                'is_rolling': self._get_text(game_node, 'IS_RB') == 'Y',
                'odds': {bt: {'handicap': '', 'home': [], 'away': [], 'draw': []} for bt in BET_TYPES_ORDER}
            }
            
            # 提取原始赔率数据
            raw = {
                'handicap_ratio': self._get_text(game_node, 'RATIO_RE'),
                'handicap_home': self._parse_odds(self._get_text(game_node, 'IOR_REH')),
                'handicap_away': self._parse_odds(self._get_text(game_node, 'IOR_REC')),
                'ou_ratio': self._get_text(game_node, 'RATIO_ROUH'),
                'over':  self._parse_odds(self._get_text(game_node, 'IOR_ROUH')),
                'under': self._parse_odds(self._get_text(game_node, 'IOR_ROUC')),
                'ml_home': self._parse_odds(self._get_text(game_node, 'IOR_RMH')),
                'ml_away': self._parse_odds(self._get_text(game_node, 'IOR_RMC')),
                'ml_draw': self._parse_odds(self._get_text(game_node, 'IOR_RMN')),
                'half_handicap_ratio': self._get_text(game_node, 'RATIO_HRE'),
                'half_handicap_home': self._parse_odds(self._get_text(game_node, 'IOR_HREH')),
                'half_handicap_away': self._parse_odds(self._get_text(game_node, 'IOR_HREC')),
                'half_ou_ratio': self._get_text(game_node, 'RATIO_HROUH'),
                'half_over': self._parse_odds(self._get_text(game_node, 'IOR_HROUH')),
                'half_under': self._parse_odds(self._get_text(game_node, 'IOR_HROUC')),
                'half_ml_home': self._parse_odds(self._get_text(game_node, 'IOR_HRMH')),
                'half_ml_away': self._parse_odds(self._get_text(game_node, 'IOR_HRMC')),
                'half_ml_draw': self._parse_odds(self._get_text(game_node, 'IOR_HRMN')),
            }
            
            # 让球
            match['odds']['让球']['handicap'] = raw['handicap_ratio']
            if raw['handicap_home'] > 0:
                match['odds']['让球']['home']. append({
                    'value': raw['handicap_home'], 'text': str(raw['handicap_home']),
                    'wtype': 'RE', 'rtype': 'REH', 'chose_team': 'H'
                })
            if raw['handicap_away'] > 0:
                match['odds']['让球']['away'].append({
                    'value': raw['handicap_away'], 'text':  str(raw['handicap_away']),
                    'wtype': 'RE', 'rtype': 'REC', 'chose_team': 'C'
                })
            
            # 大小
            match['odds']['大/小']['handicap'] = raw['ou_ratio']
            if raw['over'] > 0:
                match['odds']['大/小']['home'].append({
                    'value': raw['over'], 'text': str(raw['over']),
                    'wtype': 'ROU', 'rtype': 'ROUH', 'chose_team': 'H'
                })
            if raw['under'] > 0:
                match['odds']['大/小']['away']. append({
                    'value':  raw['under'], 'text':  str(raw['under']),
                    'wtype': 'ROU', 'rtype':  'ROUC', 'chose_team': 'C'
                })
            
            # 独赢
            if raw['ml_home'] > 0:
                match['odds']['独赢']['home'].append({
                    'value': raw['ml_home'], 'text': str(raw['ml_home']),
                    'wtype': 'RM', 'rtype': 'RMH', 'chose_team': 'H'
                })
            if raw['ml_away'] > 0:
                match['odds']['独赢']['away'].append({
                    'value': raw['ml_away'], 'text': str(raw['ml_away']),
                    'wtype': 'RM', 'rtype': 'RMC', 'chose_team': 'C'
                })
            if raw['ml_draw'] > 0:
                match['odds']['独赢']['draw'].append({
                    'value': raw['ml_draw'], 'text':  str(raw['ml_draw']),
                    'wtype':  'RM', 'rtype': 'RMN', 'chose_team': 'N'
                })
            
            # 上半场让球
            match['odds']['让球上半场']['handicap'] = raw['half_handicap_ratio']
            if raw['half_handicap_home'] > 0:
                match['odds']['让球上半场']['home'].append({
                    'value': raw['half_handicap_home'], 'text': str(raw['half_handicap_home']),
                    'wtype': 'HRE', 'rtype':  'HREH', 'chose_team': 'H'
                })
            if raw['half_handicap_away'] > 0:
                match['odds']['让球上半场']['away'].append({
                    'value': raw['half_handicap_away'], 'text': str(raw['half_handicap_away']),
                    'wtype': 'HRE', 'rtype': 'HREC', 'chose_team':  'C'
                })
            
            # 上半场大小
            match['odds']['大/小上半场']['handicap'] = raw['half_ou_ratio']
            if raw['half_over'] > 0:
                match['odds']['大/小上半场']['home'].append({
                    'value': raw['half_over'], 'text': str(raw['half_over']),
                    'wtype': 'HROU', 'rtype': 'HROUH', 'chose_team': 'H'
                })
            if raw['half_under'] > 0:
                match['odds']['大/小上半场']['away'].append({
                    'value': raw['half_under'], 'text':  str(raw['half_under']),
                    'wtype':  'HROU', 'rtype': 'HROUC', 'chose_team':  'C'
                })
            
            # 上半场独赢
            if raw['half_ml_home'] > 0:
                match['odds']['独赢上半场']['home']. append({
                    'value':  raw['half_ml_home'], 'text': str(raw['half_ml_home']),
                    'wtype': 'HRM', 'rtype': 'HRMH', 'chose_team': 'H'
                })
            if raw['half_ml_away'] > 0:
                match['odds']['独赢上半场']['away'].append({
                    'value': raw['half_ml_away'], 'text': str(raw['half_ml_away']),
                    'wtype': 'HRM', 'rtype': 'HRMC', 'chose_team':  'C'
                })
            if raw['half_ml_draw'] > 0:
                match['odds']['独赢上半场']['draw'].append({
                    'value': raw['half_ml_draw'], 'text': str(raw['half_ml_draw']),
                    'wtype': 'HRM', 'rtype': 'HRMN', 'chose_team': 'N'
                })
            
            return match
            
        except Exception as e:
            print(f"提取比赛数据错误: {e}")
            return None
    
    def _get_text(self, node, tag, default=''):
        """安全获取节点文本"""
        elem = node.find(tag)
        if elem is not None and elem.text:
            return elem.text.strip()
        return default
    
    def _parse_odds(self, odds_str):
        """解析赔率字符串为浮点数"""
        try:
            if not odds_str:
                return 0.0
            val = float(odds_str)
            if val > 50:
                val = val / 100
            return round(val, 2)
        except:
            return 0.0
    
    def _count_match_odds(self, match):
        """统计单场比赛的水位数"""
        count = 0
        for bet_type, type_odds in match. get('odds', {}).items():
            count += len(type_odds. get('home', []))
            count += len(type_odds. get('away', []))
            count += len(type_odds. get('draw', []))
        return count
    
    def _fallback_parse(self, xml_text):
        """备用解析方法"""
        matches = []
        gid_pattern = r'<gid>(\d+)</gid>'
        team_h_pattern = r'<team_h>([^<]+)</team_h>'
        team_c_pattern = r'<team_c>([^<]+)</team_c>'
        
        gids = re.findall(gid_pattern, xml_text)
        teams_h = re.findall(team_h_pattern, xml_text)
        teams_c = re.findall(team_c_pattern, xml_text)
        
        for i, gid in enumerate(gids):
            if i < len(teams_h) and i < len(teams_c):
                matches.append({
                    'gid': gid,
                    'team1': teams_h[i],
                    'team2': teams_c[i],
                    'league': '未知联赛',
                    'score1': '0',
                    'score2': '0',
                    'time': '',
                    'odds': {bt: {'handicap': '', 'home': [], 'away': [], 'draw': []} for bt in BET_TYPES_ORDER}
                })
        
        return matches
    
    def place_bet(self, gid, wtype, rtype, chose_team, ioratio, gold, gtype='FT'):
        """提交下注"""
        try:
            params = {'ver': datetime.now().strftime('%Y-%m-%d-mtfix_133')}
            
            data = {
                'p': 'FT_bet',
                'golds': gold,
                'gid': gid,
                'gtype': gtype,
                'wtype': wtype,
                'rtype': rtype,
                'chose_team': chose_team,
                'ioratio': ioratio,
                'autoOdd': 'Y',
                'isRB': 'Y',
                'uid': self.uid,
                'langx': self.langx,
                'ts': int(time.time() * 1000)
            }
            
            response = self.session.post(
                self.base_url, 
                params=params, 
                data=data, 
                timeout=15,
                verify=False
            )
            
            if response.status_code != 200:
                return {'success': False, 'error':  f'HTTP {response.status_code}', 'raw': response.text}
            
            try:
                root = ET.fromstring(response. text)
                code = root.findtext('. //code', '').lower()
                
                if code == 'success':
                    return {
                        'success': True,
                        'ticket_id': root.findtext('.//ticket_id', ''),
                        'bet_amount': float(root.findtext('.//gold', '0')),
                        'odds': float(root.findtext('.//ioratio', '0')),
                        'balance': float(root.findtext('. //nowcredit', '0')),
                        'message': '下注成功',
                        'raw': response.text
                    }
                else:
                    return {
                        'success': False,
                        'error': root.findtext('.//message', '下注失败'),
                        'raw': response.text
                    }
            except: 
                if 'success' in response.text. lower():
                    return {'success': True, 'message': '下注成功（备用解析）', 'raw': response.text}
                return {'success': False, 'error': '解析响应失败', 'raw':  response.text}
            
        except Exception as e: 
            return {'success': False, 'error': str(e)}
    
    def get_today_bets(self):
        """获取今日注单"""
        try:
            params = {'ver': datetime.now().strftime('%Y-%m-%d-mtfix_133')}
            data = {
                'p': 'get_today_wagers',
                'uid': self.uid,
                'langx': self.langx,
                'ts': int(time.time() * 1000)
            }
            
            response = self.session.post(
                self.base_url, 
                params=params, 
                data=data, 
                timeout=10,
                verify=False
            )
            
            try:
                json_data = json.loads(response.text)
                bets = []
                total_gold = 0.0
                
                if 'wagers' in json_data: 
                    for wager in json_data['wagers']:
                        bet = {
                            'w_id': wager. get('w_id', ''),
                            'gid': wager.get('gid', ''),
                            'gold': float(wager.get('gold', 0)),
                            'ioratio': float(wager.get('ioratio', 0)),
                            'status': wager.get('status', ''),
                            'team_name': wager.get('team_name', ''),
                        }
                        bets.append(bet)
                        total_gold += bet['gold']
                
                return {
                    'success': True,
                    'bets': bets,
                    'total_bet':  total_gold,
                    'count': len(bets)
                }
            except: 
                return {'success': False, 'bets': [], 'error': '解析失败'}
                
        except Exception as e: 
            return {'success': False, 'error': str(e), 'bets': []}
    
    def test_connection(self):
        """测试API连接"""
        try: 
            params = {'ver': datetime.now().strftime('%Y-%m-%d-mtfix_133')}
            data = {
                'p': 'get_game_list',
                'uid':  self.uid,
                'showtype': 'live',
                'rtype': 'rb',
                'gtype': 'FT',
                'ltype': 3,
                'langx': self.langx,
                'ts': int(time.time() * 1000)
            }
            
            response = self.session.post(
                self.base_url, 
                params=params, 
                data=data, 
                timeout=10,
                verify=False
            )
            
            return {
                'status_code': response.status_code,
                'response_length': len(response.text),
                'has_error': 'error' in response.text. lower() or 'table id error' in response.text.lower(),
                'has_game_data': '<game' in response.text.lower() or 'gid' in response.text.lower(),
                'raw_preview': response.text[: 300]
            }
        except Exception as e:
            return {'error': str(e)}


class BettingBot:
    """投注机器人核心类 - API版本"""
    
    def __init__(self):
        self.driver = None
        self.is_running = False
        self. is_logged_in = False
        self. wait = None
        self.auto_bet_enabled = False
        self.bet_amount = 2
        self.bet_history = []
        self.current_matches = []
        self.odds_threshold = 1.80
        
        # API实例
        self.api = BettingAPI()
    
    def setup_driver(self, headless=False):
        """初始化浏览器"""
        options = webdriver.ChromeOptions()
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option('useAutomationExtension', False)
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--ignore-certificate-errors")  # 忽略证书错误
        options.add_argument("--ignore-ssl-errors")  # 忽略SSL错误
        options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
        
        # 启用性能日志
        options.set_capability('goog:loggingPrefs', {'performance': 'ALL', 'browser': 'ALL'})

        if headless:
            options.add_argument("--headless=new")

        self.driver = webdriver. Chrome(options=options)
        self.wait = WebDriverWait(self. driver, 60)

        self.driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
            'source': '''
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                window.chrome = {runtime: {}};
            '''
        })
    
    def handle_password_popup(self, log_callback):
        """处理弹窗"""
        log_callback("检测并处理弹窗...")
        for attempt in range(10):
            try:
                result = self.driver.execute_script("""
                    var elements = document.querySelectorAll('div, button, span');
                    for (var elem of elements) {
                        if (elem.innerText.trim() === '否' && elem.offsetWidth > 0) {
                            elem.click();
                            return {success: true};
                        }
                    }
                    return {success: false};
                """)
                if result.get('success'):
                    log_callback(f"  ✓ 关闭弹窗成功")
                    time.sleep(1)
                else:
                    break
            except: 
                pass
            time.sleep(1)
        return True
    
    def extract_uid_from_page(self, log_callback):
        """从页面提取UID - 多种方法"""
        uid_found = None
        
        # === 方法1: 从JavaScript全局变量提取 ===
        log_callback("  方法1: 从JS变量提取...")
        try:
            uid_from_js = self.driver.execute_script("""
                var possibleNames = ['uid', 'member_id', 'user_id', 'userid', 
                                    'memberId', 'memberCode', 'member_code', 'UID'];
                
                for (var name of possibleNames) {
                    if (typeof window[name] !== 'undefined' && window[name]) {
                        return String(window[name]);
                    }
                }
                
                if (typeof window.user !== 'undefined' && window.user) {
                    if (window.user.uid) return String(window.user.uid);
                    if (window.user.id) return String(window.user. id);
                }
                
                if (typeof window.config !== 'undefined' && window. config) {
                    if (window.config.uid) return String(window.config.uid);
                }
                
                return null;
            """)
            
            if uid_from_js:
                uid_found = str(uid_from_js)
                log_callback(f"    ✓ 找到uid: {uid_found}")
                return uid_found
            else:
                log_callback(f"    未找到")
        except Exception as e:
            log_callback(f"    失败: {e}")
        
        # === 方法2: 从localStorage提取 ===
        log_callback("  方法2: 从localStorage提取...")
        try:
            uid_from_storage = self.driver.execute_script("""
                var localKeys = ['uid', 'member_id', 'user_id', 'userId', 'memberId'];
                for (var key of localKeys) {
                    var val = localStorage.getItem(key);
                    if (val) return String(val);
                }
                return null;
            """)
            
            if uid_from_storage:
                uid_found = str(uid_from_storage)
                log_callback(f"    ✓ 找到uid: {uid_found}")
                return uid_found
            else:
                log_callback(f"    未找到")
        except Exception as e:
            log_callback(f"    失败: {e}")
        
        # === 方法3: 从页面HTML提取 ===
        log_callback("  方法3: 从HTML提取...")
        try:
            page_source = self.driver.page_source
            
            patterns = [
                r'uid["\']?\s*[: =]\s*["\']? (\d+)',
                r'member_id["\']?\s*[:=]\s*["\']?(\d+)',
                r'&uid=(\d+)',
                r'"uid"\s*:\s*"? (\d+)"? ',
            ]
            
            for pattern in patterns:
                match = re.search(pattern, page_source, re.IGNORECASE)
                if match:
                    uid_found = match.group(1)
                    log_callback(f"    ✓ 找到uid: {uid_found}")
                    return uid_found
            
            log_callback(f"    未找到")
        except Exception as e:
            log_callback(f"    失败: {e}")
        
        # === 方法4: 从URL提取 ===
        log_callback("  方法4: 从URL提取...")
        try:
            current_url = self.driver.current_url
            url_match = re.search(r'[? &]uid=(\d+)', current_url)
            if url_match:
                uid_found = url_match.group(1)
                log_callback(f"    ✓ 找到uid: {uid_found}")
                return uid_found
            else:
                log_callback(f"    未找到")
        except Exception as e:
            log_callback(f"    失败: {e}")
        
        # === 方法5: 从网络请求日志提取 ===
        log_callback("  方法5: 从网络请求提取...")
        try:
            logs = self.driver.get_log('performance')
            for log_entry in logs[-100:]: 
                message = json.loads(log_entry['message'])
                if 'message' in message: 
                    msg = message['message']
                    if msg.get('method') == 'Network.requestWillBeSent':
                        request = msg. get('params', {}).get('request', {})
                        post_data = request.get('postData', '')
                        if 'uid=' in post_data:
                            uid_match = re.search(r'uid=(\d+)', post_data)
                            if uid_match:
                                uid_found = uid_match.group(1)
                                log_callback(f"    ✓ 找到uid: {uid_found}")
                                return uid_found
            log_callback(f"    未找到")
        except Exception as e:
            log_callback(f"    失败: {e}")
        
        return uid_found
    
    def login(self, username, password, log_callback, manual_uid=None):
        """登录并获取cookies给API使用"""
        try:
            log_callback("正在访问登录页面...")
            self.driver.get(URL)
            time.sleep(8)

            # 输入用户名
            log_callback("输入用户名...")
            self.driver.execute_script(f"""
                var inputs = document.querySelectorAll('input');
                for(var i=0; i<inputs.length; i++){{
                    if(inputs[i].type === 'text' && inputs[i].offsetWidth > 0){{
                        inputs[i].value = '{username}';
                        inputs[i].dispatchEvent(new Event('input', {{bubbles: true}}));
                        break;
                    }}
                }}
            """)
            log_callback(f"✓ 已输入用户名: {username}")

            # 输入密码
            self.driver.execute_script(f"""
                var inputs = document. querySelectorAll('input[type="password"]');
                for(var i=0; i<inputs. length; i++){{
                    if(inputs[i].offsetWidth > 0){{
                        inputs[i].value = '{password}';
                        inputs[i].dispatchEvent(new Event('input', {{bubbles: true}}));
                        break;
                    }}
                }}
            """)
            log_callback("✓ 已输入密码")

            time.sleep(1)

            # 点击登录按钮
            log_callback("点击登录按钮...")
            self.driver.execute_script("""
                var btn = document.getElementById('btn_login');
                if(btn) { btn.click(); return; }
                var elements = document.querySelectorAll('button, div, span');
                for(var i=0; i<elements.length; i++){
                    var text = elements[i].innerText. trim();
                    if((text === '登录' || text === '登入') && elements[i].offsetWidth > 0){
                        elements[i].click();
                        return;
                    }
                }
            """)
            log_callback("✓ 已点击登录按钮")

            log_callback("\n等待登录响应...")
            time.sleep(10)

            self.handle_password_popup(log_callback)
            time.sleep(3)

            # === 提取cookies ===
            log_callback("\n提取cookies...")
            cookies = self.driver.get_cookies()
            cookies_dict = {c['name']: c['value'] for c in cookies}
            
            log_callback(f"  获取到 {len(cookies_dict)} 个cookies")
            
            # === 提取UID ===
            log_callback("\n尝试提取UID...")
            
            if manual_uid and manual_uid.strip():
                uid = manual_uid.strip()
                log_callback(f"✓ 使用手动输入的UID: {uid}")
            else:
                uid = self. extract_uid_from_page(log_callback)
            
            if uid:
                cookies_dict['uid'] = uid
                log_callback(f"\n✓ UID已获取: {uid}")
            else:
                log_callback(f"\n⚠ 未能自动提取UID，请手动输入")
            
            # 保存cookies
            with open(COOKIES_FILE, "wb") as f:
                pickle.dump(cookies, f)
            
            # 设置给API
            self.api.set_cookies(cookies_dict)
            if uid:
                self.api.set_uid(uid)
            
            log_callback(f"\n✓ Cookies已设置给API")
            log_callback(f"  API UID: {self.api.uid or '❌ 未设置'}")

            # 进入滚球页面
            log_callback("\n进入滚球页面...")
            time.sleep(2)
            self.driver.execute_script("""
                var elements = document.querySelectorAll('*');
                for (var elem of elements) {
                    if (elem.textContent.trim() === '滚球' && elem.offsetWidth > 0) {
                        elem.click();
                        break;
                    }
                }
            """)

            time.sleep(5)

            # 再次尝试提取UID
            if not self.api.uid:
                log_callback("\n再次尝试提取UID...")
                uid = self.extract_uid_from_page(log_callback)
                if uid:
                    self.api.set_uid(uid)
                    log_callback(f"✓ UID已更新:  {uid}")

            # 测试API
            log_callback("\n测试API连接...")
            test_result = self.api.test_connection()
            
            if test_result. get('error'):
                log_callback(f"✗ API测试失败: {test_result['error']}")
            else:
                log_callback(f"  状态码: {test_result['status_code']}")
                log_callback(f"  响应长度: {test_result['response_length']}")
                log_callback(f"  有比赛数据: {'是' if test_result['has_game_data'] else '否'}")
                log_callback(f"  有错误: {'是' if test_result['has_error'] else '否'}")
                
                if test_result['has_game_data'] and not test_result['has_error']: 
                    log_callback(f"\n✓ API工作正常!")
                elif test_result['has_error']: 
                    log_callback(f"\n⚠ API返回错误，请检查UID")

            self.is_logged_in = True
            log_callback("\n✓ 登录流程完成！")
            return True

        except Exception as e:
            log_callback(f"\n✗ 登录失败: {str(e)}")
            import traceback
            log_callback(traceback.format_exc())
            return False
    
    def get_all_odds_data(self):
        """使用API获取所有比赛数据"""
        result = self.api.get_rolling_matches()
        
        if result['success']:
            self.current_matches = result['matches']
        
        return result
    
    def auto_bet_check(self, log_callback):
        """检查并自动下注"""
        if not self. auto_bet_enabled:
            return False
        
        threshold = self.odds_threshold
        
        for match in self.current_matches:
            team1 = match. get('team1', '')
            team2 = match.get('team2', '')
            gid = match.get('gid', '')
            league = match.get('league', '')
            
            for bet_type, type_odds in match.get('odds', {}).items():
                for team_type in ['home', 'away', 'draw']:
                    for odds in type_odds. get(team_type, []):
                        if odds['value'] >= threshold and odds['value'] < 50:
                            bet_key = f"{gid}_{bet_type}_{team_type}_{odds['text']}_{datetime.now().strftime('%Y%m%d%H')}"
                            
                            if bet_key in self.bet_history:
                                continue
                            
                            team_name = team1 if team_type == 'home' else (team2 if team_type == 'away' else '和局')
                            
                            log_callback(f"\n{'='*50}")
                            log_callback(f"🎯 触发自动下注!")
                            log_callback(f"   联赛: {league}")
                            log_callback(f"   比赛: {team1} vs {team2}")
                            log_callback(f"   盘口: {bet_type} ({team_name})")
                            log_callback(f"   水位: {odds['text']} >= {threshold}")
                            
                            bet_result = self.api.place_bet(
                                gid=gid,
                                wtype=odds. get('wtype', 'RE'),
                                rtype=odds.get('rtype', 'REH'),
                                chose_team=odds.get('chose_team', 'H'),
                                ioratio=odds['value'],
                                gold=self.bet_amount
                            )
                            
                            if bet_result['success']: 
                                self.bet_history. append(bet_key)
                                log_callback(f"  ✓✓ 下注成功!")
                                log_callback(f"  注单号: {bet_result. get('ticket_id', 'N/A')}")
                            else:
                                log_callback(f"  ✗ 下注失败: {bet_result.get('error', '未知错误')}")
                            
                            log_callback(f"{'='*50}\n")
                            return bet_result['success']
        
        return False
    
    def monitor_realtime(self, interval, log_callback, update_callback):
        """实时监控"""
        log_callback(f"\n{'='*50}")
        log_callback(f"🚀 开始实时监控 (API模式)")
        log_callback(f"   刷新间隔: {interval}秒")
        log_callback(f"   水位阈值: {self.odds_threshold}")
        log_callback(f"   自动下注: {'启用' if self.auto_bet_enabled else '禁用'}")
        log_callback(f"   API UID: {self.api. uid or '未设置'}")
        log_callback(f"{'='*50}\n")
        
        while self.is_running:
            try:
                data = self.get_all_odds_data()
                
                if data['success']:
                    update_callback(data)
                    
                    matches = data. get('matches', [])
                    total_odds = data.get('totalOdds', 0)
                    
                    home_count = sum(len(od. get('home', [])) for m in matches for od in m.get('odds', {}).values())
                    away_count = sum(len(od. get('away', [])) for m in matches for od in m.get('odds', {}).values())
                    draw_count = sum(len(od.get('draw', [])) for m in matches for od in m.get('odds', {}).values())
                    
                    log_callback(f"[{datetime.now().strftime('%H:%M:%S')}] {len(matches)}场, {total_odds}水位 (主:{home_count} 客:{away_count} 和:{draw_count})")
                    
                    if self.auto_bet_enabled:
                        self.auto_bet_check(log_callback)
                else:
                    error_msg = data.get('error', '未知错误')
                    log_callback(f"[{datetime.now().strftime('%H:%M:%S')}] ✗ {error_msg[: 50]}")
                
                time.sleep(interval)
                
            except Exception as e: 
                log_callback(f"✗ 监控错误: {e}")
                time.sleep(interval)
        
        log_callback("\n监控已停止")
    
    def stop(self):
        """停止"""
        self.is_running = False
        if self.driver:
            try:
                self.driver.quit()
            except:
                pass

# ================== GUI类 ==================
class BettingBotGUI:
    """GUI界面"""
    
    def __init__(self, root):
        self.root = root
        self.root.title("滚球水位实时监控系统 v6.2 (API模式)")
        self.root.geometry("1850x950")
        self.root.configure(bg='#1a1a2e')
        
        self.bot = BettingBot()
        self.monitor_thread = None
        
        self.create_widgets()
        self.load_config()
    
    def load_config(self):
        """加载配置"""
        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    config = json. load(f)
                    self.bot.odds_threshold = config.get('threshold', 1.80)
                    self.bot. bet_amount = config.get('bet_amount', 2)
                    self.threshold_entry.delete(0, tk.END)
                    self.threshold_entry.insert(0, str(self.bot.odds_threshold))
                    self.amount_entry.delete(0, tk.END)
                    self. amount_entry.insert(0, str(self.bot.bet_amount))
                    saved_uid = config.get('uid', '')
                    if saved_uid:
                        self.uid_entry.delete(0, tk.END)
                        self. uid_entry.insert(0, saved_uid)
        except:
            pass
    
    def save_config(self):
        """保存配置"""
        try:
            config = {
                'threshold': self.bot.odds_threshold,
                'bet_amount': self. bot.bet_amount,
                'uid': self.uid_entry.get().strip()
            }
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
        except:
            pass
    
    def create_widgets(self):
        """创建界面组件"""
        # ========== 标题区域 ==========
        title_frame = tk.Frame(self.root, bg='#1a1a2e')
        title_frame.pack(fill='x', padx=20, pady=10)
        
        tk.Label(title_frame, text="🎯 滚球水位实时监控系统 v6.2", bg='#1a1a2e', fg='#00ff88',
                font=('Microsoft YaHei UI', 22, 'bold')).pack()
        tk.Label(title_frame, text="API模式 | SSL已修复 | 支持手动输入UID | 自动下注",
                bg='#1a1a2e', fg='#888', font=('Microsoft YaHei UI', 10)).pack()
        
        # ========== 主容器 ==========
        main_frame = tk.Frame(self. root, bg='#1a1a2e')
        main_frame.pack(fill='both', expand=True, padx=20, pady=10)
        
        # ========== 左侧面板 ==========
        left_frame = tk.Frame(main_frame, bg='#16213e', width=340)
        left_frame.pack(side='left', fill='y', padx=(0, 10))
        left_frame.pack_propagate(False)
        
        # ----- 登录区域 -----
        login_frame = tk.LabelFrame(left_frame, text="🔐 登录", bg='#16213e',
                                   fg='#00ff88', font=('Microsoft YaHei UI', 11, 'bold'), padx=10, pady=10)
        login_frame.pack(fill='x', padx=10, pady=(10, 5))
        
        tk.Label(login_frame, text="用户名:", bg='#16213e', fg='#fff',
                font=('Microsoft YaHei UI', 10)).grid(row=0, column=0, sticky='w', pady=3)
        self.username_entry = tk.Entry(login_frame, bg='#0f3460', fg='#fff',
                                      font=('Consolas', 10), insertbackground='#fff', relief='flat', width=22)
        self.username_entry.grid(row=0, column=1, pady=3, padx=(5, 0))
        self.username_entry.insert(0, USERNAME)
        
        tk.Label(login_frame, text="密码:", bg='#16213e', fg='#fff',
                font=('Microsoft YaHei UI', 10)).grid(row=1, column=0, sticky='w', pady=3)
        self.password_entry = tk.Entry(login_frame, show="*", bg='#0f3460', fg='#fff',
                                      font=('Consolas', 10), insertbackground='#fff', relief='flat', width=22)
        self.password_entry.grid(row=1, column=1, pady=3, padx=(5, 0))
        self.password_entry.insert(0, PASSWORD)
        
        tk.Label(login_frame, text="UID(可选):", bg='#16213e', fg='#ffaa00',
                font=('Microsoft YaHei UI', 10)).grid(row=2, column=0, sticky='w', pady=3)
        self.uid_entry = tk.Entry(login_frame, bg='#0f3460', fg='#ffaa00',
                                 font=('Consolas', 10, 'bold'), insertbackground='#fff', relief='flat', width=22)
        self.uid_entry.grid(row=2, column=1, pady=3, padx=(5, 0))
        
        tk.Label(login_frame, text="(登录后自动获取，或手动输入)", bg='#16213e', fg='#666',
                font=('Microsoft YaHei UI', 8)).grid(row=3, column=0, columnspan=2, sticky='w')
        
        self.login_btn = tk.Button(login_frame, text="登录", bg='#00ff88', fg='#000',
                                  font=('Microsoft YaHei UI', 10, 'bold'), relief='flat',
                                  command=self.login, cursor='hand2', padx=20, pady=3)
        self.login_btn.grid(row=4, column=0, columnspan=2, pady=(10, 0))
        
        # ----- 日志区域 -----
        log_frame = tk.LabelFrame(left_frame, text="📋 日志", bg='#16213e',
                                 fg='#888', font=('Microsoft YaHei UI', 10, 'bold'), padx=5, pady=5)
        log_frame.pack(fill='both', expand=True, padx=10, pady=10)
        
        self.log_text = scrolledtext.ScrolledText(log_frame, bg='#0f3460', fg='#00ff88',
                                                 font=('Consolas', 9), relief='flat', height=12, wrap='word')
        self.log_text.pack(fill='both', expand=True)
        
        # ----- 下注设置区域 -----
        self.bet_frame = tk.LabelFrame(left_frame, text="💰 下注设置", bg='#16213e',
                                      fg='#ff9900', font=('Microsoft YaHei UI', 11, 'bold'), padx=10, pady=10)
        
        tk.Label(self.bet_frame, text="下注金额:", bg='#16213e', fg='#fff',
                font=('Microsoft YaHei UI', 10)).grid(row=0, column=0, sticky='w', pady=3)
        self.amount_entry = tk.Entry(self.bet_frame, bg='#0f3460', fg='#00ff88',
                                    font=('Consolas', 12, 'bold'), insertbackground='#fff', relief='flat', width=8)
        self.amount_entry.grid(row=0, column=1, pady=3, padx=(5, 0))
        self.amount_entry.insert(0, "2")
        tk.Label(self.bet_frame, text="RMB", bg='#16213e', fg='#888',
                font=('Microsoft YaHei UI', 9)).grid(row=0, column=2, padx=3)
        
        tk.Label(self.bet_frame, text="刷新间隔:", bg='#16213e', fg='#fff',
                font=('Microsoft YaHei UI', 10)).grid(row=1, column=0, sticky='w', pady=3)
        self.interval_entry = tk.Entry(self.bet_frame, bg='#0f3460', fg='#fff',
                                      font=('Consolas', 12), insertbackground='#fff', relief='flat', width=8)
        self.interval_entry.grid(row=1, column=1, pady=3, padx=(5, 0))
        self.interval_entry.insert(0, "3")
        tk.Label(self.bet_frame, text="秒", bg='#16213e', fg='#888',
                font=('Microsoft YaHei UI', 9)).grid(row=1, column=2, padx=3)
        
        tk.Label(self.bet_frame, text="水位阈值:", bg='#16213e', fg='#fff',
                font=('Microsoft YaHei UI', 10)).grid(row=2, column=0, sticky='w', pady=3)
        self.threshold_entry = tk. Entry(self.bet_frame, bg='#0f3460', fg='#ffaa00',
                                       font=('Consolas', 12, 'bold'), insertbackground='#fff', relief='flat', width=8)
        self.threshold_entry.grid(row=2, column=1, pady=3, padx=(5, 0))
        self.threshold_entry.insert(0, "1.80")
        tk.Label(self.bet_frame, text="≥触发", bg='#16213e', fg='#888',
                font=('Microsoft YaHei UI', 9)).grid(row=2, column=2, padx=3)
        
        self.auto_bet_var = tk.BooleanVar(value=False)
        self.auto_bet_check = tk.Checkbutton(self.bet_frame, text="⚡ 启用自动下注",
                                            variable=self.auto_bet_var, bg='#16213e', fg='#ff4444',
                                            selectcolor='#0f3460', activebackground='#16213e',
                                            font=('Microsoft YaHei UI', 11, 'bold'), command=self.toggle_auto_bet)
        self.auto_bet_check.grid(row=3, column=0, columnspan=3, pady=(10, 0), sticky='w')
        
        # ----- 控制按钮区域 -----
        self.control_frame = tk.Frame(left_frame, bg='#16213e')
        
        self.start_btn = tk.Button(self.control_frame, text="🚀 开始监控", bg='#0088ff',
                                  fg='#fff', font=('Microsoft YaHei UI', 12, 'bold'), relief='flat',
                                  command=self.start_monitoring, cursor='hand2', pady=10)
        self.start_btn.pack(fill='x', pady=(0, 5))
        
        self.stop_btn = tk.Button(self.control_frame, text="⏹ 停止监控", bg='#ff4444',
                                 fg='#fff', font=('Microsoft YaHei UI', 12, 'bold'), relief='flat',
                                 command=self.stop_monitoring, cursor='hand2', pady=10, state='disabled')
        self.stop_btn.pack(fill='x', pady=(0, 5))
        
        self.refresh_btn = tk.Button(self.control_frame, text="🔄 刷新数据", bg='#666',
                                    fg='#fff', font=('Microsoft YaHei UI', 10), relief='flat',
                                    command=self.refresh_data, cursor='hand2', pady=6)
        self.refresh_btn.pack(fill='x', pady=(0, 5))
        
        self.diagnose_btn = tk.Button(self.control_frame, text="🔬 API诊断", bg='#9933ff',
                                     fg='#fff', font=('Microsoft YaHei UI', 10, 'bold'), relief='flat',
                                     command=self. diagnose_api, cursor='hand2', pady=6)
        self.diagnose_btn.pack(fill='x', pady=(0, 5))
        
        self.bets_btn = tk.Button(self.control_frame, text="📋 查看今日注单", bg='#336666',
                                 fg='#fff', font=('Microsoft YaHei UI', 10), relief='flat',
                                 command=self.show_today_bets, cursor='hand2', pady=6)
        self.bets_btn.pack(fill='x')
        
        # ========== 右侧数据区域 ==========
        self.right_frame = tk.Frame(main_frame, bg='#16213e')
        self.right_frame. pack(side='right', fill='both', expand=True)
        
        # ----- 标题栏 -----
        header_frame = tk.Frame(self.right_frame, bg='#16213e')
        header_frame.pack(fill='x', pady=(0, 5))
        
        tk.Label(header_frame, text="📊 实时水位数据 (API)", bg='#16213e',
                font=('Microsoft YaHei UI', 14, 'bold'), fg='#00ff88').pack(side='left')
        
        self.uid_label = tk.Label(header_frame, text="UID:  未设置", bg='#16213e',
                                 font=('Microsoft YaHei UI', 10), fg='#ff4444')
        self.uid_label.pack(side='left', padx=20)
        
        self.update_label = tk.Label(header_frame, text="", bg='#16213e',
                                    font=('Microsoft YaHei UI', 10), fg='#ffaa00')
        self.update_label.pack(side='right', padx=10)
        
        # ----- 提示标签 -----
        self. hint_label = tk.Label(self.right_frame,
                                  text="请先登录\n\n登录后将通过API获取所有滚球比赛数据\n\nv6.2 已修复SSL证书验证问题",
                                  bg='#16213e', fg='#888', font=('Microsoft YaHei UI', 11), justify='center')
        self.hint_label.pack(pady=100)
        
        self.odds_canvas = None
        self.odds_inner_frame = None
        
        # ========== 状态栏 ==========
        status_frame = tk.Frame(self.root, bg='#0f3460', height=30)
        status_frame.pack(side='bottom', fill='x')
        
        self.status_label = tk.Label(status_frame, text="状态: 未登录", bg='#0f3460',
                                    fg='#888', font=('Microsoft YaHei UI', 10), anchor='w', padx=20)
        self.status_label.pack(side='left', fill='y')
        
        self.time_label = tk.Label(status_frame, text="", bg='#0f3460',
                                  fg='#00ff88', font=('Microsoft YaHei UI', 10), anchor='e', padx=20)
        self.time_label.pack(side='right', fill='y')
    
    def create_odds_display_area(self, parent):
        """创建水位显示区域"""
        if self.hint_label: 
            self.hint_label. pack_forget()
        
        if self.odds_canvas:
            self.odds_canvas. master.destroy()
        
        canvas_frame = tk.Frame(parent, bg='#16213e')
        canvas_frame.pack(fill='both', expand=True)
        
        self.odds_canvas = tk.Canvas(canvas_frame, bg='#0f3460', highlightthickness=0)
        scrollbar_y = tk.Scrollbar(canvas_frame, orient='vertical', command=self.odds_canvas.yview)
        scrollbar_x = tk.Scrollbar(canvas_frame, orient='horizontal', command=self.odds_canvas.xview)
        
        self. odds_inner_frame = tk.Frame(self.odds_canvas, bg='#0f3460')
        
        self.odds_canvas.configure(yscrollcommand=scrollbar_y.set, xscrollcommand=scrollbar_x.set)
        
        scrollbar_y.pack(side='right', fill='y')
        scrollbar_x.pack(side='bottom', fill='x')
        self.odds_canvas.pack(side='left', fill='both', expand=True)
        
        self.canvas_window = self.odds_canvas.create_window((0, 0), window=self.odds_inner_frame, anchor='nw')
        
        self.odds_inner_frame.bind('<Configure>', lambda e: self.odds_canvas. configure(scrollregion=self. odds_canvas.bbox('all')))
        self.odds_canvas.bind('<Configure>', lambda e: self.odds_canvas.itemconfig(self.canvas_window, width=e.width))
        self.odds_canvas.bind_all('<MouseWheel>', lambda e: self.odds_canvas.yview_scroll(int(-1*(e.delta/120)), 'units'))
    
    def update_odds_display(self, data):
        """更新水位显示"""
        def update():
            try:
                if not self.odds_inner_frame:
                    self.create_odds_display_area(self.right_frame)
                
                matches = data.get('matches', [])
                total_odds = data.get('totalOdds', 0)
                timestamp = datetime.now().strftime('%H:%M:%S')
                
                self.time_label.config(text=f"最后更新: {timestamp}")
                self.update_label.config(text=f"🔄 {timestamp}", fg='#00ff88')
                
                uid = self.bot.api.uid
                if uid:
                    self.uid_label.config(text=f"UID: {uid}", fg='#00ff88')
                else: 
                    self.uid_label. config(text="UID: 未设置", fg='#ff4444')
                
                for widget in self.odds_inner_frame.winfo_children():
                    widget.destroy()
                
                if not matches:
                    error_msg = data.get('error', '')
                    if error_msg: 
                        tk.Label(self.odds_inner_frame, text=f"❌ {error_msg[: 80]}",
                                bg='#0f3460', fg='#ff4444', font=('Microsoft YaHei UI', 11)).pack(pady=10)
                    else:
                        tk.Label(self.odds_inner_frame, text="暂无比赛数据",
                                bg='#0f3460', fg='#888', font=('Microsoft YaHei UI', 11)).pack(pady=20)
                    return
                
                home_total = sum(len(od. get('home', [])) for m in matches for od in m.get('odds', {}).values())
                away_total = sum(len(od.get('away', [])) for m in matches for od in m.get('odds', {}).values())
                draw_total = sum(len(od.get('draw', [])) for m in matches for od in m. get('odds', {}).values())
                
                tk.Label(self.odds_inner_frame,
                        text=f"共 {len(matches)} 场比赛，{total_odds} 个水位 (主:{home_total} 客:{away_total} 和:{draw_total}) | 阈值: {self.bot.odds_threshold}",
                        bg='#0f3460', fg='#00ff88', font=('Microsoft YaHei UI', 11, 'bold')).pack(anchor='w', padx=10, pady=5)
                
                current_league = ''
                threshold = self.bot.odds_threshold
                display_bet_types = BET_TYPES_ORDER[: 8]
                
                for match in matches:
                    league = match.get('league', '未知联赛')
                    team1 = match.get('team1', '主队')
                    team2 = match.get('team2', '客队')
                    score1 = match.get('score1', '0')
                    score2 = match.get('score2', '0')
                    match_time = match.get('time', '')
                    gid = match.get('gid', '')
                    odds = match.get('odds', {})
                    
                    if league and league != current_league:
                        league_frame = tk.Frame(self.odds_inner_frame, bg='#2d2d44')
                        league_frame.pack(fill='x', pady=(15, 5), padx=5)
                        tk.Label(league_frame, text=f"🏆 {league}", bg='#2d2d44', fg='#ffaa00',
                                font=('Microsoft YaHei UI', 12, 'bold'), pady=5).pack(anchor='w', padx=10)
                        current_league = league
                    
                    match_frame = tk.Frame(self.odds_inner_frame, bg='#1e1e32', bd=1, relief='solid')
                    match_frame. pack(fill='x', padx=5, pady=3)
                    
                    info_frame = tk.Frame(match_frame, bg='#1e1e32')
                    info_frame.pack(fill='x', pady=(5, 2), padx=5)
                    
                    tk.Label(info_frame, text=f"⏱ {match_time} [ID:{gid}]", bg='#1e1e32', fg='#888',
                            font=('Microsoft YaHei UI', 8), width=24, anchor='w').pack(side='left')
                    
                    for bt in display_bet_types: 
                        handicap = odds.get(bt, {}).get('handicap', '')
                        header_text = f"{bt}\n{handicap}" if handicap else bt
                        tk.Label(info_frame, text=header_text, bg='#1e1e32', fg='#aaa',
                                font=('Microsoft YaHei UI', 8), width=10, anchor='center').pack(side='left', padx=1)
                    
                    team1_frame = tk.Frame(match_frame, bg='#1e1e32')
                    team1_frame.pack(fill='x', pady=2, padx=5)
                    
                    score_color = '#ff4444' if score1 and score1. isdigit() and int(score1) > 0 else '#fff'
                    tk.Label(team1_frame, text=score1 or '0', bg='#1e1e32', fg=score_color,
                            font=('Microsoft YaHei UI', 11, 'bold'), width=3).pack(side='left')
                    
                    team1_display = team1[: 18] + '. .' if len(team1) > 20 else team1
                    tk.Label(team1_frame, text=team1_display, bg='#1e1e32', fg='#fff',
                            font=('Microsoft YaHei UI', 9), width=20, anchor='w').pack(side='left')
                    
                    for bt in display_bet_types: 
                        cell_frame = tk.Frame(team1_frame, bg='#1e1e32', width=80)
                        cell_frame. pack(side='left', padx=1)
                        cell_frame.pack_propagate(False)
                        
                        type_odds = odds.get(bt, {})
                        home_odds = type_odds.get('home', [])
                        
                        cell_inner = tk.Frame(cell_frame, bg='#1e1e32')
                        cell_inner.pack(expand=True)
                        
                        if home_odds:
                            val = home_odds[0]['value']
                            text = home_odds[0]['text']
                            color = '#ff4444' if val >= threshold else '#00ff88'
                            tk. Label(cell_inner, text=text, bg='#1e1e32', fg=color,
                                    font=('Consolas', 10, 'bold')).pack()
                        else:
                            tk.Label(cell_inner, text="-", bg='#1e1e32', fg='#444',
                                    font=('Consolas', 10)).pack()
                    
                    has_draw = any(odds.get(bt, {}).get('draw', []) for bt in ['独赢', '独赢上半场'])
                    if has_draw:
                        draw_frame = tk.Frame(match_frame, bg='#1e1e32')
                        draw_frame.pack(fill='x', pady=1, padx=5)
                        
                        tk.Label(draw_frame, text="", bg='#1e1e32', width=3).pack(side='left')
                        tk.Label(draw_frame, text="和局", bg='#1e1e32', fg='#aaa',
                                font=('Microsoft YaHei UI', 9), width=20, anchor='w').pack(side='left')
                        
                        for bt in display_bet_types:
                            cell_frame = tk.Frame(draw_frame, bg='#1e1e32', width=80)
                            cell_frame.pack(side='left', padx=1)
                            cell_frame.pack_propagate(False)
                            
                            type_odds = odds.get(bt, {})
                            draw_odds = type_odds.get('draw', [])
                            
                            cell_inner = tk.Frame(cell_frame, bg='#1e1e32')
                            cell_inner.pack(expand=True)
                            
                            if draw_odds: 
                                val = draw_odds[0]['value']
                                text = draw_odds[0]['text']
                                color = '#ff4444' if val >= threshold else '#00ccff'
                                tk.Label(cell_inner, text=text, bg='#1e1e32', fg=color,
                                        font=('Consolas', 10, 'bold')).pack()
                            else: 
                                tk.Label(cell_inner, text="", bg='#1e1e32',
                                        font=('Consolas', 10)).pack()
                    
                    team2_frame = tk.Frame(match_frame, bg='#1e1e32')
                    team2_frame.pack(fill='x', pady=(0, 5), padx=5)
                    
                    score_color = '#ff4444' if score2 and score2.isdigit() and int(score2) > 0 else '#fff'
                    tk.Label(team2_frame, text=score2 or '0', bg='#1e1e32', fg=score_color,
                            font=('Microsoft YaHei UI', 11, 'bold'), width=3).pack(side='left')
                    
                    team2_display = team2[:18] + '..' if len(team2) > 20 else team2
                    tk.Label(team2_frame, text=team2_display, bg='#1e1e32', fg='#fff',
                            font=('Microsoft YaHei UI', 9), width=20, anchor='w').pack(side='left')
                    
                    for bt in display_bet_types:
                        cell_frame = tk.Frame(team2_frame, bg='#1e1e32', width=80)
                        cell_frame.pack(side='left', padx=1)
                        cell_frame.pack_propagate(False)
                        
                        type_odds = odds.get(bt, {})
                        away_odds = type_odds.get('away', [])
                        
                        cell_inner = tk.Frame(cell_frame, bg='#1e1e32')
                        cell_inner.pack(expand=True)
                        
                        if away_odds: 
                            val = away_odds[0]['value']
                            text = away_odds[0]['text']
                            color = '#ff4444' if val >= threshold else '#ffaa00'
                            tk. Label(cell_inner, text=text, bg='#1e1e32', fg=color,
                                    font=('Consolas', 10, 'bold')).pack()
                        else:
                            tk.Label(cell_inner, text="-", bg='#1e1e32', fg='#444',
                                    font=('Consolas', 10)).pack()
                
                self.odds_inner_frame.update_idletasks()
                self. odds_canvas.configure(scrollregion=self.odds_canvas.bbox('all'))
                
            except Exception as e:
                print(f"更新显示出错: {e}")
                import traceback
                traceback.print_exc()
        
        self.root.after(0, update)
    
    def log(self, message):
        """写日志"""
        def update_log():
            timestamp = datetime.now().strftime('%H:%M:%S')
            self.log_text.insert('end', f"[{timestamp}] {message}\n")
            self.log_text.see('end')
            lines = int(self.log_text.index('end-1c').split('.')[0])
            if lines > 500:
                self.log_text.delete('1.0', '200.0')
        self.root.after(0, update_log)
    
    def toggle_auto_bet(self):
        """切换自动下注"""
        if self.auto_bet_var.get():
            result = messagebox.askyesno("确认启用自动下注",
                f"确定启用自动下注吗？\n\n"
                f"水位 ≥ {self.threshold_entry.get()} 时将自动下注\n"
                f"下注金额:  {self.amount_entry.get()} RMB\n\n"
                f"请确保账户余额充足！")
            if result:
                self.bot.auto_bet_enabled = True
                self.bot.odds_threshold = float(self.threshold_entry.get())
                self.bot.bet_amount = float(self.amount_entry.get())
                self.save_config()
                self.log("⚡ 自动下注已启用!")
            else:
                self.auto_bet_var.set(False)
        else:
            self.bot.auto_bet_enabled = False
            self.log("自动下注已关闭")
    
    def login(self):
        """登录"""
        username = self.username_entry.get()
        password = self.password_entry.get()
        manual_uid = self.uid_entry.get().strip()
        
        if not username or not password:
            messagebox.showerror("错误", "请输入用户名和密码")
            return
        
        self.login_btn.config(state='disabled', text="登录中...")
        self.status_label.config(text="状态: 登录中.. .", fg='#ffaa00')
        
        def login_thread():
            try:
                self.bot.setup_driver(headless=False)
                success = self.bot.login(username, password, self.log, manual_uid)
                
                def update_ui():
                    if success: 
                        self.status_label. config(text="状态: 已登录 (API)", fg='#00ff88')
                        self.login_btn. config(text="✓ 已登录", state='disabled')
                        self.bet_frame.pack(fill='x', padx=10, pady=5)
                        self.control_frame.pack(fill='x', padx=10, pady=10)
                        
                        if self.bot.api.uid:
                            self. uid_entry.delete(0, tk.END)
                            self.uid_entry. insert(0, self.bot. api.uid)
                            self.uid_label.config(text=f"UID: {self.bot.api.uid}", fg='#00ff88')
                        
                        self.create_odds_display_area(self.right_frame)
                        self.save_config()
                        self. refresh_data()
                    else:
                        self.status_label.config(text="状态: 登录失败", fg='#ff4444')
                        self.login_btn. config(state='normal', text="登录")
                
                self.root.after(0, update_ui)
            except Exception as e:
                self.log(f"登录异常: {e}")
                def update_ui():
                    self.status_label.config(text="状态: 登录失败", fg='#ff4444')
                    self.login_btn.config(state='normal', text="登录")
                self.root.after(0, update_ui)
        
        threading.Thread(target=login_thread, daemon=True).start()
    
    def start_monitoring(self):
        """开始监控"""
        if not self.bot.api.uid:
            manual_uid = self.uid_entry.get().strip()
            if manual_uid:
                self.bot.api.set_uid(manual_uid)
                self.log(f"使用手动输入的UID: {manual_uid}")
            else:
                messagebox.showwarning("警告", "UID未设置！\n\n请在UID输入框中输入UID")
                return
        
        try:
            interval = float(self.interval_entry.get())
            amount = float(self.amount_entry.get())
            threshold = float(self.threshold_entry.get())
        except ValueError:
            messagebox. showerror("错误", "请输入有效数字")
            return
        
        if interval < 1:
            messagebox.showwarning("警告", "刷新间隔不能小于1秒")
            return
        
        self. bot.bet_amount = amount
        self. bot.odds_threshold = threshold
        self.bot.auto_bet_enabled = self.auto_bet_var.get()
        self.bot.is_running = True
        self.save_config()
        
        self.start_btn.config(state='disabled')
        self.stop_btn.config(state='normal')
        self.status_label.config(text="状态:  监控中 (API).. .", fg='#00ff88')
        
        self.log(f"🚀 开始监控 | 间隔:{interval}秒 | 阈值:{threshold} | 金额:{amount}")
        
        self.monitor_thread = threading.Thread(
            target=self.bot.monitor_realtime,
            args=(interval, self.log, self.update_odds_display),
            daemon=True
        )
        self.monitor_thread.start()
    
    def stop_monitoring(self):
        """停止监控"""
        self.bot.is_running = False
        self.start_btn.config(state='normal')
        self.stop_btn.config(state='disabled')
        self.status_label.config(text="状态: 已停止", fg='#ffaa00')
        self.update_label. config(text="⏹ 已停止", fg='#ffaa00')
        self.log("监控已停止")
    
    def refresh_data(self):
        """手动刷新数据"""
        manual_uid = self.uid_entry.get().strip()
        if manual_uid and manual_uid != self.bot. api.uid:
            self. bot.api.set_uid(manual_uid)
            self.log(f"更新UID: {manual_uid}")
        
        def refresh_thread():
            self.log("正在刷新数据 (API)...")
            
            def update_status():
                self.update_label.config(text="🔄 刷新中.. .", fg='#ffaa00')
            self.root.after(0, update_status)
            
            try:
                data = self.bot.get_all_odds_data()
                
                if data['success']:
                    matches = data. get('matches', [])
                    total_odds = data.get('totalOdds', 0)
                    
                    home_count = sum(len(od. get('home', [])) for m in matches for od in m.get('odds', {}).values())
                    away_count = sum(len(od.get('away', [])) for m in matches for od in m.get('odds', {}).values())
                    draw_count = sum(len(od.get('draw', [])) for m in matches for od in m. get('odds', {}).values())
                    
                    self. update_odds_display(data)
                    self.log(f"✓ 获取 {len(matches)} 场比赛, {total_odds} 水位 (主:{home_count} 客:{away_count} 和:{draw_count})")
                    
                    for match in matches[: 3]: 
                        t1 = match.get('team1', '? ')[:20]
                        t2 = match.get('team2', '?')[:20]
                        s1, s2 = match.get('score1', '0'), match.get('score2', '0')
                        self.log(f"  {s1} {t1} vs {t2} {s2}")
                else:
                    self.update_odds_display(data)
                    self.log(f"❌ 获取失败: {data.get('error', '未知错误')[:60]}")
            except Exception as e:
                self. log(f"刷新失败: {e}")
        
        threading.Thread(target=refresh_thread, daemon=True).start()
    
    def diagnose_api(self):
        """API深度诊断"""
        def diagnose():
            self.log("\n" + "="*50)
            self.log("🔬 API深度诊断 v6.2")
            self.log("="*50)
            
            self.log(f"\n【1】UID检查")
            self.log(f"   API UID: {self.bot. api.uid or '❌ 未设置'}")
            self.log(f"   界面UID: {self.uid_entry.get().strip() or '空'}")
            
            self.log(f"\n【2】Cookies检查")
            self.log(f"   总数: {len(self.bot. api.cookies)}")
            if self.bot.api.cookies:
                for i, (key, value) in enumerate(list(self.bot.api.cookies.items())[:5], 1):
                    val_str = str(value)[: 20]
                    self.log(f"   {i}. {key}: {val_str}...")
            
            self.log(f"\n【3】SSL设置")
            self.log(f"   SSL验证: 已禁用 ✓")
            
            self.log(f"\n【4】测试API请求")
            test_result = self.bot.api.test_connection()
            
            if test_result. get('error'):
                self.log(f"   ❌ 请求失败: {test_result['error'][: 80]}")
            else:
                self.log(f"   状态码: {test_result['status_code']}")
                self.log(f"   响应长度: {test_result['response_length']} 字符")
                self.log(f"   有比赛数据: {'✓' if test_result['has_game_data'] else '✗'}")
                self.log(f"   有错误:  {'✗ 是' if test_result['has_error'] else '✓ 否'}")
                
                if test_result['has_game_data'] and not test_result['has_error']: 
                    self.log(f"\n   ✓ API工作正常!")
                else:
                    self.log(f"\n   响应预览:")
                    self.log(f"   {test_result['raw_preview'][:150]}")
            
            if self.bot.driver:
                self.log(f"\n【5】重新提取UID")
                uid = self.bot.extract_uid_from_page(self.log)
                if uid:
                    self.bot.api.set_uid(uid)
                    def update_uid():
                        self.uid_entry.delete(0, tk.END)
                        self. uid_entry.insert(0, uid)
                    self.root.after(0, update_uid)
            
            self.log(f"\n" + "="*50)
            self.log("诊断完成")
            self.log("="*50)
        
        threading.Thread(target=diagnose, daemon=True).start()
    
    def show_today_bets(self):
        """显示今日注单"""
        def fetch_bets():
            self.log("\n查看今日注单...")
            
            result = self.bot.api.get_today_bets()
            
            if result['success']:
                bets = result.get('bets', [])
                total = result.get('total_bet', 0)
                
                self.log(f"\n{'='*40}")
                self.log(f"📋 今日注单:  {len(bets)} 笔")
                self.log(f"总投注: {total} RMB")
                
                if bets:
                    for i, bet in enumerate(bets[:10], 1):
                        self.log(f"{i}.  ID:{bet. get('w_id', 'N/A')} 金额:{bet.get('gold', 0)} 赔率:{bet.get('ioratio', 0)}")
                else:
                    self.log("今日暂无注单")
                
                self.log(f"{'='*40}")
            else:
                self.log(f"❌ 获取失败: {result.get('error', '未知错误')}")
        
        threading.Thread(target=fetch_bets, daemon=True).start()
    
    def on_closing(self):
        """关闭窗口"""
        if messagebox.askokcancel("退出", "确定退出程序？"):
            self.save_config()
            self.bot.stop()
            self.root.destroy()


# ================== 主程序入口 ==================
if __name__ == "__main__":
    root = tk.Tk()
    app = BettingBotGUI(root)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    root.mainloop()
