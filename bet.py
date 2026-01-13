#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
滚球水位实时监控系统 v7.0
- 新增：登录后实时收集浏览器XHR请求数据
- 新增：从Chrome DevTools Protocol获取网络请求
- 新增：保存完整的HAR格式数据到JSON
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
API_URL = "https://mos055.com/transform. php"
USERNAME = "LJJ123123"
PASSWORD = "zz66688899"
COOKIES_FILE = "mos055_cookies.pkl"
CONFIG_FILE = "bet_config.json"
HAR_DATA_FILE = "har_data. json"
XHR_DATA_FILE = "xhr_collected. json"  # 新增：XHR数据收集文件
BET_TYPES_ORDER = ['让球', '大/小', '独赢', '让球上半场', '大/小上半场', '独赢上半场', '下个进球', '双方球队进球']


class XHRCollector:
    """XHR请求收集器 - 从浏览器实时收集网络请求"""
    
    def __init__(self, filename=XHR_DATA_FILE):
        self.filename = filename
        self.is_collecting = False
        self.collect_thread = None
        self.driver = None
        self.lock = threading.Lock()
        
        # HAR格式数据结构
        self.har_data = {
            "log": {
                "version": "1.2",
                "creator": {
                    "name": "BettingBot XHR Collector",
                    "version":  "7.0"
                },
                "browser": {
                    "name":  "Chrome",
                    "version": "120.0"
                },
                "pages":  [{
                    "startedDateTime": datetime.now().isoformat(),
                    "id": "page_1",
                    "title": "mos055.com",
                    "pageTimings": {
                        "onContentLoad": -1,
                        "onLoad": -1
                    }
                }],
                "entries": []
            }
        }
        
        # 请求缓存（用于匹配请求和响应）
        self.pending_requests = {}
        
        # 加载已有数据
        self.load_existing()
    
    def load_existing(self):
        """加载已有的XHR数据"""
        try:
            if os.path. exists(self.filename):
                with open(self.filename, 'r', encoding='utf-8') as f:
                    existing = json.load(f)
                    if 'log' in existing and 'entries' in existing['log']:
                        # 保留已有entries
                        self.har_data['log']['entries'] = existing['log']['entries']
                        print(f"加载已有XHR数据: {len(self.har_data['log']['entries'])} 条")
        except Exception as e:
            print(f"加载XHR数据失败: {e}")
    
    def start_collecting(self, driver, log_callback=None):
        """开始收集XHR数据"""
        self.driver = driver
        self. is_collecting = True
        self.log_callback = log_callback or print
        
        # 启用网络监控
        try:
            self.driver.execute_cdp_cmd('Network.enable', {})
            self.log_callback("✓ 网络监控已启用")
        except Exception as e:
            self.log_callback(f"启用网络监控失败:  {e}")
        
        # 启动收集线程
        self.collect_thread = threading.Thread(target=self._collect_loop, daemon=True)
        self.collect_thread.start()
        
        self.log_callback("✓ XHR数据收集已启动")
    
    def stop_collecting(self):
        """停止收集"""
        self.is_collecting = False
        if self.collect_thread:
            self.collect_thread.join(timeout=2)
        self.save()
    
    def _collect_loop(self):
        """收集循环 - 从浏览器性能日志获取网络请求"""
        while self.is_collecting and self.driver:
            try:
                # 获取性能日志
                logs = self.driver.get_log('performance')
                
                for entry in logs:
                    try:
                        log_data = json.loads(entry['message'])
                        message = log_data.get('message', {})
                        method = message.get('method', '')
                        params = message.get('params', {})
                        
                        # 处理请求发送
                        if method == 'Network.requestWillBeSent':
                            self._handle_request(params)
                        
                        # 处理响应接收
                        elif method == 'Network.responseReceived': 
                            self._handle_response(params)
                        
                        # 处理数据接收完成
                        elif method == 'Network.loadingFinished':
                            self._handle_loading_finished(params)
                            
                    except Exception as e: 
                        pass
                
                time.sleep(0.5)  # 每0.5秒检查一次
                
            except Exception as e:
                if self.is_collecting:
                    time.sleep(1)
    
    def _handle_request(self, params):
        """处理请求发送事件"""
        request_id = params.get('requestId', '')
        request = params.get('request', {})
        url = request.get('url', '')
        
        # 只收集transform.php相关的XHR请求
        if 'transform.php' not in url:
            return
        
        timestamp = params.get('wallTime', time.time())
        
        # 解析请求头
        headers = []
        for name, value in request.get('headers', {}).items():
            headers.append({"name": name, "value": str(value)})
        
        # 解析POST数据
        post_data = request.get('postData', '')
        post_params = []
        if post_data: 
            for pair in post_data.split('&'):
                if '=' in pair:
                    name, value = pair.split('=', 1)
                    post_params.append({"name": name, "value":  value})
        
        # 解析URL参数
        query_string = []
        if '?' in url:
            query_part = url.split('?', 1)[1]
            for pair in query_part.split('&'):
                if '=' in pair:
                    name, value = pair.split('=', 1)
                    query_string. append({"name": name, "value": value})
        
        # 缓存请求信息
        self.pending_requests[request_id] = {
            "startedDateTime": datetime.fromtimestamp(timestamp).isoformat(),
            "time": 0,
            "request": {
                "method": request.get('method', 'GET'),
                "url":  url,
                "httpVersion": "HTTP/1.1",
                "cookies": [],
                "headers": headers,
                "queryString": query_string,
                "postData": {
                    "mimeType":  "application/x-www-form-urlencoded",
                    "text": post_data,
                    "params": post_params
                } if post_data else {},
                "headersSize": -1,
                "bodySize":  len(post_data) if post_data else 0
            },
            "response": None,
            "cache": {},
            "timings": {
                "blocked": -1,
                "dns": -1,
                "connect": -1,
                "send": 0,
                "wait": 0,
                "receive": 0,
                "ssl": -1
            },
            "serverIPAddress": "",
            "connection": request_id
        }
    
    def _handle_response(self, params):
        """处理响应接收事件"""
        request_id = params. get('requestId', '')
        response = params.get('response', {})
        
        if request_id not in self.pending_requests:
            return
        
        # 解析响应���
        headers = []
        for name, value in response.get('headers', {}).items():
            headers.append({"name": name, "value": str(value)})
        
        # 更新响应信息
        self.pending_requests[request_id]['response'] = {
            "status": response.get('status', 0),
            "statusText": response.get('statusText', ''),
            "httpVersion": "HTTP/1.1",
            "cookies": [],
            "headers": headers,
            "content": {
                "size": 0,
                "mimeType": response.get('mimeType', 'text/html'),
                "text": "",  # 稍后填充
                "encoding": "utf-8"
            },
            "redirectURL": "",
            "headersSize": -1,
            "bodySize": -1
        }
    
    def _handle_loading_finished(self, params):
        """处理加载完成事件 - 获取响应体"""
        request_id = params.get('requestId', '')
        
        if request_id not in self.pending_requests:
            return
        
        entry = self.pending_requests[request_id]
        
        if entry['response'] is None:
            return
        
        # 尝试获取响应体
        try:
            result = self.driver.execute_cdp_cmd('Network.getResponseBody', {'requestId': request_id})
            body = result.get('body', '')
            is_base64 = result.get('base64Encoded', False)
            
            if is_base64:
                try:
                    body = base64.b64decode(body).decode('utf-8')
                except: 
                    pass
            
            entry['response']['content']['text'] = body
            entry['response']['content']['size'] = len(body)
            
        except Exception as e:
            # 某些请求可能无法获取响应体
            pass
        
        # 计算时间
        encoded_data_length = params.get('encodedDataLength', 0)
        entry['response']['bodySize'] = encoded_data_length
        
        # 添加到entries
        with self.lock:
            self. har_data['log']['entries']. append(entry)
            del self.pending_requests[request_id]
        
        # 自动保存
        self.save()
        
        # 日志输出
        url = entry['request']['url']
        status = entry['response']['status']
        size = entry['response']['content']['size']
        if self.log_callback:
            self.log_callback(f"📥 XHR:  {url[: 50]}... | {status} | {size}B")
    
    def save(self):
        """保存HAR数据到文件"""
        try:
            with self.lock:
                with open(self.filename, 'w', encoding='utf-8') as f:
                    json. dump(self.har_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存XHR数据失败: {e}")
    
    def get_statistics(self):
        """获取统计信息"""
        with self.lock:
            entries = self.har_data['log']['entries']
            total_size = sum(e. get('response', {}).get('content', {}).get('size', 0) for e in entries)
            
            return {
                "total_requests": len(entries),
                "total_size":  total_size,
                "file_size": os.path.getsize(self. filename) if os.path.exists(self.filename) else 0,
                "is_collecting": self.is_collecting
            }
    
    def get_entries(self):
        """获取所有entries"""
        with self.lock:
            return self.har_data['log']['entries']. copy()
    
    def clear(self):
        """清空数据"""
        with self.lock:
            self.har_data['log']['entries'] = []
            self.pending_requests = {}
            self.save()
    
    def export(self, filename=None):
        """导出为HAR文件"""
        if not filename:
            filename = f"xhr_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.har"
        
        try:
            with self.lock:
                with open(filename, 'w', encoding='utf-8') as f:
                    json.dump(self. har_data, f, ensure_ascii=False, indent=2)
            return filename
        except: 
            return None


class DataCollector:
    """API请求数据收集器"""
    
    def __init__(self, filename=HAR_DATA_FILE):
        self.filename = filename
        self.entries = []
        self.start_time = datetime.now().isoformat()
        self.lock = threading.Lock()
        
        self.har_data = {
            "log": {
                "version": "1.2",
                "creator": {"name": "BettingBot API", "version": "7.0"},
                "browser": {"name":  "Python Requests", "version": "2.0"},
                "pages": [],
                "entries": []
            },
            "metadata": {
                "start_time": self.start_time,
                "total_requests": 0,
                "total_matches": 0,
                "total_odds": 0
            }
        }
        self.load_existing()
    
    def load_existing(self):
        try:
            if os.path. exists(self.filename):
                with open(self.filename, 'r', encoding='utf-8') as f:
                    existing = json.load(f)
                    if 'log' in existing and 'entries' in existing['log']:
                        self. har_data = existing
                        self.entries = existing['log']['entries']
        except: 
            pass
    
    def add_entry(self, request_data, response_data, parsed_data=None):
        with self.lock:
            entry = {
                "startedDateTime": datetime.now().isoformat(),
                "time": response_data.get('elapsed_time', 0),
                "request": {
                    "method": request_data.get('method', 'POST'),
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
                    "statusText": response_data. get('status_text', ''),
                    "httpVersion": "HTTP/1.1",
                    "headers": response_data. get('headers', []),
                    "content": {
                        "size": len(response_data.get('text', '')),
                        "mimeType": response_data.get('content_type', 'text/xml'),
                        "text": response_data.get('text', ''),
                        "encoding": "utf-8"
                    },
                    "cookies": []
                },
                "cache":  {},
                "timings": {"send": 0, "wait": response_data.get('elapsed_time', 0), "receive": 0},
                "_parsed": parsed_data
            }
            
            self.entries.append(entry)
            self.har_data['log']['entries'] = self.entries
            self. har_data['metadata']['total_requests'] = len(self.entries)
            
            if parsed_data:
                self.har_data['metadata']['total_matches'] = parsed_data.get('match_count', 0)
                self.har_data['metadata']['total_odds'] = parsed_data.get('odds_count', 0)
            
            self.save()
            return entry
    
    def add_match_data(self, matches, total_odds):
        with self. lock:
            snapshot = {
                "timestamp": datetime.now().isoformat(),
                "match_count":  len(matches),
                "total_odds": total_odds,
                "matches": matches
            }
            self.har_data['log']['pages'].append({
                "startedDateTime": snapshot['timestamp'],
                "id":  f"snapshot_{len(self.har_data['log']['pages'])}",
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
    
    def get_statistics(self):
        return {
            "total_entries": len(self.entries),
            "total_pages": len(self.har_data['log']['pages']),
            "start_time": self.start_time,
            "file_size": os.path.getsize(self.filename) if os.path.exists(self.filename) else 0
        }
    
    def clear(self):
        with self. lock:
            self.entries = []
            self.har_data['log']['entries'] = []
            self.har_data['log']['pages'] = []
            self.har_data['metadata']['total_requests'] = 0
            self.save()
    
    def export(self, filename=None):
        if not filename:
            filename = f"api_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(self. har_data, f, ensure_ascii=False, indent=2)
            return filename
        except: 
            return None


class BettingAPI:
    """投注API类"""
    
    def __init__(self, data_collector=None):
        self.session = requests.Session()
        self.base_url = "https://mos055.com/transform.php"
        self.cookies = {}
        self.uid = ""
        self.ver = None
        self.langx = "zh-cn"
        self.session.verify = False
        self.collector = data_collector or DataCollector()
        
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept':  'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'X-Requested-With': 'XMLHttpRequest',
            'Origin': 'https://mos055.com',
            'Referer': 'https://mos055.com/',
        })
    
    def build_ver(self, date_str=None):
        if not date_str:
            date_str = datetime.now().strftime('%Y-%m-%d')
        return f"{date_str}-mtfix_133"
    
    def set_cookies(self, cookies_dict):
        self.cookies = cookies_dict
        self.session.cookies.update(cookies_dict)
        
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
        
        self.ver = self.build_ver()
    
    def set_uid(self, uid):
        if uid:
            match = re.search(r'(\d{8})', str(uid))
            if match: 
                self.uid = match. group(1)
            else:
                digits = re.sub(r'\D', '', str(uid))
                if len(digits) >= 8:
                    self.uid = digits[:8]
                elif len(digits) >= 6:
                    self.uid = digits
    
    def set_ver(self, ver):
        if ver:
            ver = str(ver).strip()
            if re.match(r'\d{4}-\d{2}-\d{2}-mtfix', ver):
                self.ver = ver
            elif re.match(r'\d{4}-\d{2}-\d{2}', ver):
                self.ver = f"{ver}-mtfix_133"
            else:
                self.ver = self.build_ver()
    
    def get_rolling_matches(self, gtype='ft', ltype=3, sorttype='L'):
        try:
            if not self.ver or not re.match(r'\d{4}-\d{2}-\d{2}-mtfix', self. ver):
                self.ver = self.build_ver()
            
            params = {'ver': self.ver}
            data = {
                'p': 'get_game_list', 'uid': self.uid, 'langx': self.langx,
                'gtype': gtype. upper(), 'showtype': 'live', 'rtype': 'rb',
                'ltype': str(ltype), 'sorttype': sorttype, 'specialClick': '',
                'is498': 'N', 'ts': int(time.time() * 1000)
            }
            
            start_time = time.time()
            response = self.session.post(self.base_url, params=params, data=data, timeout=30, verify=False)
            elapsed_time = (time.time() - start_time) * 1000
            
            request_data = {
                'method': 'POST', 'url': f"{self.base_url}? ver={self.ver}",
                'headers': [{'name': k, 'value': v} for k, v in self.session. headers.items()],
                'params': [{'name': 'ver', 'value': self.ver}],
                'body': '&'.join([f"{k}={v}" for k, v in data.items()]),
                'form_data': [{'name': k, 'value': str(v)} for k, v in data.items()],
                'cookies': [{'name': k, 'value': v} for k, v in self.cookies.items()]
            }
            
            response_data = {
                'status_code': response.status_code, 'status_text': 'OK' if response.status_code == 200 else 'Error',
                'headers': [{'name': k, 'value': v} for k, v in response.headers.items()],
                'content_type': response.headers.get('Content-Type', 'text/xml'),
                'text': response. text, 'elapsed_time': elapsed_time
            }
            
            if response.status_code != 200:
                self.collector.add_entry(request_data, response_data, {'success': False, 'error': f'HTTP {response.status_code}'})
                return {'success': False, 'error':  f'HTTP {response.status_code}', 'matches': [], 'totalOdds': 0}
            
            xml_text = response.text
            
            if 'table id error' in xml_text. lower():
                self.collector. add_entry(request_data, response_data, {'success': False, 'error': 'table id error'})
                return {'success': False, 'error':  'table id error', 'matches': [], 'totalOdds': 0,
                        'hint': f'UID: {self.uid}, ver: {self.ver}'}
            
            if xml_text.strip() == 'CheckEMNU':
                self.collector.add_entry(request_data, response_data, {'success': False, 'error': 'CheckEMNU'})
                return {'success': False, 'error': 'CheckEMNU', 'matches': [], 'totalOdds': 0}
            
            matches, total_odds = self._parse_game_list_xml(xml_text)
            
            parsed_data = {'success': True, 'match_count': len(matches), 'odds_count': total_odds}
            self.collector.add_entry(request_data, response_data, parsed_data)
            self.collector.add_match_data(matches, total_odds)
            
            return {'success': True, 'matches': matches, 'totalOdds': total_odds, 'total_count': len(matches)}
            
        except Exception as e:
            return {'success': False, 'error': str(e), 'matches': [], 'totalOdds': 0}
    
    def _parse_game_list_xml(self, xml_text):
        matches = []
        total_odds = 0
        
        try:
            xml_text = re.sub(r'<\? xml[^>]*\?>', '', xml_text).strip().lstrip('\ufeff')
            if not xml_text:
                return matches, total_odds
            
            root = ET.fromstring(xml_text)
            
            for ec in root.findall('.//ec'):
                for game in ec.findall('game'):
                    match = self._extract_game_data(game)
                    if match and (match['team1'] or match['team2']):
                        total_odds += self._count_match_odds(match)
                        matches.append(match)
            
            if not matches:
                for game in root.findall('.//game'):
                    match = self._extract_game_data(game)
                    if match and (match['team1'] or match['team2']):
                        total_odds += self._count_match_odds(match)
                        matches.append(match)
                        
        except ET.ParseError:
            matches = self._fallback_regex_parse(xml_text)
            total_odds = sum(self._count_match_odds(m) for m in matches)
        
        return matches, total_odds
    
    def _extract_game_data(self, game_node):
        try:
            def get_text(tag, default=''):
                elem = game_node.find(tag)
                return elem.text. strip() if elem is not None and elem.text else default
            
            match = {
                'gid': get_text('GID') or game_node.get('id', ''),
                'league': get_text('LEAGUE', '未知联赛'),
                'team1': get_text('TEAM_H', ''), 'team2': get_text('TEAM_C', ''),
                'score1': get_text('SCORE_H', '0'), 'score2': get_text('SCORE_C', '0'),
                'time':  get_text('RETIMESET', ''), 'datetime': get_text('DATETIME', ''),
                'odds': {bt: {'handicap': '', 'home': [], 'away': [], 'draw': []} for bt in BET_TYPES_ORDER}
            }
            
            time_str = match['time']
            if '^' in time_str:
                parts = time_str.split('^')
                period_map = {'1H': '上半场', '2H': '下半场', 'HT': '中场'}
                match['time'] = f"{period_map. get(parts[0], parts[0])} {parts[1] if len(parts) > 1 else ''}"
            
            # 让球盘
            match['odds']['让球']['handicap'] = get_text('RATIO_RE')
            for side, tag, rtype in [('home', 'IOR_REH', 'REH'), ('away', 'IOR_REC', 'REC')]:
                val = self._parse_odds(get_text(tag))
                if val > 0:
                    match['odds']['让球'][side]. append({'value': val, 'wtype': 'RE', 'rtype': rtype, 'chose_team': 'H' if side == 'home' else 'C'})
            
            # 大小盘
            match['odds']['大/小']['handicap'] = get_text('RATIO_ROUO') or get_text('RATIO_ROUU')
            for side, tag, rtype in [('home', 'IOR_ROUH', 'ROUH'), ('away', 'IOR_ROUC', 'ROUC')]:
                val = self._parse_odds(get_text(tag))
                if val > 0:
                    match['odds']['大/小'][side].append({'value': val, 'wtype': 'ROU', 'rtype': rtype, 'chose_team': 'H' if side == 'home' else 'C'})
            
            # 独赢盘
            for side, tag, rtype, team in [('home', 'IOR_RMH', 'RMH', 'H'), ('draw', 'IOR_RMN', 'RMN', 'N'), ('away', 'IOR_RMC', 'RMC', 'C')]:
                val = self._parse_odds(get_text(tag))
                if val > 0:
                    match['odds']['独赢'][side].append({'value':  val, 'wtype': 'RM', 'rtype': rtype, 'chose_team':  team})
            
            # 上半场让球
            match['odds']['让球上半场']['handicap'] = get_text('RATIO_HRE')
            for side, tag, rtype in [('home', 'IOR_HREH', 'HREH'), ('away', 'IOR_HREC', 'HREC')]:
                val = self._parse_odds(get_text(tag))
                if val > 0:
                    match['odds']['让球上半场'][side]. append({'value': val, 'wtype': 'HRE', 'rtype': rtype, 'chose_team': 'H' if side == 'home' else 'C'})
            
            # 上半场大小
            match['odds']['大/小上半场']['handicap'] = get_text('RATIO_HROUO') or get_text('RATIO_HROUU')
            for side, tag, rtype in [('home', 'IOR_HROUH', 'HROUH'), ('away', 'IOR_HROUC', 'HROUC')]:
                val = self._parse_odds(get_text(tag))
                if val > 0:
                    match['odds']['大/小上半场'][side].append({'value': val, 'wtype': 'HROU', 'rtype': rtype, 'chose_team': 'H' if side == 'home' else 'C'})
            
            # 上半场独赢
            for side, tag, rtype, team in [('home', 'IOR_HRMH', 'HRMH', 'H'), ('draw', 'IOR_HRMN', 'HRMN', 'N'), ('away', 'IOR_HRMC', 'HRMC', 'C')]:
                val = self._parse_odds(get_text(tag))
                if val > 0:
                    match['odds']['独赢上半场'][side].append({'value': val, 'wtype':  'HRM', 'rtype': rtype, 'chose_team':  team})
            
            return match
        except:
            return None
    
    def _parse_odds(self, odds_str):
        try:
            if not odds_str:
                return 0.0
            val = float(str(odds_str).strip())
            return round(val / 100 if val > 50 else val, 2)
        except:
            return 0.0
    
    def _count_match_odds(self, match):
        return sum(len(od. get('home', [])) + len(od.get('away', [])) + len(od.get('draw', [])) for od in match.get('odds', {}).values())
    
    def _fallback_regex_parse(self, xml_text):
        matches = []
        for block in re.findall(r'<game[^>]*>.*?</game>', xml_text, re. DOTALL | re.IGNORECASE):
            def extract(pattern):
                m = re.search(pattern, block, re.IGNORECASE)
                return m.group(1) if m else ''
            team_h, team_c = extract(r'<TEAM_H>([^<]+)</TEAM_H>'), extract(r'<TEAM_C>([^<]+)</TEAM_C>')
            if team_h and team_c: 
                matches.append({
                    'gid': extract(r'<GID>(\d+)</GID>'), 'league': extract(r'<LEAGUE>([^<]+)</LEAGUE>') or '未知联赛',
                    'team1': team_h, 'team2': team_c, 'score1': extract(r'<SCORE_H>(\d*)</SCORE_H>') or '0',
                    'score2': extract(r'<SCORE_C>(\d*)</SCORE_C>') or '0', 'time': extract(r'<RETIMESET>([^<]*)</RETIMESET>'),
                    'odds': {bt: {'handicap':  '', 'home': [], 'away': [], 'draw': []} for bt in BET_TYPES_ORDER}
                })
        return matches
    
    def place_bet(self, gid, wtype, rtype, chose_team, ioratio, gold, gtype='FT'):
        try:
            params = {'ver': self.ver}
            data = {'p': 'FT_bet', 'golds': gold, 'gid': gid, 'gtype': gtype, 'wtype': wtype, 'rtype': rtype,
                    'chose_team':  chose_team, 'ioratio': ioratio, 'autoOdd': 'Y', 'isRB': 'Y',
                    'uid': self.uid, 'langx': self.langx, 'ts': int(time.time() * 1000)}
            response = self.session.post(self.base_url, params=params, data=data, timeout=15, verify=False)
            if response.status_code != 200:
                return {'success': False, 'error': f'HTTP {response.status_code}'}
            try:
                root = ET.fromstring(response. text)
                if (root.findtext('. //code') or '').lower() == 'success':
                    return {'success':  True, 'ticket_id': root.findtext('.//ticket_id', ''),
                            'bet_amount':  float(root.findtext('.//gold', '0') or 0),
                            'balance': float(root.findtext('. //nowcredit', '0') or 0)}
                return {'success': False, 'error': root.findtext('.//message', '下注失败')}
            except: 
                return {'success': 'success' in response.text. lower(), 'error': '解析失败'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def get_today_bets(self):
        try:
            response = self.session.post(self.base_url, params={'ver': self.ver},
                                        data={'p': 'get_today_wagers', 'uid': self.uid, 'langx': self.langx, 'ts': int(time. time() * 1000)},
                                        timeout=10, verify=False)
            try:
                data = json.loads(response.text)
                bets = [{'w_id': w. get('w_id', ''), 'gold': float(w.get('gold', 0) or 0), 'ioratio': float(w.get('ioratio', 0) or 0)}
                        for w in data. get('wagers', [])]
                return {'success': True, 'bets': bets, 'total_bet':  sum(b['gold'] for b in bets), 'count': len(bets)}
            except:
                return {'success':  False, 'bets': []}
        except Exception as e: 
            return {'success': False, 'error': str(e), 'bets': []}
    
    def test_connection(self):
        try:
            if not self.ver or not re.match(r'\d{4}-\d{2}-\d{2}-mtfix', self.ver):
                self.ver = self.build_ver()
            data = {'p': 'get_game_list', 'uid': self.uid, 'showtype': 'live', 'rtype': 'rb',
                    'gtype': 'FT', 'ltype': '3', 'langx': self. langx, 'ts': int(time.time() * 1000)}
            response = self.session.post(self. base_url, params={'ver': self.ver}, data=data, timeout=10, verify=False)
            return {'status_code': response.status_code, 'response_length': len(response.text),
                    'has_game_data': '<game' in response.text. lower() or '<GID>' in response.text,
                    'has_error': 'table id error' in response.text. lower(),
                    'raw_preview': response.text[: 500], 'used_ver': self.ver, 'used_uid': self.uid}
        except Exception as e:
            return {'error': str(e)}
    
    def try_different_vers(self):
        results = []
        today = datetime.now()
        for days_ago in range(7):
            date = today - __import__('datetime').timedelta(days=days_ago)
            ver = f"{date.strftime('%Y-%m-%d')}-mtfix_133"
            try:
                data = {'p': 'get_game_list', 'uid':  self.uid, 'showtype': 'live', 'rtype': 'rb',
                        'gtype': 'FT', 'ltype': '3', 'langx': self.langx, 'ts':  int(time.time() * 1000)}
                response = self.session.post(self.base_url, params={'ver': ver}, data=data, timeout=10, verify=False)
                success = '<game' in response.text.lower() or '<GID>' in response.text
                results.append({'ver': ver, 'success': success, 'length': len(response.text), 'preview': response.text[:100]})
                if success:
                    self.ver = ver
                    return results
            except Exception as e: 
                results.append({'ver': ver, 'error': str(e)})
        return results


class BettingBot:
    """投注机器人核心类"""
    
    def __init__(self):
        self.driver = None
        self.is_running = False
        self. is_logged_in = False
        self. wait = None
        self.auto_bet_enabled = False
        self. bet_amount = 2
        self.bet_history = []
        self.current_matches = []
        self.odds_threshold = 1.80
        
        # 数据收集器
        self.collector = DataCollector()
        self.xhr_collector = XHRCollector()  # 新增XHR收集器
        self.api = BettingAPI(self.collector)
    
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
        options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
        # 启用性能日志（用于收集网络请求）
        options.set_capability('goog:loggingPrefs', {'performance': 'ALL', 'browser': 'ALL'})
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
                    for (var e of els) { if (e.innerText.trim() === '否' && e.offsetWidth > 0) { e.click(); return true; } }
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
        log_callback("  从网络请求提取UID...")
        try:
            for entry in self.driver.get_log('performance')[-200:]:
                try:
                    msg = json.loads(entry['message']).get('message', {})
                    if msg.get('method') == 'Network.requestWillBeSent':
                        post_data = msg.get('params', {}).get('request', {}).get('postData', '')
                        match = re.search(r'uid=(\d{8})(? : &|$)', post_data)
                        if match:
                            log_callback(f"    ✓ 找到UID: {match.group(1)}")
                            return match.group(1)
                except:
                    pass
        except:
            pass
        
        log_callback("  从cookies提取UID...")
        try:
            for c in self.driver.get_cookies():
                match = re.search(r'_(\d{8})(?:_|$)', c['name'])
                if match:
                    log_callback(f"    ✓ 找到UID: {match.group(1)}")
                    return match. group(1)
        except:
            pass
        return None
    
    def extract_ver_from_network(self, log_callback):
        log_callback("  从网络请求提取ver...")
        try:
            for entry in self.driver.get_log('performance')[-300:]:
                try:
                    msg = json.loads(entry['message']).get('message', {})
                    if msg. get('method') == 'Network.requestWillBeSent': 
                        url = msg.get('params', {}).get('request', {}).get('url', '')
                        if 'transform. php' in url and 'ver=' in url: 
                            match = re.search(r'ver=([^&]+)', url)
                            if match and re.match(r'\d{4}-\d{2}-\d{2}-mtfix', match.group(1)):
                                log_callback(f"    ✓ 找到ver: {match.group(1)}")
                                return match. group(1)
                except: 
                    pass
        except: 
            pass
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
                for(var i of inputs) {{ if(i.offsetWidth>0) {{ i.value='{password}'; i.dispatchEvent(new Event('input',{{bubbles: true}})); break; }} }}
            """)
            log_callback(f"✓ 输入凭据: {username}")
            time.sleep(1)

            self.driver.execute_script("""
                var btn = document.getElementById('btn_login');
                if(btn) btn.click();
                else { var els = document.querySelectorAll('button, div, span');
                    for(var e of els) { if((e.innerText. trim()==='登录'||e.innerText.trim()==='登入') && e.offsetWidth>0) { e.click(); break; } } }
            """)
            log_callback("✓ 点击登录")
            time.sleep(10)

            self.handle_password_popup(log_callback)
            time.sleep(3)

            # 提取Cookies
            log_callback("\n提取Cookies...")
            cookies = self.driver.get_cookies()
            cookies_dict = {c['name']: c['value'] for c in cookies}
            log_callback(f"获取到 {len(cookies_dict)} 个cookies")
            
            log_callback("\nCookies详情:")
            for name, value in cookies_dict.items():
                if name.startswith('myGameVer_'):
                    try:
                        decoded = base64.b64decode(value).decode('utf-8')
                        log_callback(f"  ★ {name}:  {value} (解码:  {decoded}) [不使用]")
                    except: 
                        log_callback(f"  ★ {name}:  {value}")
                elif name. startswith('login_'):
                    log_callback(f"  ★ {name}: {value[: 30]}...")
            
            self.api.set_cookies(cookies_dict)
            
            if manual_uid and manual_uid. strip():
                self.api.set_uid(manual_uid. strip())
                log_callback(f"✓ 使用手动UID: {self.api.uid}")
            
            if not self.api.uid or len(self.api.uid) < 6:
                uid = self.extract_uid_from_page(log_callback)
                if uid:
                    self.api.set_uid(uid)
            
            self.api.ver = self.api.build_ver()
            log_callback(f"\n当前UID: {self.api.uid or '未设置'}")
            log_callback(f"当前ver: {self.api. ver}")

            with open(COOKIES_FILE, "wb") as f:
                pickle.dump(cookies, f)

            # 进入滚球页面
            log_callback("\n进入滚球页面...")
            self.driver.execute_script("""
                var els = document.querySelectorAll('*');
                for(var e of els) { if(e.textContent.trim()==='滚球' && e.offsetWidth>0) { e.click(); break; } }
            """)
            time.sleep(5)

            # 尝试从网络提取ver
            network_ver = self.extract_ver_from_network(log_callback)
            if network_ver: 
                self.api.ver = network_ver
                log_callback(f"✓ 使用网络请求中的ver: {network_ver}")

            if not self.api.uid or len(self.api.uid) < 6:
                uid = self.extract_uid_from_page(log_callback)
                if uid:
                    self.api.set_uid(uid)

            # ========== 关键：登录成功后启动XHR数据收集 ==========
            log_callback("\n🔴 启动XHR数据收集...")
            self.xhr_collector.start_collecting(self.driver, log_callback)
            log_callback(f"✓ XHR数据将保存到: {XHR_DATA_FILE}")

            # 测试API
            log_callback("\n测试API...")
            test = self.api.test_connection()
            if test. get('error'):
                log_callback(f"✗ 错误: {test['error'][: 60]}")
            else:
                log_callback(f"状态: {test['status_code']}, 长度: {test['response_length']}")
                if test['has_game_data']: 
                    log_callback("✓ API正常!")
                elif test. get('has_error'):
                    log_callback("⚠ table id error - 尝试不同日期...")
                    for r in self.api.try_different_vers():
                        status = "✓" if r. get('success') else "✗"
                        log_callback(f"  {status} {r['ver']}:  {r. get('preview', r.get('error', ''))[:50]}")
                        if r.get('success'):
                            break

            self.is_logged_in = True
            log_callback("\n✓ 登录完成!  XHR数据收集已启动")
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
                            result = self.api.place_bet(match['gid'], odds. get('wtype', 'RE'), odds.get('rtype', 'REH'),
                                                       odds.get('chose_team', 'H'), odds['value'], self.bet_amount)
                            if result['success']:
                                self.bet_history.append(bet_key)
                                log_callback("   ✓ 成功!")
                            else:
                                log_callback(f"   ✗ 失败: {result. get('error', '')}")
                            return result['success']
        return False
    
    def monitor_realtime(self, interval, log_callback, update_callback):
        log_callback(f"\n🚀 开始监控 | 间隔:{interval}s | 阈值:{self.odds_threshold}")
        log_callback(f"   UID:{self.api.uid} | ver:{self.api.ver}")
        log_callback(f"   API数据:  {HAR_DATA_FILE}")
        log_callback(f"   XHR数据: {XHR_DATA_FILE}")
        
        while self.is_running:
            try:
                data = self.get_all_odds_data()
                if data['success']:
                    update_callback(data)
                    api_stats = self.collector.get_statistics()
                    xhr_stats = self.xhr_collector.get_statistics()
                    log_callback(f"[{datetime.now().strftime('%H:%M:%S')}] {len(data['matches'])}场, {data['totalOdds']}水位 | API:{api_stats['total_entries']} XHR:{xhr_stats['total_requests']}")
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
        # 停止XHR收集
        self.xhr_collector.stop_collecting()
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
        self.root.title("滚球水位实时监控系统 v7.0 (XHR实时收集)")
        self.root.geometry("1920x1000")
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
                    config = json.load(f)
                    self.bot.odds_threshold = config.get('threshold', 1.80)
                    self.bot. bet_amount = config.get('bet_amount', 2)
                    self.threshold_entry.delete(0, tk.END)
                    self.threshold_entry. insert(0, str(self. bot.odds_threshold))
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
        
        tk.Label(title_frame, text="🎯 滚球水位实时监控系统 v7.0", bg='#1a1a2e', fg='#00ff88',
                font=('Microsoft YaHei UI', 22, 'bold')).pack()
        tk.Label(title_frame, text="XHR实时收集版 | 登录后自动收集浏览器XHR请求 | 保存完整HAR格式数据",
                bg='#1a1a2e', fg='#888', font=('Microsoft YaHei UI', 10)).pack()
        
        # ========== 主容器 ==========
        main_frame = tk.Frame(self. root, bg='#1a1a2e')
        main_frame.pack(fill='both', expand=True, padx=20, pady=10)
        
        # ========== 左侧面板 ==========
        left_frame = tk.Frame(main_frame, bg='#16213e', width=440)
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
        self.ver_entry.insert(0, datetime.now().strftime('%Y-%m-%d') + '-mtfix_133')
        
        btn_row = tk.Frame(login_frame, bg='#16213e')
        btn_row.grid(row=4, column=0, columnspan=2, pady=(10, 0))
        
        self.login_btn = tk.Button(btn_row, text="登录", bg='#00ff88', fg='#000',
                                  font=('Microsoft YaHei UI', 10, 'bold'), relief='flat',
                                  command=self.login, cursor='hand2', padx=20, pady=3)
        self.login_btn.pack(side='left', padx=5)
        
        self.try_ver_btn = tk.Button(btn_row, text="尝试不同日期", bg='#ff9900', fg='#000',
                                    font=('Microsoft YaHei UI', 9), relief='flat',
                                    command=self.try_different_vers, cursor='hand2', padx=10, pady=3)
        self.try_ver_btn.pack(side='left', padx=5)
        
        # ----- XHR数据收集状态 -----
        xhr_frame = tk.LabelFrame(left_frame, text="🔴 XHR实时收集", bg='#16213e',
                                 fg='#ff4444', font=('Microsoft YaHei UI', 11, 'bold'), padx=10, pady=10)
        xhr_frame.pack(fill='x', padx=10, pady=5)
        
        self.xhr_status_label = tk.Label(xhr_frame, text="状态: 未启动", bg='#16213e', fg='#888',
                                        font=('Microsoft YaHei UI', 10, 'bold'))
        self.xhr_status_label.pack(anchor='w')
        
        self.xhr_stats_label = tk.Label(xhr_frame, text="请求:  0 | 大小: 0 KB",
                                       bg='#16213e', fg='#aaa', font=('Microsoft YaHei UI', 9))
        self.xhr_stats_label.pack(anchor='w')
        
        self.xhr_file_label = tk.Label(xhr_frame, text=f"文件: {XHR_DATA_FILE}",
                                      bg='#16213e', fg='#666', font=('Microsoft YaHei UI', 8))
        self.xhr_file_label.pack(anchor='w')
        
        xhr_btn_frame = tk.Frame(xhr_frame, bg='#16213e')
        xhr_btn_frame. pack(fill='x', pady=(5, 0))
        
        self.xhr_view_btn = tk.Button(xhr_btn_frame, text="👁 查看XHR", bg='#336699', fg='#fff',
                                     font=('Microsoft YaHei UI', 9), relief='flat',
                                     command=self.view_xhr_data, cursor='hand2', padx=8)
        self.xhr_view_btn.pack(side='left', padx=(0, 3))
        
        self.xhr_export_btn = tk.Button(xhr_btn_frame, text="📤 导出HAR", bg='#669933', fg='#fff',
                                       font=('Microsoft YaHei UI', 9), relief='flat',
                                       command=self.export_xhr_data, cursor='hand2', padx=8)
        self.xhr_export_btn.pack(side='left', padx=(0, 3))
        
        self.xhr_clear_btn = tk.Button(xhr_btn_frame, text="🗑 清空", bg='#993333', fg='#fff',
                                      font=('Microsoft YaHei UI', 9), relief='flat',
                                      command=self.clear_xhr_data, cursor='hand2', padx=8)
        self.xhr_clear_btn.pack(side='left')
        
        # ----- API数据收集状态 -----
        api_frame = tk. LabelFrame(left_frame, text="📊 API数据收集", bg='#16213e',
                                 fg='#00ccff', font=('Microsoft YaHei UI', 11, 'bold'), padx=10, pady=10)
        api_frame.pack(fill='x', padx=10, pady=5)
        
        self. api_stats_label = tk.Label(api_frame, text="请求: 0 | 快照: 0 | 文件: 0 KB",
                                       bg='#16213e', fg='#aaa', font=('Microsoft YaHei UI', 9))
        self.api_stats_label.pack(anchor='w')
        
        self.api_file_label = tk.Label(api_frame, text=f"文件: {HAR_DATA_FILE}",
                                      bg='#16213e', fg='#666', font=('Microsoft YaHei UI', 8))
        self.api_file_label.pack(anchor='w')
        
        api_btn_frame = tk.Frame(api_frame, bg='#16213e')
        api_btn_frame.pack(fill='x', pady=(5, 0))
        
        self.api_view_btn = tk.Button(api_btn_frame, text="👁 查看", bg='#666', fg='#fff',
                                     font=('Microsoft YaHei UI', 9), relief='flat',
                                     command=self.view_api_data, cursor='hand2', padx=8)
        self.api_view_btn.pack(side='left', padx=(0, 3))
        
        self.api_export_btn = tk.Button(api_btn_frame, text="📤 导出", bg='#666', fg='#fff',
                                       font=('Microsoft YaHei UI', 9), relief='flat',
                                       command=self.export_api_data, cursor='hand2', padx=8)
        self.api_export_btn.pack(side='left', padx=(0, 3))
        
        self.api_clear_btn = tk.Button(api_btn_frame, text="🗑 清空", bg='#663333', fg='#fff',
                                      font=('Microsoft YaHei UI', 9), relief='flat',
                                      command=self.clear_api_data, cursor='hand2', padx=8)
        self.api_clear_btn.pack(side='left')
        
        # ----- 日志区域 -----
        log_frame = tk.LabelFrame(left_frame, text="📋 日志", bg='#16213e',
                                 fg='#888', font=('Microsoft YaHei UI', 10, 'bold'), padx=5, pady=5)
        log_frame.pack(fill='both', expand=True, padx=10, pady=5)
        
        self.log_text = scrolledtext.ScrolledText(log_frame, bg='#0f3460', fg='#00ff88',
                                                 font=('Consolas', 9), relief='flat', height=6, wrap='word')
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
        self.threshold_entry.insert(0, "1. 80")
        tk.Label(self.bet_frame, text="≥触发", bg='#16213e', fg='#888',
                font=('Microsoft YaHei UI', 9)).grid(row=2, column=2, padx=3)
        
        self.auto_bet_var = tk.BooleanVar(value=False)
        self.auto_bet_check = tk.Checkbutton(self.bet_frame, text="⚡ 启用自动下注",
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
                                 command=self. stop_monitoring, cursor='hand2', pady=10, state='disabled')
        self.stop_btn.pack(fill='x', pady=(0, 5))
        
        self.refresh_btn = tk.Button(self.control_frame, text="🔄 刷新数据", bg='#666',
                                    fg='#fff', font=('Microsoft YaHei UI', 10), relief='flat',
                                    command=self.refresh_data, cursor='hand2', pady=6)
        self.refresh_btn.pack(fill='x', pady=(0, 5))
        
        self. diagnose_btn = tk.Button(self.control_frame, text="🔬 API诊断", bg='#9933ff',
                                     fg='#fff', font=('Microsoft YaHei UI', 10, 'bold'), relief='flat',
                                     command=self. diagnose_api, cursor='hand2', pady=6)
        self.diagnose_btn.pack(fill='x')
        
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
                                  text="请先登录\n\nv7.0 新功能:\n\n🔴 登录后自动启动XHR数据收集\n📥 实时捕获浏览器transform. php请求\n💾 保存完整HAR格式数据到JSON\n📤 支持导出为标准. har文件",
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
            # API数据统计
            api_stats = self.bot.collector.get_statistics()
            api_size_kb = api_stats['file_size'] / 1024
            self.api_stats_label.config(
                text=f"请求: {api_stats['total_entries']} | 快照: {api_stats['total_pages']} | 文件: {api_size_kb:.1f} KB"
            )
            
            # XHR数据统计
            xhr_stats = self.bot.xhr_collector.get_statistics()
            xhr_size_kb = xhr_stats['total_size'] / 1024
            xhr_file_kb = xhr_stats['file_size'] / 1024
            
            if xhr_stats['is_collecting']:
                self.xhr_status_label.config(text="状态: 🔴 收集中", fg='#ff4444')
            else:
                self.xhr_status_label.config(text="状态: ⚪ 未启动", fg='#888')
            
            self.xhr_stats_label.config(
                text=f"请求: {xhr_stats['total_requests']} | 数据: {xhr_size_kb:.1f} KB | 文件: {xhr_file_kb:.1f} KB"
            )
        except: 
            pass
        
        self.root.after(2000, self.update_collector_stats)
    
    def view_xhr_data(self):
        """查看XHR数据"""
        self._view_data("XHR数据查看器", self.bot.xhr_collector. har_data, self.bot.xhr_collector.get_statistics())
    
    def view_api_data(self):
        """查看API数据"""
        self._view_data("API数据查看器", self.bot.collector.har_data, self.bot.collector.get_statistics())
    
    def _view_data(self, title, data, stats):
        """通用数据查看器"""
        view_window = tk.Toplevel(self.root)
        view_window.title(title)
        view_window.geometry("1100x750")
        view_window.configure(bg='#1a1a2e')
        
        tk.Label(view_window, text=f"📊 {title}", bg='#1a1a2e', fg='#00ff88',
                font=('Microsoft YaHei UI', 14, 'bold')).pack(pady=10)
        
        stats_text = f"总请求: {stats. get('total_requests', stats.get('total_entries', 0))} | 文件大小: {stats['file_size']/1024:.1f} KB"
        tk.Label(view_window, text=stats_text, bg='#1a1a2e', fg='#aaa',
                font=('Microsoft YaHei UI', 10)).pack()
        
        text_frame = tk.Frame(view_window, bg='#1a1a2e')
        text_frame.pack(fill='both', expand=True, padx=20, pady=10)
        
        text_widget = scrolledtext.ScrolledText(text_frame, bg='#0f3460', fg='#00ff88',
                                               font=('Consolas', 9), wrap='none')
        text_widget.pack(fill='both', expand=True)
        
        # 添加水平滚动条
        h_scroll = tk.Scrollbar(text_frame, orient='horizontal', command=text_widget.xview)
        h_scroll.pack(side='bottom', fill='x')
        text_widget.config(xscrollcommand=h_scroll.set)
        
        try:
            display_text = json.dumps(data, ensure_ascii=False, indent=2)
            text_widget.insert('1.0', display_text)
        except Exception as e:
            text_widget.insert('1.0', f"加载数据失败: {e}")
        
        btn_frame = tk.Frame(view_window, bg='#1a1a2e')
        btn_frame.pack(pady=10)
        
        tk.Button(btn_frame, text="刷新", bg='#336699', fg='#fff',
                 command=lambda: self._refresh_view(text_widget, data)).pack(side='left', padx=5)
        tk.Button(btn_frame, text="关闭", bg='#666', fg='#fff',
                 command=view_window.destroy).pack(side='left', padx=5)
    
    def _refresh_view(self, text_widget, data):
        """刷新数据视图"""
        text_widget.delete('1.0', tk.END)
        try:
            display_text = json.dumps(data, ensure_ascii=False, indent=2)
            text_widget.insert('1.0', display_text)
        except Exception as e:
            text_widget.insert('1.0', f"加载失败: {e}")
    
    def export_xhr_data(self):
        """导出XHR数据为HAR文件"""
        filename = filedialog.asksaveasfilename(
            defaultextension=".har",
            filetypes=[("HAR文件", "*.har"), ("JSON文件", "*.json"), ("所有文件", "*.*")],
            initialfilename=f"xhr_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.har"
        )
        if filename:
            result = self.bot.xhr_collector.export(filename)
            if result: 
                self.log(f"✓ XHR数据已导出:  {result}")
                messagebox.showinfo("导出成功", f"XHR数据已导出到:\n{result}")
            else:
                messagebox.showerror("导出失败", "导出失败")
    
    def export_api_data(self):
        """导出API数据"""
        filename = filedialog. asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON文件", "*.json"), ("所有文件", "*.*")],
            initialfilename=f"api_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )
        if filename:
            result = self.bot.collector.export(filename)
            if result:
                self.log(f"✓ API数据已导出:  {result}")
                messagebox. showinfo("导出成功", f"API数据已导出到:\n{result}")
    
    def clear_xhr_data(self):
        """清空XHR数据"""
        if messagebox.askyesno("确认", "确定要清空XHR收集数据吗？"):
            self.bot.xhr_collector.clear()
            self.log("✓ XHR数据已清空")
    
    def clear_api_data(self):
        """清空API数据"""
        if messagebox.askyesno("确认", "确定要清空API收集数据吗？"):
            self.bot.collector.clear()
            self.log("✓ API数据已清空")
    
    def try_different_vers(self):
        """尝试不同日期的ver"""
        def try_vers():
            self.log("\n尝试不同日期的ver...")
            manual_uid = self.uid_entry.get().strip()
            if manual_uid:
                self.bot.api. set_uid(manual_uid)
            if not self.bot.api.uid:
                self.log("✗ 请先输入UID")
                return
            
            for r in self.bot.api.try_different_vers():
                status = "✓" if r. get('success') else "✗"
                self.log(f"  {status} {r['ver']}:  {r. get('preview', r.get('error', ''))[:50]}")
                if r. get('success'):
                    self.root.after(0, lambda v=r['ver']: (
                        self.ver_entry.delete(0, tk.END),
                        self.ver_entry. insert(0, v),
                        self.ver_label.config(text=f"ver: {v}", fg='#00ff88')
                    ))
                    self.log(f"\n✓ 找到有效ver: {r['ver']}")
                    break
            else: 
                self.log("\n✗ 所有日期都失败")
        
        threading.Thread(target=try_vers, daemon=True).start()
    
    def create_odds_display_area(self, parent):
        """创建水位显示区域"""
        if self.hint_label: 
            self.hint_label. pack_forget()
        
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
                
                self.time_label.config(text=f"更��:  {timestamp}")
                self.update_label.config(text=f"🔄 {timestamp}", fg='#00ff88')
                
                uid = self.bot.api.uid
                ver = self.bot.api.ver
                self.uid_label.config(text=f"UID: {uid}" if uid else "UID: 未设置",
                                     fg='#00ff88' if uid else '#ff4444')
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
                    else:
                        tk.Label(self.odds_inner_frame, text="暂无比赛数据",
                                bg='#0f3460', fg='#888', font=('Microsoft YaHei UI', 11)).pack(pady=20)
                    return
                
                # 统计信息
                xhr_stats = self.bot.xhr_collector.get_statistics()
                api_stats = self.bot.collector.get_statistics()
                tk.Label(self.odds_inner_frame,
                        text=f"共 {len(matches)} 场比赛，{total_odds} 个水位 | XHR:{xhr_stats['total_requests']} API:{api_stats['total_entries']}",
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
                        league_frame. pack(fill='x', pady=(15, 5), padx=5)
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
                    
                    s_color = '#ff4444' if score1 and score1.isdigit() and int(score1) > 0 else '#fff'
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
                    
                    # 客队行
                    team2_frame = tk.Frame(match_frame, bg='#1e1e32')
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
                self. odds_canvas.configure(scrollregion=self.odds_canvas.bbox('all'))
                
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
                        self.status_label. config(text="状态: 已登录 | XHR收集中", fg='#00ff88')
                        self.login_btn.config(text="✓ 已登录", state='disabled')
                        self.bet_frame.pack(fill='x', padx=10, pady=5)
                        self.control_frame.pack(fill='x', padx=10, pady=10)
                        
                        if self.bot.api.uid:
                            self. uid_entry.delete(0, tk.END)
                            self.uid_entry. insert(0, self.bot. api.uid)
                            self.uid_label.config(text=f"UID: {self.bot.api.uid}", fg='#00ff88')
                        
                        if self. bot.api.ver:
                            self.ver_entry.delete(0, tk.END)
                            self.ver_entry. insert(0, self.bot. api.ver)
                            self.ver_label.config(text=f"ver: {self. bot.api.ver}", fg='#00ff88')
                        
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
            messagebox.showwarning("警告", "ver格式不正确!")
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
        self.status_label.config(text="状态:  监控中 | XHR收集中", fg='#00ff88')
        
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
        self.status_label.config(text="状态: 已停止 | XHR收集中", fg='#ffaa00')
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
                xhr_stats = self.bot.xhr_collector.get_statistics()
                self.log(f"✓ 获取 {len(matches)} 场比赛, {data['totalOdds']} 水位")
                self.log(f"  XHR已收集: {xhr_stats['total_requests']} 条请求")
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
            self.log("🔬 API诊断 v7.0")
            self.log("="*50)
            
            self.log(f"\n【API】 {self.bot.api.base_url}")
            self.log(f"【UID】 {self.bot. api.uid or '未设置'}")
            self.log(f"【ver】 {self.bot.api.ver or '未设置'}")
            
            xhr_stats = self.bot.xhr_collector.get_statistics()
            api_stats = self.bot.collector.get_statistics()
            self.log(f"\n【XHR收集】 {'🔴 运行中' if xhr_stats['is_collecting'] else '⚪ 未启动'}")
            self.log(f"  请求数: {xhr_stats['total_requests']}")
            self.log(f"  数据量: {xhr_stats['total_size']/1024:. 1f} KB")
            
            self.log(f"\n���API收集】")
            self.log(f"  请求数: {api_stats['total_entries']}")
            self.log(f"  快照数: {api_stats['total_pages']}")
            
            self.log(f"\n【测试请求】")
            test = self.bot.api.test_connection()
            if test. get('error') and isinstance(test.get('error'), str):
                self.log(f"❌ 错误: {test['error'][: 60]}")
            else:
                self.log(f"状态码: {test['status_code']}")
                self.log(f"响应长度: {test['response_length']}")
                if test.get('has_game_data'):
                    self.log("✓ API正常!")
                elif test.get('has_error'):
                    self.log("⚠ table id error - 点击「尝试不同日期」")
            
            self.log("\n" + "="*50)
        
        threading.Thread(target=diagnose, daemon=True).start()
    
    def on_closing(self):
        """关闭"""
        if messagebox.askokcancel("退出", "确定退出?\n\nXHR数据已自动保存到JSON文件"):
            self.save_config()
            self.bot.stop()
            self.root.destroy()


# ================== 主程序 ==================
if __name__ == "__main__":
    root = tk.Tk()
    app = BettingBotGUI(root)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    root.mainloop()
