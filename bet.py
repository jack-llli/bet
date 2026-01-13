#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
滚球水位实时监控系统 v6.9
- 彻底修复ver参数问题
- ver格式必须是:  YYYY-MM-DD-mtfix_133 (固定后缀_133)
- cookie中的_211228是旧版本号，不应使用
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
from tkinter import ttk, messagebox, scrolledtext, filedialog
import threading
from datetime import datetime
import re
import json
import os
import base64

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ================== 配置 ==================
URL = "https://mos055.com/"
API_URL = "https://mos055.com/transform.php"
USERNAME = "LJJ123123"
PASSWORD = "zz66688899"
COOKIES_FILE = "mos055_cookies.pkl"
CONFIG_FILE = "bet_config.json"
HAR_DATA_FILE = "har_data. json"
BET_TYPES_ORDER = ['让球', '大/小', '独赢', '让球上半场', '大/小上半场', '独赢上半场', '下个进球', '双方球队进球']


class DataCollector:
    """数据收集器"""
    
    def __init__(self, filename=HAR_DATA_FILE):
        self.filename = filename
        self.entries = []
        self.start_time = datetime.now().isoformat()
        self.lock = threading.Lock()
        
        self.har_data = {
            "log": {
                "version": "1.2",
                "creator":  {"name": "BettingBot", "version": "6.9"},
                "browser": {"name": "Chrome", "version": "120.0"},
                "pages": [],
                "entries": []
            },
            "metadata": {
                "start_time": self.start_time,
                "total_requests": 0,
                "total_matches":  0,
                "total_odds": 0
            }
        }
        self.load_existing()
    
    def load_existing(self):
        try:
            if os.path.exists(self. filename):
                with open(self.filename, 'r', encoding='utf-8') as f:
                    existing = json.load(f)
                    if 'log' in existing and 'entries' in existing['log']:
                        self.har_data = existing
                        self.entries = existing['log']['entries']
        except: 
            pass
    
    def add_entry(self, request_data, response_data, parsed_data=None):
        with self.lock:
            entry = {
                "startedDateTime": datetime.now().isoformat(),
                "time": response_data. get('elapsed_time', 0),
                "request": {
                    "method":  request_data.get('method', 'POST'),
                    "url": request_data.get('url', ''),
                    "httpVersion": "HTTP/1.1",
                    "headers": request_data.get('headers', []),
                    "queryString": request_data.get('params', []),
                    "postData": {
                        "mimeType":  "application/x-www-form-urlencoded",
                        "text": request_data.get('body', ''),
                        "params": request_data.get('form_data', [])
                    },
                    "cookies": request_data.get('cookies', [])
                },
                "response":  {
                    "status": response_data.get('status_code', 0),
                    "statusText":  response_data.get('status_text', ''),
                    "httpVersion": "HTTP/1.1",
                    "headers":  response_data.get('headers', []),
                    "content":  {
                        "size": len(response_data.get('text', '')),
                        "mimeType": response_data.get('content_type', 'text/xml'),
                        "text": response_data.get('text', ''),
                        "encoding": "utf-8"
                    },
                    "cookies": []
                },
                "cache": {},
                "timings": {"send": 0, "wait":  response_data.get('elapsed_time', 0), "receive": 0},
                "_parsed": parsed_data
            }
            
            self.entries.append(entry)
            self.har_data['log']['entries'] = self.entries
            self.har_data['metadata']['total_requests'] = len(self.entries)
            
            if parsed_data:
                self.har_data['metadata']['total_matches'] = parsed_data.get('match_count', 0)
                self. har_data['metadata']['total_odds'] = parsed_data.get('odds_count', 0)
            
            self.save()
            return entry
    
    def add_match_data(self, matches, total_odds):
        with self.lock:
            snapshot = {
                "timestamp": datetime.now().isoformat(),
                "match_count": len(matches),
                "total_odds": total_odds,
                "matches": matches
            }
            self.har_data['log']['pages'].append({
                "startedDateTime": snapshot['timestamp'],
                "id": f"snapshot_{len(self.har_data['log']['pages'])}",
                "title": f"比赛数据快照 - {len(matches)}场比赛",
                "pageTimings": {"onContentLoad": 0, "onLoad": 0},
                "_data": snapshot
            })
            self.save()
    
    def save(self):
        try:
            with open(self.filename, 'w', encoding='utf-8') as f:
                json.dump(self.har_data, f, ensure_ascii=False, indent=2)
        except:
            pass
    
    def export(self, export_filename=None):
        if not export_filename:
            export_filename = f"har_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        try:
            with open(export_filename, 'w', encoding='utf-8') as f:
                json.dump(self.har_data, f, ensure_ascii=False, indent=2)
            return export_filename
        except: 
            return None
    
    def get_statistics(self):
        return {
            "total_entries": len(self.entries),
            "total_pages": len(self.har_data['log']['pages']),
            "start_time": self.start_time,
            "file_size": os.path.getsize(self.filename) if os.path.exists(self.filename) else 0
        }
    
    def clear(self):
        with self.lock:
            self.entries = []
            self.har_data['log']['entries'] = []
            self.har_data['log']['pages'] = []
            self.har_data['metadata']['total_requests'] = 0
            self.save()


class BettingAPI:
    """投注API类 - v6.9 彻底修复ver"""
    
    def __init__(self, data_collector=None):
        self.session = requests.Session()
        self.base_url = "https://mos055.com/transform.php"
        self. cookies = {}
        self.uid = ""
        self.ver = None
        self.langx = "zh-cn"
        self.session.verify = False
        self. collector = data_collector or DataCollector()
        
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept':  'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'X-Requested-With': 'XMLHttpRequest',
            'Origin': 'https://mos055.com',
            'Referer': 'https://mos055.com/',
            'Connection': 'keep-alive',
        })
    
    def build_ver(self, date_str=None):
        """构建正确的ver参数 - 固定格式:  YYYY-MM-DD-mtfix_133"""
        if not date_str:
            date_str = datetime.now().strftime('%Y-%m-%d')
        return f"{date_str}-mtfix_133"
    
    def set_cookies(self, cookies_dict):
        """设置cookies并提取UID，ver使用固定格式"""
        self. cookies = cookies_dict
        self.session.cookies.update(cookies_dict)
        
        # 提取UID
        for key in cookies_dict. keys():
            match = re.search(r'_(\d{8})(?: _|$)', key)
            if match:
                self.uid = match.group(1)
                break
        
        if not self.uid:
            for key in cookies_dict.keys():
                match = re.search(r'_(\d{6,10})(?:_|$)', key)
                if match:
                    self.uid = match.group(1)
                    break
        
        # ver使用固定格式，不从cookie提取
        self.ver = self.build_ver()
        print(f"UID: {self.uid}, ver: {self.ver}")
    
    def set_uid(self, uid):
        if uid:
            match = re.search(r'(\d{8})', str(uid))
            if match: 
                self.uid = match. group(1)
            else:
                digits = re.sub(r'\D', '', str(uid))
                if len(digits) >= 8:
                    self. uid = digits[:8]
                elif len(digits) >= 6:
                    self.uid = digits
    
    def set_ver(self, ver):
        """手动设置ver"""
        if ver:
            ver = str(ver).strip()
            # 检查是否是完整格式
            if re.match(r'\d{4}-\d{2}-\d{2}-mtfix', ver):
                self.ver = ver
            elif re.match(r'\d{4}-\d{2}-\d{2}', ver):
                # 如果只有日期，补上后缀
                self.ver = f"{ver}-mtfix_133"
            else:
                # 其他情况使用默认格式
                self.ver = self.build_ver()
    
    def extract_uid_from_cookies(self):
        for key in self.cookies.keys():
            match = re.search(r'_(\d{8})(?:_|$)', key)
            if match:
                return match.group(1)
        return None
    
    def get_rolling_matches(self, gtype='ft', ltype=3, sorttype='L'):
        """获取滚球比赛列表"""
        try:
            # 确保ver格式正确
            if not self.ver or not re.match(r'\d{4}-\d{2}-\d{2}-mtfix', self. ver):
                self.ver = self.build_ver()
            
            params = {'ver': self.ver}
            
            data = {
                'p': 'get_game_list',
                'uid': self.uid,
                'langx': self. langx,
                'gtype': gtype. upper(),
                'showtype': 'live',
                'rtype': 'rb',
                'ltype': str(ltype),
                'sorttype': sorttype,
                'specialClick': '',
                'is498': 'N',
                'ts':  int(time.time() * 1000)
            }
            
            start_time = time.time()
            
            response = self.session.post(
                self.base_url,
                params=params,
                data=data,
                timeout=30,
                verify=False
            )
            
            elapsed_time = (time.time() - start_time) * 1000
            
            # 记录请求数据
            request_data = {
                'method': 'POST',
                'url': f"{self.base_url}?ver={self.ver}",
                'headers': [{'name': k, 'value': v} for k, v in self.session. headers.items()],
                'params': [{'name': 'ver', 'value': self.ver}],
                'body': '&'.join([f"{k}={v}" for k, v in data.items()]),
                'form_data': [{'name': k, 'value': str(v)} for k, v in data.items()],
                'cookies': [{'name': k, 'value': v} for k, v in self.cookies.items()]
            }
            
            response_data = {
                'status_code': response.status_code,
                'status_text': 'OK' if response.status_code == 200 else 'Error',
                'headers': [{'name': k, 'value': v} for k, v in response.headers.items()],
                'content_type': response.headers.get('Content-Type', 'text/xml'),
                'text': response. text,
                'elapsed_time': elapsed_time
            }
            
            if response.status_code != 200:
                self.collector.add_entry(request_data, response_data, {
                    'success': False, 'error': f'HTTP {response.status_code}',
                    'match_count': 0, 'odds_count': 0
                })
                return {'success': False, 'error':  f'HTTP {response.status_code}', 'matches': [], 'totalOdds': 0}
            
            xml_text = response.text
            
            if 'table id error' in xml_text. lower():
                self.collector. add_entry(request_data, response_data, {
                    'success': False, 'error': 'table id error',
                    'match_count': 0, 'odds_count': 0, 'used_ver': self.ver
                })
                return {
                    'success': False,
                    'error': f'table id error',
                    'matches': [],
                    'totalOdds': 0,
                    'hint': f'UID: {self.uid}, ver: {self.ver}\n请检查UID是否正确，或尝试不同日期的ver'
                }
            
            if xml_text.strip() == 'CheckEMNU':
                self.collector. add_entry(request_data, response_data, {
                    'success': False, 'error': 'CheckEMNU', 'match_count': 0, 'odds_count': 0
                })
                return {'success': False, 'error':  'CheckEMNU - 权限检查失败', 'matches':  [], 'totalOdds':  0}
            
            # 解析XML
            matches, total_odds = self._parse_game_list_xml(xml_text)
            
            parsed_data = {
                'success': True,
                'match_count': len(matches),
                'odds_count': total_odds,
                'used_ver': self.ver,
                'used_uid': self.uid,
                'matches_summary': [
                    {'gid': m['gid'], 'league': m['league'], 'team1': m['team1'], 'team2': m['team2'],
                     'score': f"{m['score1']}-{m['score2']}", 'time': m['time']} for m in matches
                ]
            }
            
            self.collector.add_entry(request_data, response_data, parsed_data)
            self.collector.add_match_data(matches, total_odds)
            
            return {
                'success': True, 'matches': matches, 'totalOdds': total_odds,
                'total_count': len(matches), 'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            return {'success': False, 'error':  str(e), 'matches': [], 'totalOdds': 0}
    
    def _parse_game_list_xml(self, xml_text):
        """解析滚球比赛XML"""
        matches = []
        total_odds = 0
        
        try:
            xml_text = re.sub(r'<\? xml[^>]*\?>', '', xml_text)
            xml_text = xml_text.strip().lstrip('\ufeff')
            
            if not xml_text:
                return matches, total_odds
            
            root = ET.fromstring(xml_text)
            
            for ec in root.findall('. //ec'):
                for game in ec.findall('game'):
                    match = self._extract_game_data(game)
                    if match and (match['team1'] or match['team2']):
                        match_odds = self._count_match_odds(match)
                        total_odds += match_odds
                        matches.append(match)
            
            if not matches:
                for game in root.findall('. //game'):
                    match = self._extract_game_data(game)
                    if match and (match['team1'] or match['team2']):
                        match_odds = self._count_match_odds(match)
                        total_odds += match_odds
                        matches.append(match)
                        
        except ET.ParseError as e:
            print(f"XML解析错误: {e}")
            matches = self._fallback_regex_parse(xml_text)
            total_odds = sum(self._count_match_odds(m) for m in matches)
        except Exception as e:
            print(f"解析错误: {e}")
        
        return matches, total_odds
    
    def _extract_game_data(self, game_node):
        """从<game>节点提取比赛数据"""
        try:
            def get_text(tag, default=''):
                elem = game_node.find(tag)
                if elem is not None and elem.text:
                    return elem.text. strip()
                return default
            
            match = {
                'gid': get_text('GID') or game_node.get('id', ''),
                'league': get_text('LEAGUE', '未知联赛'),
                'team1': get_text('TEAM_H', ''),
                'team2': get_text('TEAM_C', ''),
                'score1': get_text('SCORE_H', '0'),
                'score2': get_text('SCORE_C', '0'),
                'time':  get_text('RETIMESET', ''),
                'datetime': get_text('DATETIME', ''),
                'odds':  {bt: {'handicap': '', 'home': [], 'away': [], 'draw': []} for bt in BET_TYPES_ORDER}
            }
            
            time_str = match['time']
            if '^' in time_str:
                parts = time_str.split('^')
                period = parts[0]
                time_val = parts[1] if len(parts) > 1 else ''
                period_map = {'1H': '上半场', '2H': '下半场', 'HT': '中场'}
                match['time'] = f"{period_map. get(period, period)} {time_val}"
            
            # 让球盘
            match['odds']['让球']['handicap'] = get_text('RATIO_RE')
            ior_reh = self._parse_odds(get_text('IOR_REH'))
            ior_rec = self._parse_odds(get_text('IOR_REC'))
            if ior_reh > 0:
                match['odds']['让球']['home']. append({'value': ior_reh, 'text': str(ior_reh), 'wtype': 'RE', 'rtype': 'REH', 'chose_team': 'H'})
            if ior_rec > 0:
                match['odds']['让球']['away']. append({'value': ior_rec, 'text': str(ior_rec), 'wtype': 'RE', 'rtype': 'REC', 'chose_team': 'C'})
            
            # 大小盘
            match['odds']['大/小']['handicap'] = get_text('RATIO_ROUO') or get_text('RATIO_ROUU')
            ior_rouh = self._parse_odds(get_text('IOR_ROUH'))
            ior_rouc = self._parse_odds(get_text('IOR_ROUC'))
            if ior_rouh > 0:
                match['odds']['大/小']['home'].append({'value': ior_rouh, 'text': str(ior_rouh), 'wtype': 'ROU', 'rtype': 'ROUH', 'chose_team': 'H'})
            if ior_rouc > 0:
                match['odds']['大/小']['away'].append({'value': ior_rouc, 'text': str(ior_rouc), 'wtype': 'ROU', 'rtype': 'ROUC', 'chose_team': 'C'})
            
            # 独赢盘
            ior_rmh = self._parse_odds(get_text('IOR_RMH'))
            ior_rmn = self._parse_odds(get_text('IOR_RMN'))
            ior_rmc = self._parse_odds(get_text('IOR_RMC'))
            if ior_rmh > 0:
                match['odds']['独赢']['home'].append({'value': ior_rmh, 'text': str(ior_rmh), 'wtype': 'RM', 'rtype': 'RMH', 'chose_team': 'H'})
            if ior_rmn > 0:
                match['odds']['独赢']['draw'].append({'value': ior_rmn, 'text': str(ior_rmn), 'wtype': 'RM', 'rtype': 'RMN', 'chose_team': 'N'})
            if ior_rmc > 0:
                match['odds']['独赢']['away'].append({'value': ior_rmc, 'text':  str(ior_rmc), 'wtype': 'RM', 'rtype': 'RMC', 'chose_team': 'C'})
            
            # 上半场让球
            match['odds']['让球上半场']['handicap'] = get_text('RATIO_HRE')
            ior_hreh = self._parse_odds(get_text('IOR_HREH'))
            ior_hrec = self._parse_odds(get_text('IOR_HREC'))
            if ior_hreh > 0:
                match['odds']['让球上半场']['home'].append({'value': ior_hreh, 'text': str(ior_hreh), 'wtype': 'HRE', 'rtype': 'HREH', 'chose_team': 'H'})
            if ior_hrec > 0:
                match['odds']['让球上半场']['away'].append({'value': ior_hrec, 'text': str(ior_hrec), 'wtype': 'HRE', 'rtype': 'HREC', 'chose_team':  'C'})
            
            # 上半场大小
            match['odds']['大/小上半场']['handicap'] = get_text('RATIO_HROUO') or get_text('RATIO_HROUU')
            ior_hrouh = self._parse_odds(get_text('IOR_HROUH'))
            ior_hrouc = self._parse_odds(get_text('IOR_HROUC'))
            if ior_hrouh > 0:
                match['odds']['大/小上半场']['home'].append({'value': ior_hrouh, 'text':  str(ior_hrouh), 'wtype': 'HROU', 'rtype': 'HROUH', 'chose_team': 'H'})
            if ior_hrouc > 0:
                match['odds']['大/小上半场']['away'].append({'value':  ior_hrouc, 'text': str(ior_hrouc), 'wtype': 'HROU', 'rtype': 'HROUC', 'chose_team': 'C'})
            
            # 上半场独赢
            ior_hrmh = self._parse_odds(get_text('IOR_HRMH'))
            ior_hrmn = self._parse_odds(get_text('IOR_HRMN'))
            ior_hrmc = self._parse_odds(get_text('IOR_HRMC'))
            if ior_hrmh > 0:
                match['odds']['独赢上半场']['home']. append({'value': ior_hrmh, 'text': str(ior_hrmh), 'wtype': 'HRM', 'rtype': 'HRMH', 'chose_team': 'H'})
            if ior_hrmn > 0:
                match['odds']['独赢上半场']['draw'].append({'value': ior_hrmn, 'text': str(ior_hrmn), 'wtype': 'HRM', 'rtype': 'HRMN', 'chose_team': 'N'})
            if ior_hrmc > 0:
                match['odds']['独赢上半场']['away'].append({'value': ior_hrmc, 'text':  str(ior_hrmc), 'wtype': 'HRM', 'rtype': 'HRMC', 'chose_team': 'C'})
            
            # 下个进球
            ior_rgh = self._parse_odds(get_text('IOR_RGH'))
            ior_rgn = self._parse_odds(get_text('IOR_RGN'))
            ior_rgc = self._parse_odds(get_text('IOR_RGC'))
            if ior_rgh > 0:
                match['odds']['下个进球']['home'].append({'value':  ior_rgh, 'text': str(ior_rgh), 'wtype': 'RG', 'rtype': 'RGH', 'chose_team': 'H'})
            if ior_rgn > 0:
                match['odds']['下个进球']['draw'].append({'value': ior_rgn, 'text': str(ior_rgn), 'wtype': 'RG', 'rtype': 'RGN', 'chose_team': 'N'})
            if ior_rgc > 0:
                match['odds']['下个进球']['away'].append({'value': ior_rgc, 'text':  str(ior_rgc), 'wtype': 'RG', 'rtype': 'RGC', 'chose_team': 'C'})
            
            # 双方球队进球
            ior_rtsy = self._parse_odds(get_text('IOR_RTSY'))
            ior_rtsn = self._parse_odds(get_text('IOR_RTSN'))
            if ior_rtsy > 0:
                match['odds']['双方球队进球']['home']. append({'value': ior_rtsy, 'text': str(ior_rtsy), 'wtype': 'RTS', 'rtype': 'RTSY', 'chose_team': 'H'})
            if ior_rtsn > 0:
                match['odds']['双方球队进球']['away'].append({'value': ior_rtsn, 'text':  str(ior_rtsn), 'wtype': 'RTS', 'rtype':  'RTSN', 'chose_team': 'C'})
            
            return match
        except Exception as e:
            print(f"提取比赛数据错误: {e}")
            return None
    
    def _parse_odds(self, odds_str):
        try:
            if not odds_str:
                return 0.0
            val = float(str(odds_str).strip())
            if val > 50:
                val = val / 100
            return round(val, 2)
        except:
            return 0.0
    
    def _count_match_odds(self, match):
        count = 0
        for bt, od in match. get('odds', {}).items():
            count += len(od. get('home', [])) + len(od.get('away', [])) + len(od.get('draw', []))
        return count
    
    def _fallback_regex_parse(self, xml_text):
        matches = []
        game_blocks = re.findall(r'<game[^>]*>.*?</game>', xml_text, re. DOTALL | re.IGNORECASE)
        for block in game_blocks:
            def extract(pattern):
                m = re.search(pattern, block, re.IGNORECASE)
                return m.group(1) if m else ''
            team_h = extract(r'<TEAM_H>([^<]+)</TEAM_H>')
            team_c = extract(r'<TEAM_C>([^<]+)</TEAM_C>')
            if team_h and team_c: 
                match = {
                    'gid': extract(r'<GID>(\d+)</GID>'),
                    'league': extract(r'<LEAGUE>([^<]+)</LEAGUE>') or '未知联赛',
                    'team1': team_h, 'team2': team_c,
                    'score1':  extract(r'<SCORE_H>(\d*)</SCORE_H>') or '0',
                    'score2': extract(r'<SCORE_C>(\d*)</SCORE_C>') or '0',
                    'time': extract(r'<RETIMESET>([^<]*)</RETIMESET>'),
                    'odds': {bt: {'handicap':  '', 'home': [], 'away': [], 'draw': []} for bt in BET_TYPES_ORDER}
                }
                matches.append(match)
        return matches
    
    def place_bet(self, gid, wtype, rtype, chose_team, ioratio, gold, gtype='FT'):
        try:
            params = {'ver': self.ver}
            data = {
                'p': 'FT_bet', 'golds': gold, 'gid': gid, 'gtype': gtype,
                'wtype': wtype, 'rtype': rtype, 'chose_team': chose_team,
                'ioratio': ioratio, 'autoOdd': 'Y', 'isRB': 'Y',
                'uid': self.uid, 'langx': self.langx, 'ts': int(time.time() * 1000)
            }
            response = self.session.post(self.base_url, params=params, data=data, timeout=15, verify=False)
            if response.status_code != 200:
                return {'success': False, 'error': f'HTTP {response.status_code}'}
            try:
                root = ET.fromstring(response. text)
                code = (root.findtext('. //code') or '').lower()
                if code == 'success':
                    return {
                        'success': True,
                        'ticket_id': root.findtext('.//ticket_id', ''),
                        'bet_amount': float(root.findtext('.//gold', '0') or 0),
                        'odds': float(root.findtext('.//ioratio', '0') or 0),
                        'balance': float(root.findtext('. //nowcredit', '0') or 0),
                        'message': '下注成功'
                    }
                else:
                    return {'success': False, 'error': root.findtext('.//message', '下注失败')}
            except: 
                if 'success' in response.text. lower():
                    return {'success': True, 'message': '下注成功'}
                return {'success': False, 'error': '解析响应失败'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def get_today_bets(self):
        try:
            params = {'ver': self.ver}
            data = {'p': 'get_today_wagers', 'uid': self. uid, 'langx': self.langx, 'ts': int(time.time() * 1000)}
            response = self.session.post(self.base_url, params=params, data=data, timeout=10, verify=False)
            try:
                json_data = json.loads(response.text)
                bets = []
                total_gold = 0.0
                if 'wagers' in json_data: 
                    for w in json_data['wagers']: 
                        bet = {'w_id': w. get('w_id', ''), 'gid': w.get('gid', ''),
                               'gold': float(w.get('gold', 0) or 0), 'ioratio': float(w.get('ioratio', 0) or 0),
                               'status': w.get('status', '')}
                        bets.append(bet)
                        total_gold += bet['gold']
                return {'success': True, 'bets': bets, 'total_bet':  total_gold, 'count': len(bets)}
            except:
                return {'success':  False, 'bets': [], 'error': '解析失败'}
        except Exception as e:
            return {'success': False, 'error': str(e), 'bets': []}
    
    def test_connection(self):
        try:
            if not self.ver or not re.match(r'\d{4}-\d{2}-\d{2}-mtfix', self.ver):
                self.ver = self.build_ver()
            
            params = {'ver': self. ver}
            data = {'p': 'get_game_list', 'uid': self.uid, 'showtype': 'live', 'rtype': 'rb',
                    'gtype': 'FT', 'ltype': '3', 'langx': self. langx, 'ts': int(time.time() * 1000)}
            response = self. session.post(self.base_url, params=params, data=data, timeout=10, verify=False)
            
            return {
                'status_code': response.status_code,
                'response_length': len(response.text),
                'has_error': 'error' in response.text.lower() or 'table id error' in response.text.lower(),
                'has_game_data': '<game' in response.text. lower() or '<GID>' in response.text,
                'has_ec_data': '<ec' in response.text.lower(),
                'is_check_menu': response.text.strip() == 'CheckEMNU',
                'raw_preview': response.text[: 500],
                'used_ver': self.ver,
                'used_uid': self.uid
            }
        except Exception as e:
            return {'error': str(e)}
    
    def try_different_vers(self):
        """尝试不同的ver格式"""
        results = []
        today = datetime.now()
        
        # 尝试今天和前几天的日期
        for days_ago in range(0, 7):
            date = today - __import__('datetime').timedelta(days=days_ago)
            date_str = date.strftime('%Y-%m-%d')
            ver = f"{date_str}-mtfix_133"
            
            try:
                params = {'ver':  ver}
                data = {'p': 'get_game_list', 'uid': self.uid, 'showtype': 'live', 'rtype': 'rb',
                        'gtype': 'FT', 'ltype': '3', 'langx': self.langx, 'ts': int(time.time() * 1000)}
                response = self.session. post(self.base_url, params=params, data=data, timeout=10, verify=False)
                
                success = '<game' in response.text.lower() or '<GID>' in response.text
                error = 'table id error' in response.text. lower()
                
                results.append({
                    'ver': ver, 'status':  response.status_code, 'length': len(response.text),
                    'success': success, 'error': error, 'preview': response.text[:100]
                })
                
                if success:
                    self.ver = ver
                    return results
                    
            except Exception as e:
                results.append({'ver': ver, 'error':  str(e)})
        
        return results


class BettingBot:
    """投注机器人核心类"""
    
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
        self.collector = DataCollector()
        self.api = BettingAPI(self. collector)
    
    def setup_driver(self, headless=False):
        options = webdriver.ChromeOptions()
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option('useAutomationExtension', False)
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--ignore-certificate-errors")
        options.add_argument("--ignore-ssl-errors")
        options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
        options.set_capability('goog:loggingPrefs', {'performance':  'ALL', 'browser': 'ALL'})
        if headless:
            options.add_argument("--headless=new")
        self.driver = webdriver.Chrome(options=options)
        self.wait = WebDriverWait(self. driver, 60)
        self.driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
            'source': 'Object.defineProperty(navigator, "webdriver", {get: () => undefined});'
        })
    
    def handle_password_popup(self, log_callback):
        for _ in range(10):
            try:
                result = self.driver.execute_script("""
                    var els = document.querySelectorAll('div, button, span');
                    for (var e of els) {
                        if (e.innerText.trim() === '否' && e.offsetWidth > 0) {
                            e.click(); return true;
                        }
                    }
                    return false;
                """)
                if result: 
                    log_callback("  ✓ 关闭弹窗")
                    time.sleep(1)
                else:
                    break
            except:
                pass
            time.sleep(1)
    
    def extract_uid_from_page(self, log_callback):
        log_callback("  方法1: 从网络请求提取...")
        try:
            logs = self.driver.get_log('performance')
            for entry in logs[-200:]: 
                try:
                    msg = json.loads(entry['message'])
                    if 'message' in msg: 
                        m = msg['message']
                        if m.get('method') == 'Network.requestWillBeSent':
                            post_data = m.get('params', {}).get('request', {}).get('postData', '')
                            if 'uid=' in post_data:
                                match = re.search(r'uid=(\d{8})(? : &|$)', post_data)
                                if match:
                                    uid = match.group(1)
                                    log_callback(f"    ✓ 找到UID: {uid}")
                                    return uid
                except:
                    pass
        except Exception as e:
            log_callback(f"    失败: {e}")
        
        log_callback("  方法2: 从cookies名称提取...")
        try:
            cookies = self.driver.get_cookies()
            for c in cookies:
                name = c['name']
                match = re.search(r'_(\d{8})(?:_|$)', name)
                if match: 
                    uid = match.group(1)
                    log_callback(f"    ✓ 从cookie '{name}' 找到UID: {uid}")
                    return uid
        except Exception as e:
            log_callback(f"    失败: {e}")
        
        log_callback("  ✗ 未找到UID")
        return None
    
    def extract_ver_from_network(self, log_callback):
        """从网络请求中提取ver参数"""
        log_callback("  从网络请求提取ver...")
        try:
            logs = self.driver.get_log('performance')
            for entry in logs[-300:]:
                try:
                    msg = json.loads(entry['message'])
                    if 'message' in msg:
                        m = msg['message']
                        if m.get('method') == 'Network.requestWillBeSent':
                            url = m.get('params', {}).get('request', {}).get('url', '')
                            if 'transform. php' in url and 'ver=' in url:
                                match = re.search(r'ver=([^&]+)', url)
                                if match:
                                    ver = match.group(1)
                                    # 只接受正确格式的ver
                                    if re.match(r'\d{4}-\d{2}-\d{2}-mtfix', ver):
                                        log_callback(f"    ✓ 找到ver: {ver}")
                                        return ver
                except:
                    pass
        except Exception as e:
            log_callback(f"    失败: {e}")
        return None
    
    def login(self, username, password, log_callback, manual_uid=None):
        try:
            log_callback("访问登录页面...")
            self.driver.get(URL)
            time.sleep(8)

            self.driver.execute_script(f"""
                var inputs = document.querySelectorAll('input');
                for(var i of inputs) {{ if(i.type==='text' && i.offsetWidth>0) {{ i.value='{username}'; i.dispatchEvent(new Event('input',{{bubbles:true}})); break; }} }}
            """)
            self.driver.execute_script(f"""
                var inputs = document. querySelectorAll('input[type="password"]');
                for(var i of inputs) {{ if(i.offsetWidth>0) {{ i.value='{password}'; i.dispatchEvent(new Event('input',{{bubbles:true}})); break; }} }}
            """)
            log_callback(f"✓ 输入凭据: {username}")
            time.sleep(1)

            self.driver.execute_script("""
                var btn = document.getElementById('btn_login');
                if(btn) btn.click();
                else {
                    var els = document. querySelectorAll('button, div, span');
                    for(var e of els) { if((e.innerText. trim()==='登录'||e.innerText.trim()==='登入') && e.offsetWidth>0) { e.click(); break; } }
                }
            """)
            log_callback("✓ 点击登录")
            time.sleep(10)

            self.handle_password_popup(log_callback)
            time.sleep(3)

            log_callback("\n提取Cookies...")
            cookies = self.driver.get_cookies()
            cookies_dict = {c['name']: c['value'] for c in cookies}
            log_callback(f"获取到 {len(cookies_dict)} 个cookies")
            
            log_callback("\nCookies详情:")
            for name, value in cookies_dict.items():
                if name.startswith('myGameVer_'):
                    try:
                        decoded = base64.b64decode(value).decode('utf-8')
                        log_callback(f"  ★ {name}:  {value} (解码: {decoded}) [不使用此值作为ver]")
                    except:
                        log_callback(f"  ★ {name}: {value}")
                elif name.startswith('login_'):
                    log_callback(f"  ★ {name}: {value[: 30]}...")
                else:
                    val_display = value[: 40] + '...' if len(value) > 40 else value
                    log_callback(f"  - {name}: {val_display}")
            
            self.api.set_cookies(cookies_dict)
            
            if manual_uid and manual_uid. strip():
                self.api.set_uid(manual_uid. strip())
                log_callback(f"✓ 使用手动UID: {self.api.uid}")
            
            if not self.api.uid or len(self.api.uid) < 6:
                log_callback("\n从页面提取UID...")
                uid = self.extract_uid_from_page(log_callback)
                if uid:
                    self.api.set_uid(uid)
            
            # ver使用固定格式
            self.api.ver = self.api.build_ver()
            log_callback(f"\n当前UID: {self.api.uid or '未设置'}")
            log_callback(f"当前ver: {self.api. ver} (固定格式)")

            with open(COOKIES_FILE, "wb") as f:
                pickle.dump(cookies, f)

            log_callback("\n进入滚球页面...")
            self.driver. execute_script("""
                var els = document.querySelectorAll('*');
                for(var e of els) { if(e.textContent.trim()==='滚球' && e.offsetWidth>0) { e.click(); break; } }
            """)
            time.sleep(5)

            # 尝试从网络请求中提取ver
            log_callback("\n从网络请求提取ver...")
            network_ver = self.extract_ver_from_network(log_callback)
            if network_ver: 
                self.api.ver = network_ver
                log_callback(f"✓ 使用网络请求中的ver: {network_ver}")

            if not self.api.uid or len(self.api.uid) < 6:
                log_callback("再次尝试提取UID...")
                uid = self.extract_uid_from_page(log_callback)
                if uid:
                    self. api.set_uid(uid)
                    log_callback(f"✓ UID更新:  {uid}")

            log_callback("\n测试API...")
            log_callback(f"API URL: {self.api.base_url}")
            log_callback(f"使用UID: {self.api.uid or '未设置'}")
            log_callback(f"使用ver: {self.api.ver or '未设置'}")
            
            test = self.api.test_connection()
            if test. get('error'):
                log_callback(f"✗ 错误: {test['error'][: 60]}")
            else:
                log_callback(f"状态: {test['status_code']}, 长度: {test['response_length']}")
                log_callback(f"有数据: {test['has_game_data']}, CheckEMNU: {test['is_check_menu']}")
                
                if test['has_game_data']:
                    log_callback("✓ API正常!")
                elif 'table id error' in test. get('raw_preview', '').lower():
                    log_callback("⚠ table id error - 尝试不同日期的ver...")
                    results = self.api.try_different_vers()
                    for r in results:
                        status = "✓" if r. get('success') else "✗"
                        log_callback(f"  {status} {r['ver']}:  {r. get('preview', r.get('error', ''))[:50]}")
                        if r.get('success'):
                            log_callback(f"  ✓ 找到有效ver: {r['ver']}")
                            break
                elif test['is_check_menu']:
                    log_callback("⚠ 返回CheckEMNU，需要正确UID")

            self.is_logged_in = True
            log_callback("\n✓ 登录完成!")
            return True

        except Exception as e:
            log_callback(f"✗ 登录失败: {e}")
            import traceback
            log_callback(traceback.format_exc())
            return False
    
    def get_all_odds_data(self):
        result = self.api.get_rolling_matches()
        if result['success']:
            self.current_matches = result['matches']
        return result
    
    def auto_bet_check(self, log_callback):
        if not self.auto_bet_enabled:
            return False
        for match in self.current_matches:
            for bt, type_odds in match.get('odds', {}).items():
                for team_type in ['home', 'away', 'draw']:
                    for odds in type_odds.get(team_type, []):
                        if odds['value'] >= self.odds_threshold and odds['value'] < 50:
                            bet_key = f"{match['gid']}_{bt}_{team_type}_{datetime.now().strftime('%Y%m%d%H')}"
                            if bet_key in self.bet_history:
                                continue
                            team_name = match['team1'] if team_type == 'home' else (match['team2'] if team_type == 'away' else '和局')
                            log_callback(f"\n🎯 触发下注!  {match['team1']} vs {match['team2']}")
                            log_callback(f"   {bt} {team_name} @ {odds['value']}")
                            result = self.api.place_bet(
                                gid=match['gid'], wtype=odds. get('wtype', 'RE'),
                                rtype=odds.get('rtype', 'REH'), chose_team=odds.get('chose_team', 'H'),
                                ioratio=odds['value'], gold=self.bet_amount
                            )
                            if result['success']: 
                                self.bet_history.append(bet_key)
                                log_callback(f"   ✓ 成功!")
                            else:
                                log_callback(f"   ✗ 失败: {result. get('error', '')}")
                            return result['success']
        return False
    
    def monitor_realtime(self, interval, log_callback, update_callback):
        log_callback(f"\n🚀 开始监控 | 间隔:{interval}s | 阈值:{self.odds_threshold}")
        log_callback(f"   UID:{self.api.uid} | ver:{self.api.ver}")
        log_callback(f"   数据收集:  已启用 → {HAR_DATA_FILE}")
        
        while self.is_running:
            try:
                data = self.get_all_odds_data()
                if data['success']:
                    update_callback(data)
                    stats = self.collector.get_statistics()
                    log_callback(f"[{datetime.now().strftime('%H:%M:%S')}] {len(data['matches'])}场, {data['totalOdds']}水位 | 已收集{stats['total_entries']}条")
                    if self.auto_bet_enabled:
                        self.auto_bet_check(log_callback)
                else:
                    log_callback(f"[{datetime.now().strftime('%H:%M:%S')}] ✗ {data. get('error', '')[:50]}")
                time.sleep(interval)
            except Exception as e:
                log_callback(f"✗ 错误: {e}")
                time.sleep(interval)
        log_callback("监控已停止")
    
    def stop(self):
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
        self.root.title("滚球水位实时监控系统 v6.9 (ver格式彻底修复)")
        self.root.geometry("1900x980")
        self.root.configure(bg='#1a1a2e')
        
        self.bot = BettingBot()
        self.monitor_thread = None
        
        self.create_widgets()
        self.load_config()
        self.update_collector_stats()
    
    def load_config(self):
        """加载配置"""
        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    config = json. load(f)
                    self.bot.odds_threshold = config.get('threshold', 1.80)
                    self.bot.bet_amount = config.get('bet_amount', 2)
                    self.threshold_entry.delete(0, tk.END)
                    self.threshold_entry.insert(0, str(self.bot.odds_threshold))
                    self.amount_entry.delete(0, tk.END)
                    self. amount_entry.insert(0, str(self.bot.bet_amount))
                    saved_uid = config.get('uid', '')
                    if saved_uid:
                        self.uid_entry.delete(0, tk.END)
                        self. uid_entry.insert(0, saved_uid)
                    # ver使用固定格式，不从配置加载
        except: 
            pass
    
    def save_config(self):
        """保存配置"""
        try:
            config = {
                'threshold': self.bot.odds_threshold,
                'bet_amount': self. bot.bet_amount,
                'uid': self.uid_entry.get().strip(),
                'ver': self.bot.api.ver or self.ver_entry.get().strip()
            }
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
        except:
            pass
    
    def create_widgets(self):
        """创建界面组件"""
        # ========== 标题 ==========
        title_frame = tk.Frame(self.root, bg='#1a1a2e')
        title_frame.pack(fill='x', padx=20, pady=10)
        
        tk.Label(title_frame, text="🎯 滚球水位实时监控系统 v6.9", bg='#1a1a2e', fg='#00ff88',
                font=('Microsoft YaHei UI', 22, 'bold')).pack()
        tk.Label(title_frame, text="ver格式彻底修复:  YYYY-MM-DD-mtfix_133 | cookie中的_211228是旧版本号不使用",
                bg='#1a1a2e', fg='#888', font=('Microsoft YaHei UI', 10)).pack()
        
        # ========== 主容器 ==========
        main_frame = tk.Frame(self. root, bg='#1a1a2e')
        main_frame.pack(fill='both', expand=True, padx=20, pady=10)
        
        # ========== 左侧面板 ==========
        left_frame = tk.Frame(main_frame, bg='#16213e', width=420)
        left_frame.pack(side='left', fill='y', padx=(0, 10))
        left_frame.pack_propagate(False)
        
        # ----- 登录区域 -----
        login_frame = tk.LabelFrame(left_frame, text="🔐 登录", bg='#16213e',
                                   fg='#00ff88', font=('Microsoft YaHei UI', 11, 'bold'), padx=10, pady=10)
        login_frame.pack(fill='x', padx=10, pady=(10, 5))
        
        tk.Label(login_frame, text="用户名:", bg='#16213e', fg='#fff',
                font=('Microsoft YaHei UI', 10)).grid(row=0, column=0, sticky='w', pady=3)
        self.username_entry = tk.Entry(login_frame, bg='#0f3460', fg='#fff',
                                      font=('Consolas', 10), insertbackground='#fff', relief='flat', width=30)
        self.username_entry.grid(row=0, column=1, pady=3, padx=(5, 0))
        self.username_entry.insert(0, USERNAME)
        
        tk.Label(login_frame, text="密码:", bg='#16213e', fg='#fff',
                font=('Microsoft YaHei UI', 10)).grid(row=1, column=0, sticky='w', pady=3)
        self.password_entry = tk.Entry(login_frame, show="*", bg='#0f3460', fg='#fff',
                                      font=('Consolas', 10), insertbackground='#fff', relief='flat', width=30)
        self.password_entry.grid(row=1, column=1, pady=3, padx=(5, 0))
        self.password_entry.insert(0, PASSWORD)
        
        tk.Label(login_frame, text="UID(8位):", bg='#16213e', fg='#ffaa00',
                font=('Microsoft YaHei UI', 10)).grid(row=2, column=0, sticky='w', pady=3)
        self.uid_entry = tk.Entry(login_frame, bg='#0f3460', fg='#ffaa00',
                                 font=('Consolas', 11, 'bold'), insertbackground='#fff', relief='flat', width=30)
        self.uid_entry.grid(row=2, column=1, pady=3, padx=(5, 0))
        
        tk.Label(login_frame, text="ver参数:", bg='#16213e', fg='#00ccff',
                font=('Microsoft YaHei UI', 10)).grid(row=3, column=0, sticky='w', pady=3)
        self.ver_entry = tk.Entry(login_frame, bg='#0f3460', fg='#00ccff',
                                 font=('Consolas', 10), insertbackground='#fff', relief='flat', width=30)
        self.ver_entry. grid(row=3, column=1, pady=3, padx=(5, 0))
        # 默认填入正确格式
        self.ver_entry.insert(0, datetime.now().strftime('%Y-%m-%d') + '-mtfix_133')
        
        # ver格式提示
        tk.Label(login_frame, text="✓ 正确格式: 2026-01-13-mtfix_133 (自动生成)", bg='#16213e', fg='#00ff88',
                font=('Microsoft YaHei UI', 8)).grid(row=4, column=0, columnspan=2, sticky='w')
        tk.Label(login_frame, text="✗ 错误格式: _211228 (cookie值，不要使用)", bg='#16213e', fg='#ff4444',
                font=('Microsoft YaHei UI', 8)).grid(row=5, column=0, columnspan=2, sticky='w')
        
        btn_row = tk.Frame(login_frame, bg='#16213e')
        btn_row.grid(row=6, column=0, columnspan=2, pady=(10, 0))
        
        self.login_btn = tk.Button(btn_row, text="登录", bg='#00ff88', fg='#000',
                                  font=('Microsoft YaHei UI', 10, 'bold'), relief='flat',
                                  command=self.login, cursor='hand2', padx=20, pady=3)
        self.login_btn.pack(side='left', padx=5)
        
        self.try_ver_btn = tk.Button(btn_row, text="尝试不同日期", bg='#ff9900', fg='#000',
                                    font=('Microsoft YaHei UI', 9), relief='flat',
                                    command=self.try_different_vers, cursor='hand2', padx=10, pady=3)
        self.try_ver_btn.pack(side='left', padx=5)
        
        # ----- 数据收集状态 -----
        collector_frame = tk.LabelFrame(left_frame, text="📊 数据收集", bg='#16213e',
                                       fg='#00ccff', font=('Microsoft YaHei UI', 11, 'bold'), padx=10, pady=10)
        collector_frame.pack(fill='x', padx=10, pady=5)
        
        self. collector_stats_label = tk.Label(collector_frame, text="请求:  0 | 快照: 0 | 文件: 0 KB",
                                             bg='#16213e', fg='#aaa', font=('Microsoft YaHei UI', 9))
        self.collector_stats_label. pack(anchor='w')
        
        self.collector_file_label = tk.Label(collector_frame, text=f"存储:  {HAR_DATA_FILE}",
                                            bg='#16213e', fg='#666', font=('Microsoft YaHei UI', 8))
        self.collector_file_label.pack(anchor='w')
        
        btn_frame = tk.Frame(collector_frame, bg='#16213e')
        btn_frame.pack(fill='x', pady=(5, 0))
        
        self.export_btn = tk.Button(btn_frame, text="📤 导出", bg='#336699', fg='#fff',
                                   font=('Microsoft YaHei UI', 9), relief='flat',
                                   command=self.export_har_data, cursor='hand2', padx=8)
        self.export_btn.pack(side='left', padx=(0, 3))
        
        self.view_btn = tk.Button(btn_frame, text="👁 查看", bg='#666', fg='#fff',
                                 font=('Microsoft YaHei UI', 9), relief='flat',
                                 command=self.view_har_data, cursor='hand2', padx=8)
        self.view_btn.pack(side='left', padx=(0, 3))
        
        self.clear_btn = tk.Button(btn_frame, text="🗑 清空", bg='#993333', fg='#fff',
                                  font=('Microsoft YaHei UI', 9), relief='flat',
                                  command=self.clear_har_data, cursor='hand2', padx=8)
        self.clear_btn.pack(side='left')
        
        # ----- 日志区域 -----
        log_frame = tk.LabelFrame(left_frame, text="📋 日志", bg='#16213e',
                                 fg='#888', font=('Microsoft YaHei UI', 10, 'bold'), padx=5, pady=5)
        log_frame.pack(fill='both', expand=True, padx=10, pady=5)
        
        self.log_text = scrolledtext.ScrolledText(log_frame, bg='#0f3460', fg='#00ff88',
                                                 font=('Consolas', 9), relief='flat', height=8, wrap='word')
        self.log_text.pack(fill='both', expand=True)
        
        # ----- 下注设置 -----
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
        self.threshold_entry = tk.Entry(self.bet_frame, bg='#0f3460', fg='#ffaa00',
                                       font=('Consolas', 12, 'bold'), insertbackground='#fff', relief='flat', width=8)
        self.threshold_entry.grid(row=2, column=1, pady=3, padx=(5, 0))
        self.threshold_entry.insert(0, "1.80")
        tk.Label(self.bet_frame, text="≥触发", bg='#16213e', fg='#888',
                font=('Microsoft YaHei UI', 9)).grid(row=2, column=2, padx=3)
        
        self.auto_bet_var = tk.BooleanVar(value=False)
        self.auto_bet_check = tk.Checkbutton(self. bet_frame, text="⚡ 启用自动下注",
                                            variable=self.auto_bet_var, bg='#16213e', fg='#ff4444',
                                            selectcolor='#0f3460', activebackground='#16213e',
                                            font=('Microsoft YaHei UI', 11, 'bold'), command=self.toggle_auto_bet)
        self.auto_bet_check.grid(row=3, column=0, columnspan=3, pady=(10, 0), sticky='w')
        
        # ----- 控制按钮 -----
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
        
        self.bets_btn = tk.Button(self.control_frame, text="📋 今日注单", bg='#336666',
                                 fg='#fff', font=('Microsoft YaHei UI', 10), relief='flat',
                                 command=self.show_today_bets, cursor='hand2', pady=6)
        self.bets_btn.pack(fill='x')
        
        # ========== 右侧数据区域 ==========
        self.right_frame = tk.Frame(main_frame, bg='#16213e')
        self.right_frame.pack(side='right', fill='both', expand=True)
        
        # 标题栏
        header_frame = tk.Frame(self.right_frame, bg='#16213e')
        header_frame.pack(fill='x', pady=(0, 5))
        
        tk.Label(header_frame, text="📊 实时水位数据", bg='#16213e',
                font=('Microsoft YaHei UI', 14, 'bold'), fg='#00ff88').pack(side='left')
        
        self.uid_label = tk.Label(header_frame, text="UID:  未设置", bg='#16213e',
                                 font=('Microsoft YaHei UI', 10, 'bold'), fg='#ff4444')
        self.uid_label.pack(side='left', padx=10)
        
        self.ver_label = tk.Label(header_frame, text="ver: 未设置", bg='#16213e',
                                 font=('Microsoft YaHei UI', 10), fg='#00ccff')
        self.ver_label.pack(side='left', padx=10)
        
        self.update_label = tk.Label(header_frame, text="", bg='#16213e',
                                    font=('Microsoft YaHei UI', 10), fg='#ffaa00')
        self.update_label.pack(side='right', padx=10)
        
        # 提示
        self.hint_label = tk.Label(self.right_frame,
                                  text="请先登录\n\nv6.9 关键修复:\n\n✓ ver格式:  YYYY-MM-DD-mtfix_133\n✗ 不使用cookie中的 _211228\n\n登录后自动使用正确的ver格式\n如果仍然失败，点击「尝试不同日期」",
                                  bg='#16213e', fg='#888', font=('Microsoft YaHei UI', 11), justify='center')
        self.hint_label.pack(pady=60)
        
        self.odds_canvas = None
        self.odds_inner_frame = None
        
        # 状态栏
        status_frame = tk.Frame(self.root, bg='#0f3460', height=30)
        status_frame.pack(side='bottom', fill='x')
        
        self.status_label = tk.Label(status_frame, text="状态: 未登录", bg='#0f3460',
                                    fg='#888', font=('Microsoft YaHei UI', 10), anchor='w', padx=20)
        self.status_label.pack(side='left', fill='y')
        
        self.time_label = tk.Label(status_frame, text="", bg='#0f3460',
                                  fg='#00ff88', font=('Microsoft YaHei UI', 10), anchor='e', padx=20)
        self.time_label.pack(side='right', fill='y')
    
    def update_collector_stats(self):
        """更新数据收集统计"""
        try:
            stats = self.bot.collector.get_statistics()
            file_size_kb = stats['file_size'] / 1024
            self.collector_stats_label.config(
                text=f"请求: {stats['total_entries']} | 快照: {stats['total_pages']} | 文件: {file_size_kb:.1f} KB"
            )
        except: 
            pass
        self.root.after(5000, self.update_collector_stats)
    
    def try_different_vers(self):
        """尝试不同日期的ver格式"""
        def try_vers():
            self.log("\n尝试不同日期的ver格式...")
            self.log("格式:  YYYY-MM-DD-mtfix_133")
            
            manual_uid = self.uid_entry.get().strip()
            if manual_uid:
                self.bot.api.set_uid(manual_uid)
            
            if not self.bot.api.uid:
                self.log("✗ 请先输入UID")
                return
            
            results = self.bot.api.try_different_vers()
            
            found_valid = False
            for r in results:
                if r. get('success'):
                    self.log(f"  ✓ 成功: {r['ver']}")
                    self.log(f"    响应长度: {r['length']}, 包含比赛数据")
                    
                    # 更新ver输入框
                    self.root.after(0, lambda v=r['ver']: (
                        self.ver_entry.delete(0, tk.END),
                        self. ver_entry.insert(0, v),
                        self.ver_label.config(text=f"ver: {v}", fg='#00ff88')
                    ))
                    found_valid = True
                    break
                elif r.get('error') and not isinstance(r. get('error'), bool):
                    self.log(f"  ✗ {r['ver']}: 异常 - {str(r['error'])[:40]}")
                else:
                    self.log(f"  ✗ {r['ver']}: {r. get('preview', '')[: 40]}")
            
            if found_valid:
                self.log("\n✓ 找到有效ver!  请点击刷新数据")
            else:
                self.log("\n✗ 所有日期��失败")
                self.log("请检查:")
                self.log("  1. UID是否正确 (8位数字)")
                self.log("  2. 网络连接是否正常")
                self.log("  3. 账号是否已登录")
        
        threading.Thread(target=try_vers, daemon=True).start()
    
    def export_har_data(self):
        """导出HAR数据"""
        filename = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON文件", "*.json"), ("所有文件", "*.*")],
            initialfilename=f"har_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )
        if filename:
            result = self.bot.collector.export(filename)
            if result: 
                self.log(f"✓ 数据已导出到:  {result}")
                messagebox.showinfo("导出成功", f"数据已导出到:\n{result}")
            else:
                self.log("✗ 导出失败")
                messagebox.showerror("导出失败", "数据导出失败")
    
    def view_har_data(self):
        """查看HAR数据"""
        view_window = tk.Toplevel(self.root)
        view_window.title("HAR数据查看器")
        view_window.geometry("1000x700")
        view_window.configure(bg='#1a1a2e')
        
        tk.Label(view_window, text="📊 HAR数据查看器", bg='#1a1a2e', fg='#00ff88',
                font=('Microsoft YaHei UI', 14, 'bold')).pack(pady=10)
        
        stats = self.bot.collector.get_statistics()
        stats_text = f"总请求: {stats['total_entries']} | 快照: {stats['total_pages']} | 文件大小: {stats['file_size']/1024:.1f} KB"
        tk.Label(view_window, text=stats_text, bg='#1a1a2e', fg='#aaa',
                font=('Microsoft YaHei UI', 10)).pack()
        
        text_frame = tk.Frame(view_window, bg='#1a1a2e')
        text_frame.pack(fill='both', expand=True, padx=20, pady=10)
        
        text_widget = scrolledtext.ScrolledText(text_frame, bg='#0f3460', fg='#00ff88',
                                               font=('Consolas', 9), wrap='word')
        text_widget.pack(fill='both', expand=True)
        
        try:
            har_data = self.bot.collector.har_data
            display_text = json.dumps(har_data, ensure_ascii=False, indent=2)
            text_widget.insert('1.0', display_text)
        except Exception as e: 
            text_widget.insert('1.0', f"加载数据失败: {e}")
        
        btn_frame = tk.Frame(view_window, bg='#1a1a2e')
        btn_frame.pack(pady=10)
        
        tk.Button(btn_frame, text="刷新", bg='#336699', fg='#fff',
                 command=lambda: self.refresh_har_view(text_widget)).pack(side='left', padx=5)
        tk.Button(btn_frame, text="关闭", bg='#666', fg='#fff',
                 command=view_window.destroy).pack(side='left', padx=5)
    
    def refresh_har_view(self, text_widget):
        """刷新HAR数据显示"""
        text_widget.delete('1.0', tk.END)
        try:
            har_data = self.bot.collector.har_data
            display_text = json. dumps(har_data, ensure_ascii=False, indent=2)
            text_widget.insert('1.0', display_text)
        except Exception as e: 
            text_widget.insert('1.0', f"加载数据失败: {e}")
    
    def clear_har_data(self):
        """清空HAR数据"""
        if messagebox.askyesno("确认", "确定要清空所有收集的数据吗？"):
            self.bot.collector. clear()
            self.log("✓ HAR数据已清空")
            self.update_collector_stats()
    
    def create_odds_display_area(self, parent):
        """创建水位显示区域"""
        if self.hint_label:
            self.hint_label.pack_forget()
        
        if self.odds_canvas:
            self.odds_canvas.master.destroy()
        
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
        self.odds_canvas.bind_all('<MouseWheel>', lambda e: self.odds_canvas. yview_scroll(int(-1*(e.delta/120)), 'units'))
    
    def update_odds_display(self, data):
        """更新水位显示"""
        def update():
            try:
                if not self.odds_inner_frame:
                    self.create_odds_display_area(self.right_frame)
                
                matches = data.get('matches', [])
                total_odds = data.get('totalOdds', 0)
                timestamp = datetime.now().strftime('%H:%M:%S')
                
                self.time_label.config(text=f"更新:  {timestamp}")
                self.update_label.config(text=f"🔄 {timestamp}", fg='#00ff88')
                
                uid = self.bot.api.uid
                ver = self.bot.api.ver
                self.uid_label.config(text=f"UID: {uid}" if uid else "UID: 未设置",
                                     fg='#00ff88' if uid and len(uid) >= 6 else '#ff4444')
                self.ver_label.config(text=f"ver: {ver}" if ver else "ver: 未设置",
                                     fg='#00ff88' if ver and 'mtfix' in ver else '#ff4444')
                
                for widget in self.odds_inner_frame.winfo_children():
                    widget.destroy()
                
                if not matches:
                    error = data.get('error', '')
                    hint = data.get('hint', '')
                    if error:
                        tk.Label(self.odds_inner_frame, text=f"❌ {error[: 100]}",
                                bg='#0f3460', fg='#ff4444', font=('Microsoft YaHei UI', 11), wraplength=800).pack(pady=10)
                        if hint:
                            tk.Label(self.odds_inner_frame, text=f"💡 {hint}",
                                    bg='#0f3460', fg='#ffaa00', font=('Microsoft YaHei UI', 10), wraplength=800).pack(pady=5)
                        tk.Label(self.odds_inner_frame, text="建议:  点击左侧「尝试不同日期」按钮",
                                bg='#0f3460', fg='#00ccff', font=('Microsoft YaHei UI', 10)).pack(pady=10)
                    else:
                        tk.Label(self.odds_inner_frame, text="暂无比赛数据",
                                bg='#0f3460', fg='#888', font=('Microsoft YaHei UI', 11)).pack(pady=20)
                    return
                
                # 统计
                stats = self.bot.collector.get_statistics()
                tk.Label(self.odds_inner_frame,
                        text=f"共 {len(matches)} 场比赛，{total_odds} 个水位 | 已收集 {stats['total_entries']} 条请求",
                        bg='#0f3460', fg='#00ff88', font=('Microsoft YaHei UI', 11, 'bold')).pack(anchor='w', padx=10, pady=5)
                
                current_league = ''
                threshold = self.bot.odds_threshold
                display_types = BET_TYPES_ORDER[: 6]
                
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
                            font=('Microsoft YaHei UI', 8), width=26, anchor='w').pack(side='left')
                    
                    for bt in display_types:
                        handicap = odds.get(bt, {}).get('handicap', '')
                        header = f"{bt}\n{handicap}" if handicap else bt
                        tk.Label(info_frame, text=header, bg='#1e1e32', fg='#aaa',
                                font=('Microsoft YaHei UI', 8), width=11, anchor='center').pack(side='left', padx=1)
                    
                    # 主队行
                    team1_frame = tk.Frame(match_frame, bg='#1e1e32')
                    team1_frame.pack(fill='x', pady=2, padx=5)
                    
                    s_color = '#ff4444' if score1 and score1. isdigit() and int(score1) > 0 else '#fff'
                    tk.Label(team1_frame, text=score1 or '0', bg='#1e1e32', fg=s_color,
                            font=('Microsoft YaHei UI', 11, 'bold'), width=3).pack(side='left')
                    
                    t1_display = team1[: 20] + '. .' if len(team1) > 22 else team1
                    tk.Label(team1_frame, text=t1_display, bg='#1e1e32', fg='#fff',
                            font=('Microsoft YaHei UI', 9), width=22, anchor='w').pack(side='left')
                    
                    for bt in display_types:
                        cell = tk.Frame(team1_frame, bg='#1e1e32', width=88)
                        cell.pack(side='left', padx=1)
                        cell.pack_propagate(False)
                        
                        home_odds = odds.get(bt, {}).get('home', [])
                        inner = tk.Frame(cell, bg='#1e1e32')
                        inner.pack(expand=True)
                        
                        if home_odds:
                            val = home_odds[0]['value']
                            color = '#ff4444' if val >= threshold else '#00ff88'
                            tk. Label(inner, text=str(val), bg='#1e1e32', fg=color,
                                    font=('Consolas', 10, 'bold')).pack()
                        else:
                            tk.Label(inner, text="-", bg='#1e1e32', fg='#444', font=('Consolas', 10)).pack()
                    
                    # 和局行
                    has_draw = any(odds.get(bt, {}).get('draw', []) for bt in ['独赢', '独赢上半场', '下个进球'])
                    if has_draw:
                        draw_frame = tk.Frame(match_frame, bg='#1e1e32')
                        draw_frame.pack(fill='x', pady=1, padx=5)
                        
                        tk.Label(draw_frame, text="", bg='#1e1e32', width=3).pack(side='left')
                        tk.Label(draw_frame, text="和局/无进球", bg='#1e1e32', fg='#aaa',
                                font=('Microsoft YaHei UI', 9), width=22, anchor='w').pack(side='left')
                        
                        for bt in display_types: 
                            cell = tk.Frame(draw_frame, bg='#1e1e32', width=88)
                            cell.pack(side='left', padx=1)
                            cell.pack_propagate(False)
                            
                            draw_odds = odds.get(bt, {}).get('draw', [])
                            inner = tk.Frame(cell, bg='#1e1e32')
                            inner.pack(expand=True)
                            
                            if draw_odds:
                                val = draw_odds[0]['value']
                                color = '#ff4444' if val >= threshold else '#00ccff'
                                tk.Label(inner, text=str(val), bg='#1e1e32', fg=color,
                                        font=('Consolas', 10, 'bold')).pack()
                            else:
                                tk.Label(inner, text="", bg='#1e1e32', font=('Consolas', 10)).pack()
                    
                    # 客队行
                    team2_frame = tk. Frame(match_frame, bg='#1e1e32')
                    team2_frame.pack(fill='x', pady=(0, 5), padx=5)
                    
                    s_color = '#ff4444' if score2 and score2.isdigit() and int(score2) > 0 else '#fff'
                    tk.Label(team2_frame, text=score2 or '0', bg='#1e1e32', fg=s_color,
                            font=('Microsoft YaHei UI', 11, 'bold'), width=3).pack(side='left')
                    
                    t2_display = team2[:20] + '..' if len(team2) > 22 else team2
                    tk.Label(team2_frame, text=t2_display, bg='#1e1e32', fg='#fff',
                            font=('Microsoft YaHei UI', 9), width=22, anchor='w').pack(side='left')
                    
                    for bt in display_types:
                        cell = tk.Frame(team2_frame, bg='#1e1e32', width=88)
                        cell.pack(side='left', padx=1)
                        cell.pack_propagate(False)
                        
                        away_odds = odds. get(bt, {}).get('away', [])
                        inner = tk.Frame(cell, bg='#1e1e32')
                        inner.pack(expand=True)
                        
                        if away_odds:
                            val = away_odds[0]['value']
                            color = '#ff4444' if val >= threshold else '#ffaa00'
                            tk. Label(inner, text=str(val), bg='#1e1e32', fg=color,
                                    font=('Consolas', 10, 'bold')).pack()
                        else:
                            tk.Label(inner, text="-", bg='#1e1e32', fg='#444', font=('Consolas', 10)).pack()
                
                self.odds_inner_frame.update_idletasks()
                self.odds_canvas.configure(scrollregion=self.odds_canvas.bbox('all'))
                
            except Exception as e:
                print(f"显示错误: {e}")
                import traceback
                traceback.print_exc()
        
        self.root.after(0, update)
    
    def log(self, message):
        """写日志"""
        def update_log():
            ts = datetime.now().strftime('%H:%M:%S')
            self.log_text.insert('end', f"[{ts}] {message}\n")
            self.log_text.see('end')
            lines = int(self.log_text.index('end-1c').split('.')[0])
            if lines > 500:
                self.log_text.delete('1.0', '200.0')
        self.root.after(0, update_log)
    
    def toggle_auto_bet(self):
        """切换自动下注"""
        if self.auto_bet_var.get():
            if messagebox.askyesno("确认", f"启用自动下注?\n水位≥{self.threshold_entry.get()}时下注{self.amount_entry.get()}RMB"):
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
                        self.status_label. config(text="状态: 已登录", fg='#00ff88')
                        self.login_btn.config(text="✓ 已登录", state='disabled')
                        self.bet_frame.pack(fill='x', padx=10, pady=5)
                        self.control_frame.pack(fill='x', padx=10, pady=10)
                        
                        if self.bot.api.uid:
                            self. uid_entry.delete(0, tk.END)
                            self. uid_entry.insert(0, self.bot.api.uid)
                            self.uid_label.config(text=f"UID: {self.bot.api.uid}", fg='#00ff88')
                        
                        if self.bot.api.ver:
                            self.ver_entry.delete(0, tk.END)
                            self.ver_entry.insert(0, self. bot.api.ver)
                            self.ver_label.config(text=f"ver: {self.bot.api.ver}", fg='#00ff88')
                        
                        self.create_odds_display_area(self.right_frame)
                        self. save_config()
                        self. refresh_data()
                    else:
                        self.status_label.config(text="状态: 登录失败", fg='#ff4444')
                        self.login_btn. config(state='normal', text="登录")
                
                self.root.after(0, update_ui)
            except Exception as e:
                self.log(f"登录异常: {e}")
                self.root.after(0, lambda: self.login_btn.config(state='normal', text="登录"))
        
        threading.Thread(target=login_thread, daemon=True).start()
    
    def start_monitoring(self):
        """开始监控"""
        manual_uid = self.uid_entry.get().strip()
        manual_ver = self.ver_entry.get().strip()
        
        if manual_uid: 
            self.bot.api.set_uid(manual_uid)
        if manual_ver:
            self. bot.api.set_ver(manual_ver)
        
        if not self.bot.api.uid or len(self.bot.api.uid) < 6:
            messagebox.showwarning("警告", "请输入有效的UID!")
            return
        
        if not self.bot.api.ver or 'mtfix' not in self.bot.api.ver:
            messagebox.showwarning("警告", "ver格式不正确!\n\n正确格式: 2026-01-13-mtfix_133")
            return
        
        try:
            interval = float(self.interval_entry.get())
            self.bot.bet_amount = float(self.amount_entry.get())
            self.bot.odds_threshold = float(self.threshold_entry.get())
        except ValueError:
            messagebox. showerror("错误", "请输入有效数字")
            return
        
        self.bot.auto_bet_enabled = self.auto_bet_var.get()
        self.bot.is_running = True
        self.save_config()
        
        self.start_btn.config(state='disabled')
        self.stop_btn.config(state='normal')
        self.status_label.config(text="状态:  监控中...", fg='#00ff88')
        
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
        self.log("监控已停止")
    
    def refresh_data(self):
        """刷新数据"""
        manual_uid = self.uid_entry.get().strip()
        manual_ver = self.ver_entry.get().strip()
        
        if manual_uid:
            self.bot.api.set_uid(manual_uid)
        if manual_ver:
            self.bot.api.set_ver(manual_ver)
        
        def refresh():
            self.log("刷新数据...")
            self.log(f"UID: {self. bot.api.uid}, ver: {self.bot.api. ver}")
            self.root.after(0, lambda: self.update_label. config(text="🔄 刷新中.. .", fg='#ffaa00'))
            
            data = self.bot.get_all_odds_data()
            self.update_odds_display(data)
            
            if data['success']:
                matches = data['matches']
                stats = self.bot.collector.get_statistics()
                self.log(f"✓ 获取 {len(matches)} 场比赛, {data['totalOdds']} 水位")
                self.log(f"  数据已收集: {stats['total_entries']} 条请求")
                for m in matches[: 3]: 
                    self.log(f"  {m['score1']} {m['team1'][: 15]} vs {m['team2'][:15]} {m['score2']}")
            else:
                self.log(f"❌ 失败: {data. get('error', '')[: 60]}")
                if data.get('hint'):
                    self.log(f"💡 {data['hint']}")
        
        threading.Thread(target=refresh, daemon=True).start()
    
    def diagnose_api(self):
        """API诊断"""
        def diagnose():
            self.log("\n" + "="*50)
            self.log("🔬 API诊断 v6.9")
            self.log("="*50)
            
            self.log(f"\n【API URL】 {self.bot.api.base_url}")
            self.log(f"【当前UID】 {self. bot.api.uid or '未设置'}")
            self.log(f"【当前ver】 {self.bot.api.ver or '未设置'}")
            self.log(f"【Cookies数】 {len(self.bot.api.cookies)}")
            
            # 检查ver格式
            ver = self.bot.api.ver
            if ver:
                if re.match(r'\d{4}-\d{2}-\d{2}-mtfix_\d+', ver):
                    self. log(f"【ver格式】 ✓ 正确")
                else:
                    self. log(f"【ver格式】 ✗ 错误，应为:  YYYY-MM-DD-mtfix_133")
            
            stats = self.bot.collector.get_statistics()
            self.log(f"\n【数据收集】")
            self.log(f"  请求数: {stats['total_entries']}")
            self.log(f"  快照数: {stats['total_pages']}")
            self.log(f"  文件大小: {stats['file_size']/1024:. 1f} KB")
            
            self.log(f"\n【测试请求】")
            test = self.bot.api.test_connection()
            
            if test. get('error') and isinstance(test.get('error'), str):
                self.log(f"❌ 错误: {test['error'][: 60]}")
            else:
                self.log(f"状态码: {test['status_code']}")
                self.log(f"响应长度: {test['response_length']}")
                self.log(f"有<game>:  {test['has_game_data']}")
                self.log(f"CheckEMNU: {test['is_check_menu']}")
                self. log(f"使用ver: {test. get('used_ver', '未知')}")
                
                if test['has_game_data'] and not test['has_error']:
                    self.log("\n✓ API正常!")
                elif 'table id error' in test.get('raw_preview', '').lower():
                    self.log("\n⚠ table id error")
                    self.log("  请点击「尝试不同日期」按钮")
                elif test['is_check_menu']: 
                    self.log("\n⚠ CheckEMNU - 权限检查失败")
            
            self.log("\n" + "="*50)
        
        threading.Thread(target=diagnose, daemon=True).start()
    
    def show_today_bets(self):
        """今日注单"""
        def fetch():
            self.log("\n查看注单...")
            result = self.bot.api.get_today_bets()
            if result['success']:
                bets = result['bets']
                self.log(f"共 {len(bets)} 笔, 总额 {result['total_bet']} RMB")
                for b in bets[: 5]:
                    self.log(f"  {b['w_id']} | {b['gold']}RMB @ {b['ioratio']}")
            else:
                self. log(f"❌ {result. get('error', '')}")
        
        threading.Thread(target=fetch, daemon=True).start()
    
    def on_closing(self):
        """关闭"""
        if messagebox.askokcancel("退出", "确定退出?\n\n数据已自���保存到JSON文件"):
            self.save_config()
            self.bot.stop()
            self.root.destroy()


# ================== 主程序 ==================
if __name__ == "__main__":
    root = tk. Tk()
    app = BettingBotGUI(root)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    root.mainloop()
